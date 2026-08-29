import networkx as nx
import numpy as np
import pytest

import modo
from modo import CompactRoadGraph, analyze_vertices


@pytest.fixture
def graph():
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=0, y=0)
    graph.add_node("b", x=10, y=0)
    graph.add_node("x", x=2, y=1)
    graph.add_node("y", x=3, y=1)
    graph.add_edge("a", "x", travel_time=8)
    graph.add_edge("a", "x", travel_time=1)
    graph.add_edge("b", "x", travel_time=9)
    graph.add_edge("a", "y", travel_time=5)
    graph.add_edge("b", "y", travel_time=6)
    return graph


def write_single_edge_archive(path, **changes):
    graph = nx.DiGraph()
    graph.add_node("a", x=0, y=0)
    graph.add_node("b", x=1, y=1)
    graph.add_edge("a", "b", travel_time=1)
    CompactRoadGraph.from_networkx(graph).save(path)
    with np.load(path, allow_pickle=False) as archive:
        values = {name: archive[name] for name in archive.files}
    values.update(changes)
    with open(path, "wb") as output:
        np.savez_compressed(output, **values)


@pytest.mark.parametrize(("objective", "tolerance"), [
    ("total", 0), ("total", 0.75), ("maximum", 0), ("maximum", 3),
])
def test_compact_results_match_networkx(graph, objective, tolerance):
    expected = analyze_vertices(graph, ["a", "b"]).optimize(objective, tolerance)
    road = CompactRoadGraph.from_networkx(graph)
    assert road.analyze_vertices(["a", "b"]).optimize(objective, tolerance) == expected


def test_compact_analysis_runs_one_sparse_search(graph, monkeypatch):
    import modo.compact

    sparse_dijkstra = modo.compact.dijkstra
    calls = []

    def counted(*args, **kwargs):
        calls.append(kwargs["indices"])
        return sparse_dijkstra(*args, **kwargs)

    monkeypatch.setattr(modo.compact, "dijkstra", counted)
    analysis = CompactRoadGraph.from_networkx(graph).analyze_vertices(["a", "b"])
    assert analysis.optimize().vertex == "x"
    assert analysis.optimize("maximum").vertex == "y"
    assert analysis.travel_times("y").travel_times_seconds == (5, 6)
    assert calls == [[0, 1]]


@pytest.mark.parametrize(("objective", "tolerance"), [
    ("total", 0), ("total", 0.75), ("maximum", 0), ("maximum", 3),
])
def test_memory_bounded_analysis_matches_retained_fields(
        graph, objective, tolerance):
    road = CompactRoadGraph.from_networkx(graph)
    retained = road.analyze_vertices(["a", "b"])
    bounded = road.analyze_vertices(["a", "b"], retain_distances=False)
    assert bounded.optimize(objective, tolerance) == retained.optimize(
        objective, tolerance)
    assert bounded.travel_times("y") == retained.travel_times("y")
    assert bounded._distances is None


def test_memory_bounded_analysis_streams_origins_and_reverses_queries(
        graph, monkeypatch):
    import modo.compact

    sparse_dijkstra = modo.compact.dijkstra
    calls = []

    def counted(*args, **kwargs):
        calls.append(kwargs["indices"])
        return sparse_dijkstra(*args, **kwargs)

    monkeypatch.setattr(modo.compact, "dijkstra", counted)
    analysis = CompactRoadGraph.from_networkx(graph).analyze_vertices(
        ["a", "b"], retain_distances=False)
    assert analysis.optimize().vertex == "x"
    assert analysis.optimize("maximum").vertex == "y"
    assert calls == [0, 1, 2, 3]
    assert analysis.travel_times("y").travel_times_seconds == (5, 6)
    assert calls == [0, 1, 2, 3, 3]


def test_memory_bounded_mode_requires_a_bool(graph):
    road = CompactRoadGraph.from_networkx(graph)
    with pytest.raises(TypeError, match="retain_distances must be a bool"):
        road.analyze_vertices(["a", "b"], retain_distances="no")


def test_compact_coordinate_queries_match_networkx(graph):
    road = CompactRoadGraph.from_networkx(graph)
    analysis = road.analyze_coordinates([(0, 0.1), (0, 9.9)])
    assert analysis.origin_vertices == ("a", "b")
    assert analysis.travel_times_at_coordinate((1, 2.1)).vertex == "x"
    assert analysis.travel_times_at_coordinate((1, 2.1)).travel_times_seconds == (1, 9)


def test_compact_tie_breaks_by_vertex_string():
    graph = nx.DiGraph()
    for vertex, longitude in [("b", 2), ("a", 1), ("first", 0), ("second", 3)]:
        graph.add_node(vertex, x=longitude, y=0)
    for origin in ("first", "second"):
        graph.add_edge(origin, "a", travel_time=1)
        graph.add_edge(origin, "b", travel_time=1)
    result = CompactRoadGraph.from_networkx(graph).analyze_vertices(
        ["first", "second"]).optimize()
    assert result.vertex == "a"
    assert result.region == {"a", "b"}


@pytest.mark.parametrize("candidates", [(1, "1"), ("1", 1)])
def test_tie_breaking_distinguishes_mixed_vertex_types(candidates):
    graph = nx.DiGraph()
    for longitude, vertex in enumerate([*candidates, "first", "second"]):
        graph.add_node(vertex, x=longitude, y=0)
    for origin in ("first", "second"):
        for vertex in candidates:
            graph.add_edge(origin, vertex, travel_time=1)
    expected = analyze_vertices(graph, ["first", "second"]).optimize()
    actual = CompactRoadGraph.from_networkx(graph).analyze_vertices(
        ["first", "second"]).optimize()
    assert actual == expected
    assert actual.vertex == 1


def test_opaque_vertex_ties_fall_back_to_graph_order():
    class Vertex:
        pass

    first, second = Vertex(), Vertex()
    graph = nx.DiGraph()
    for longitude, vertex in enumerate([second, first, "origin-a", "origin-b"]):
        graph.add_node(vertex, x=longitude, y=0)
    for origin in ("origin-a", "origin-b"):
        graph.add_edge(origin, first, travel_time=1)
        graph.add_edge(origin, second, travel_time=1)
    expected = analyze_vertices(graph, ["origin-a", "origin-b"]).optimize()
    actual = CompactRoadGraph.from_networkx(graph).analyze_vertices(
        ["origin-a", "origin-b"]).optimize()
    assert actual == expected
    assert actual.vertex is second


def test_total_tolerance_boundary_matches_networkx():
    graph = nx.DiGraph()
    for longitude, vertex in enumerate(["first", "second", "third", "best", "edge"]):
        graph.add_node(vertex, x=longitude, y=0)
    for origin, best, edge in zip(
            ("first", "second", "third"), (0.1, 0.1, 0.1), (0.2, 0.4, 0.3)):
        graph.add_edge(origin, "best", travel_time=best)
        graph.add_edge(origin, "edge", travel_time=edge)
    expected = analyze_vertices(graph, ["first", "second", "third"]).optimize(
        tolerance_seconds=0.6)
    actual = CompactRoadGraph.from_networkx(graph).analyze_vertices(
        ["first", "second", "third"]).optimize(tolerance_seconds=0.6)
    assert actual == expected
    assert actual.region == {"best", "edge"}
    assert actual.region_excess_seconds["edge"] == 0.6


def test_compact_undirected_and_missing_weights_match_networkx():
    graph = nx.Graph()
    graph.add_node(2, x=2, y=0)
    graph.add_node(1, x=1, y=0)
    graph.add_edge(1, 2)
    expected = analyze_vertices(graph, [2]).optimize()
    result = CompactRoadGraph.from_networkx(graph).analyze_vertices([2]).optimize()
    assert result == expected


def test_numeric_string_and_parallel_weights_match_networkx():
    graph = nx.MultiDiGraph()
    for longitude, vertex in enumerate(["first", "second", "target"]):
        graph.add_node(vertex, x=longitude, y=0)
    graph.add_edge("first", "target", travel_time="4")
    graph.add_edge("first", "target", travel_time=2)
    graph.add_edge("second", "target", travel_time="3")
    expected = analyze_vertices(graph, ["first", "second"]).optimize()
    actual = CompactRoadGraph.from_networkx(graph).analyze_vertices(
        ["first", "second"]).optimize()
    assert actual == expected
    assert actual.travel_times_seconds == (2, 3)


@pytest.mark.parametrize("weight", [
    -1, float("nan"), float("inf"), "slow", 10**400,
])
def test_compact_rejects_invalid_weights(weight):
    graph = nx.DiGraph()
    graph.add_node("a", x=0, y=0)
    graph.add_node("b", x=1, y=0)
    graph.add_edge("a", "b", travel_time=weight)
    with pytest.raises(ValueError, match="nonnegative"):
        CompactRoadGraph.from_networkx(graph)


def test_nonfinite_total_scores_fail_consistently():
    graph = nx.DiGraph()
    graph.add_node("first", x=0, y=0)
    graph.add_node("second", x=1, y=0)
    graph.add_node("target", x=2, y=0)
    graph.add_edge("first", "target", travel_time=1e308)
    graph.add_edge("second", "target", travel_time=1e308)
    analyses = (
        analyze_vertices(graph, ["first", "second"]),
        CompactRoadGraph.from_networkx(graph).analyze_vertices(["first", "second"]),
        CompactRoadGraph.from_networkx(graph).analyze_vertices(
            ["first", "second"], retain_distances=False),
    )
    for analysis in analyses:
        assert analysis.optimize("maximum").objective_seconds == 1e308
        with pytest.raises(ValueError, match="objective scores must be finite"):
            analysis.optimize("total")


def test_compact_graph_round_trip_and_coordinates(graph, tmp_path):
    expected = CompactRoadGraph.from_networkx(graph)
    expected_result = expected.analyze_vertices(["a", "b"]).optimize("maximum", 3)
    expected._matrix.indices = expected._matrix.indices.astype("int64")
    expected._matrix.indptr = expected._matrix.indptr.astype("int64")
    path = tmp_path / "roads.npz"
    expected.save(path)
    duplicate = tmp_path / "duplicate.npz"
    expected.save(duplicate)
    assert path.read_bytes() == duplicate.read_bytes()
    actual = CompactRoadGraph.load(path)
    assert actual._matrix.indices.dtype.name == "int32"
    assert actual._matrix.indptr.dtype.name == "int32"
    assert actual.coordinate("x") == (1.0, 2.0)
    assert actual.coordinates(["y", "x"]) == ((1.0, 3.0), (1.0, 2.0))
    assert actual.analyze_vertices(["a", "b"]).optimize("maximum", 3) == expected_result


@pytest.mark.parametrize(("field", "value"), [
    ("indices", np.array([2**32 + 1], dtype=np.uint64)),
    ("indices", np.array([1.0])),
    ("indices", np.array([2], dtype=np.int32)),
    ("indices", np.array([1, 1], dtype=np.int32)),
    ("indptr", np.array([0, 2**32 + 1, 2**32 + 1], dtype=np.uint64)),
    ("indptr", np.array([0.0, 1.0, 1.0])),
    ("indptr", np.array([0, 1], dtype=np.int32)),
    ("indptr", np.array([0, 1, 0], dtype=np.int32)),
])
def test_compact_load_rejects_malformed_csr_arrays(tmp_path, field, value):
    path = tmp_path / "roads.npz"
    write_single_edge_archive(path, **{field: value})
    with pytest.raises(ValueError, match="invalid compact road graph"):
        CompactRoadGraph.load(path)


@pytest.mark.parametrize("coordinates", [
    [[0, 0], [float("nan"), 1]],
    [[0, 0], [1, float("inf")]],
    [[0, 0], [91, 1]],
    [[0, 0], [1, 181]],
])
def test_compact_load_rejects_invalid_road_coordinates(tmp_path, coordinates):
    path = tmp_path / "roads.npz"
    write_single_edge_archive(path, coordinates=np.array(coordinates))
    with pytest.raises(ValueError, match="invalid compact road graph coordinates"):
        CompactRoadGraph.load(path)


def test_compact_load_rejects_empty_graph(tmp_path):
    path = tmp_path / "roads.npz"
    write_single_edge_archive(
        path,
        vertices=np.frombuffer(b"[]", dtype=np.uint8),
        coordinates=np.empty((0, 2)),
        data=np.array([]),
        indices=np.array([], dtype=np.int32),
        indptr=np.array([0], dtype=np.int32),
    )
    with pytest.raises(ValueError, match="invalid compact road graph vertices"):
        CompactRoadGraph.load(path)


@pytest.mark.parametrize(("attribute", "value"), [
    ("y", float("nan")),
    ("x", float("inf")),
    ("y", 91),
    ("x", 181),
])
def test_all_networkx_coordinates_are_validated_by_both_backends(attribute, value):
    graph = nx.DiGraph()
    graph.add_node("origin", x=0, y=0)
    graph.add_node("invalid", x=1, y=1)
    graph.nodes["invalid"][attribute] = value
    for compile_graph in (
        lambda: analyze_vertices(graph, ["origin"]),
        lambda: CompactRoadGraph.from_networkx(graph),
    ):
        with pytest.raises(ValueError, match="geographic ranges"):
            compile_graph()


def test_compact_save_rejects_unsafe_vertex_objects(tmp_path):
    graph = nx.DiGraph()
    graph.add_node((1, 2), x=0, y=0)
    road = CompactRoadGraph.from_networkx(graph)
    with pytest.raises(TypeError, match="integers or strings"):
        road.save(tmp_path / "roads.npz")


def test_compact_coordinate_overflow_is_a_value_error(graph):
    road = CompactRoadGraph.from_networkx(graph)
    with pytest.raises(ValueError, match="pairs"):
        road.nearest_vertices([(10**400, 0)])

    graph.nodes["a"]["x"] = 10**400
    with pytest.raises(ValueError, match="numeric x and y"):
        CompactRoadGraph.from_networkx(graph)


def test_compact_api_is_public():
    assert {"CompactRoadGraph", "CompactStaticRoadAnalysis"} <= set(modo.__all__)
