import networkx as nx
import pytest

import modo
from modo import nearest_vertices, optimize_coordinates, optimize_vertices


@pytest.fixture
def graph():
    graph = nx.DiGraph()
    graph.add_node("a", x=0, y=0)
    graph.add_node("b", x=10, y=0)
    graph.add_node("x", x=2, y=1)
    graph.add_node("y", x=3, y=1)
    graph.add_weighted_edges_from([
        ("a", "x", 1), ("b", "x", 9),
        ("a", "y", 5), ("b", "y", 6),
    ], weight="travel_time")
    return graph


def test_total_objective_and_average_tolerance(graph):
    result = optimize_vertices(graph, ["a", "b"], tolerance_seconds=1)
    assert result.vertex == "x"
    assert result.coordinate == (1.0, 2.0)
    assert result.origin_vertices == ("a", "b")
    assert result.objective_seconds == 10
    assert result.travel_times_seconds == (1, 9)
    assert result.region == {"x", "y"}


def test_maximum_objective_and_tolerance(graph):
    result = optimize_vertices(graph, ["a", "b"], "maximum", 3)
    assert result.vertex == "y"
    assert result.objective_seconds == 6
    assert result.travel_times_seconds == (5, 6)
    assert result.region == {"x", "y"}


@pytest.mark.parametrize("kwargs", [
    {"origins": []},
    {"origins": ["a"], "objective": "median"},
    {"origins": ["a"], "tolerance_seconds": -1},
    {"origins": ["a"], "tolerance_seconds": float("nan")},
])
def test_rejects_invalid_options(graph, kwargs):
    with pytest.raises(ValueError):
        optimize_vertices(graph, **kwargs)


def test_rejects_disconnected_origins():
    graph = nx.DiGraph()
    graph.add_nodes_from(["a", "b"])
    with pytest.raises(nx.NetworkXNoPath):
        optimize_vertices(graph, ["a", "b"])


def test_requires_coordinates_on_the_result_vertex():
    graph = nx.DiGraph()
    graph.add_node("a")
    with pytest.raises(ValueError, match="numeric x and y"):
        optimize_vertices(graph, ["a"])


def test_optimizes_from_coordinates(graph):
    result = optimize_coordinates(graph, [(0, 0.1), (0, 9.9)])
    assert result.origin_vertices == ("a", "b")
    assert result.vertex == "x"


def test_nearest_vertices_handles_the_dateline():
    graph = nx.Graph()
    graph.add_node("east", x=179, y=0)
    graph.add_node("west", x=-170, y=0)
    assert nearest_vertices(graph, [(0, -179.9)]) == ("east",)


@pytest.mark.parametrize("coordinates", [[], [(91, 0)], [(0, 181)], [(1, 2, 3)]])
def test_coordinate_optimizer_rejects_invalid_input(graph, coordinates):
    with pytest.raises(ValueError):
        optimize_coordinates(graph, coordinates)


def test_road_api_is_public():
    assert {"RoadResult", "nearest_vertices", "optimize_coordinates",
            "optimize_vertices"} <= set(modo.__all__)
