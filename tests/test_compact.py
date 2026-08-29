import networkx as nx
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


def test_compact_undirected_and_missing_weights_match_networkx():
    graph = nx.Graph()
    graph.add_node(2, x=2, y=0)
    graph.add_node(1, x=1, y=0)
    graph.add_edge(1, 2)
    expected = analyze_vertices(graph, [2]).optimize()
    result = CompactRoadGraph.from_networkx(graph).analyze_vertices([2]).optimize()
    assert result == expected


@pytest.mark.parametrize("weight", [-1, float("nan"), "slow"])
def test_compact_rejects_invalid_weights(weight):
    graph = nx.DiGraph()
    graph.add_node("a", x=0, y=0)
    graph.add_node("b", x=1, y=0)
    graph.add_edge("a", "b", travel_time=weight)
    with pytest.raises(ValueError, match="nonnegative"):
        CompactRoadGraph.from_networkx(graph)


def test_compact_graph_round_trip_and_coordinates(graph, tmp_path):
    expected = CompactRoadGraph.from_networkx(graph)
    path = tmp_path / "roads.npz"
    expected.save(path)
    duplicate = tmp_path / "duplicate.npz"
    expected.save(duplicate)
    assert path.read_bytes() == duplicate.read_bytes()
    actual = CompactRoadGraph.load(path)
    assert actual.coordinate("x") == (1.0, 2.0)
    assert actual.coordinates(["y", "x"]) == ((1.0, 3.0), (1.0, 2.0))
    assert actual.analyze_vertices(["a", "b"]).optimize(
        "maximum", 3) == expected.analyze_vertices(["a", "b"]).optimize("maximum", 3)


def test_compact_save_rejects_unsafe_vertex_objects(tmp_path):
    graph = nx.DiGraph()
    graph.add_node((1, 2), x=0, y=0)
    road = CompactRoadGraph.from_networkx(graph)
    with pytest.raises(TypeError, match="integers or strings"):
        road.save(tmp_path / "roads.npz")


def test_compact_api_is_public():
    assert {"CompactRoadGraph", "CompactStaticRoadAnalysis"} <= set(modo.__all__)
