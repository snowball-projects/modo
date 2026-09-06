"""Compile and describe a production GraphML road snapshot."""

import json
import platform
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

import networkx as nx
import numpy as np
import scipy

from modo import CompactRoadGraph, __version__
from modo.snapshots import is_https_url

WEIGHT = "travel_time"


def digest(path):
    result = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def validate_source(graph):
    """Require the directed, explicit, positive costs used in production."""
    if not graph.is_directed():
        raise ValueError("production source graph must be directed")
    if not graph.number_of_edges():
        raise ValueError("production source graph must contain edges")
    for _start, _end, attributes in graph.edges(data=True):
        if WEIGHT not in attributes:
            raise ValueError(f"every production edge must define {WEIGHT}")
        try:
            value = float(attributes[WEIGHT])
        except (OverflowError, TypeError, ValueError) as error:
            raise ValueError(
                f"every production edge must define positive {WEIGHT}"
            ) from error
        if not 0 < value < float("inf"):
            raise ValueError(f"every production edge must define positive {WEIGHT}")


def _temporary(parent):
    with NamedTemporaryFile(dir=parent, delete=False) as output:
        return Path(output.name)


def _write_manifest(path, metadata):
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def _publish_pair(staged_artifact, artifact, staged_manifest, manifest):
    pairs = ((staged_artifact, artifact), (staged_manifest, manifest))
    backups = {}
    published = []
    try:
        for _staged, target in pairs:
            if target.exists():
                backup = _temporary(target.parent)
                backup.unlink()
                target.replace(backup)
                backups[target] = backup
        for staged, target in pairs:
            staged.replace(target)
            published.append(target)
    except Exception:
        for target in published:
            target.unlink(missing_ok=True)
        for target, backup in backups.items():
            backup.replace(target)
        raise
    else:
        for backup in backups.values():
            backup.unlink(missing_ok=True)


def _metadata(source, source_url, source_sha256, graph, road, artifact, staged):
    coordinates = road._coordinates
    bounds = [
        float(coordinates[:, 0].min()),
        float(coordinates[:, 1].min()),
        float(coordinates[:, 0].max()),
        float(coordinates[:, 1].max()),
    ]
    return {
        "schema_version": 1,
        "source": {
            "file": source.name,
            "sha256": source_sha256,
            **({"url": source_url} if source_url else {}),
            **{
                key: str(graph.graph[key])
                for key in ("created_date", "created_with", "crs", "simplified")
                if key in graph.graph
            },
        },
        "build": {
            "modo": __version__,
            "networkx": nx.__version__,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "scipy": scipy.__version__,
            "weight": WEIGHT,
        },
        "graph": {
            "bounds": bounds,
            "directed": True,
            "edges": int(road._matrix.nnz),
            "vertices": len(road._vertices),
        },
        "artifact": {
            "file": artifact.name,
            "sha256": digest(staged),
            "bytes": staged.stat().st_size,
        },
    }


def build(source, destination, manifest=None, source_url=None):
    """Build a validated snapshot and a checksummed provenance manifest."""
    source, destination = Path(source), Path(destination)
    manifest = (
        Path(manifest)
        if manifest
        else destination.with_suffix(destination.suffix + ".build.json")
    )
    if len({source.resolve(), destination.resolve(), manifest.resolve()}) != 3:
        raise ValueError("source, destination, and manifest must be different files")
    if source_url is not None and not is_https_url(source_url):
        raise ValueError("source URL must use HTTPS without credentials")
    source_sha256 = digest(source)
    graph = nx.read_graphml(source)
    if digest(source) != source_sha256:
        raise RuntimeError("source graph changed while it was being read")
    validate_source(graph)
    road = CompactRoadGraph.from_networkx(graph, WEIGHT).validate_snapshot()
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    if any(path.exists() and not path.is_file() for path in (destination, manifest)):
        raise ValueError("destination and manifest must be files")
    staged_artifact = _temporary(destination.parent)
    staged_manifest = _temporary(manifest.parent)
    try:
        road.save(staged_artifact)
        metadata = _metadata(
            source,
            source_url,
            source_sha256,
            graph,
            road,
            destination,
            staged_artifact,
        )
        _write_manifest(staged_manifest, metadata)
        _publish_pair(staged_artifact, destination, staged_manifest, manifest)
        return metadata
    finally:
        staged_artifact.unlink(missing_ok=True)
        staged_manifest.unlink(missing_ok=True)


def main():
    parser = ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--manifest")
    parser.add_argument("--source-url")
    args = parser.parse_args()
    build(args.source, args.destination, args.manifest, args.source_url)


if __name__ == "__main__":
    main()
