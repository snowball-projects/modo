import json
from hashlib import sha256
from types import SimpleNamespace

import networkx as nx
import pytest

from modo import CompactRoadGraph
from scripts import build_snapshot, validate_snapshot


def source_graph():
    graph = nx.MultiDiGraph(
        created_date="2026-08-31",
        created_with="test",
        crs="epsg:4326",
        simplified=True,
    )
    graph.add_node("a", x=-88, y=41)
    graph.add_node("b", x=-87, y=42)
    graph.add_edge("a", "b", travel_time=2.5)
    return graph


def test_builds_validated_snapshot_with_provenance_manifest(tmp_path):
    source = tmp_path / "roads.graphml"
    destination = tmp_path / "roads.npz"
    nx.write_graphml(source_graph(), source)
    metadata = build_snapshot.build(
        source,
        destination,
        source_url="https://download.example.test/roads.graphml",
    )
    manifest = destination.with_suffix(".npz.build.json")
    assert json.loads(manifest.read_text()) == metadata
    assert metadata["source"]["sha256"] == sha256(source.read_bytes()).hexdigest()
    assert metadata["source"]["url"].startswith("https://")
    assert metadata["graph"] == {
        "bounds": [41.0, -88.0, 42.0, -87.0],
        "directed": True,
        "edges": 1,
        "vertices": 2,
    }
    road = CompactRoadGraph.load(destination)
    assert road.validate_snapshot(metadata["graph"]["bounds"]) is road
    snapshot = SimpleNamespace(
        sha256=metadata["artifact"]["sha256"],
        graph_bounds=tuple(metadata["graph"]["bounds"]),
    )
    assert validate_snapshot.validate(snapshot, destination).coordinate("a") == (
        41.0,
        -88.0,
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("undirected", "must be directed"),
        ("empty", "must contain edges"),
        ("missing", "must define travel_time"),
        ("zero", "must define positive travel_time"),
        ("infinite", "must define positive travel_time"),
    ],
)
def test_rejects_nonproduction_source_graphs(change, message):
    graph = source_graph()
    if change == "undirected":
        graph = nx.MultiGraph(graph)
    elif change == "empty":
        graph.remove_edges_from(list(graph.edges))
    elif change == "missing":
        del next(iter(graph.edges(data=True)))[2]["travel_time"]
    elif change == "zero":
        next(iter(graph.edges(data=True)))[2]["travel_time"] = 0
    else:
        next(iter(graph.edges(data=True)))[2]["travel_time"] = float("inf")
    with pytest.raises(ValueError, match=message):
        build_snapshot.validate_source(graph)


def test_rejects_unverifiable_source_url(tmp_path):
    source = tmp_path / "roads.graphml"
    nx.write_graphml(source_graph(), source)
    with pytest.raises(ValueError, match="source URL must use HTTPS"):
        build_snapshot.build(source, tmp_path / "roads.npz", source_url="file:///roads")


def test_refuses_to_overwrite_build_inputs(tmp_path):
    source = tmp_path / "roads.graphml"
    nx.write_graphml(source_graph(), source)
    with pytest.raises(ValueError, match="must be different files"):
        build_snapshot.build(source, source)


def test_manifest_staging_failure_preserves_existing_pair(tmp_path, monkeypatch):
    source = tmp_path / "roads.graphml"
    destination = tmp_path / "roads.npz"
    manifest = tmp_path / "roads.manifest.json"
    nx.write_graphml(source_graph(), source)
    destination.write_bytes(b"existing artifact")
    manifest.write_bytes(b"existing manifest")

    def fail(_path, _metadata):
        raise OSError("manifest write failed")

    monkeypatch.setattr(build_snapshot, "_write_manifest", fail)
    with pytest.raises(OSError, match="manifest write failed"):
        build_snapshot.build(source, destination, manifest)
    assert destination.read_bytes() == b"existing artifact"
    assert manifest.read_bytes() == b"existing manifest"


def test_publish_failure_rolls_back_existing_pair(tmp_path, monkeypatch):
    artifact = tmp_path / "roads.npz"
    manifest = tmp_path / "roads.manifest.json"
    staged_artifact = tmp_path / "staged.npz"
    staged_manifest = tmp_path / "staged.manifest.json"
    artifact.write_bytes(b"existing artifact")
    manifest.write_bytes(b"existing manifest")
    staged_artifact.write_bytes(b"new artifact")
    staged_manifest.write_bytes(b"new manifest")
    replace = type(staged_manifest).replace

    def fail_manifest(self, target):
        if self == staged_manifest:
            raise OSError("manifest publish failed")
        return replace(self, target)

    monkeypatch.setattr(type(staged_manifest), "replace", fail_manifest)
    with pytest.raises(OSError, match="manifest publish failed"):
        build_snapshot._publish_pair(
            staged_artifact, artifact, staged_manifest, manifest
        )
    assert artifact.read_bytes() == b"existing artifact"
    assert manifest.read_bytes() == b"existing manifest"
