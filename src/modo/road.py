"""Exact static-road reference optimization."""

from collections.abc import Hashable
from dataclasses import dataclass
from math import cos, isfinite, radians, sin

import networkx as nx
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class RoadResult:
    vertex: Hashable
    coordinate: tuple[float, float]
    origin_vertices: tuple[Hashable, ...]
    region: frozenset[Hashable]
    objective_seconds: float
    travel_times_seconds: tuple[float, ...]


def optimize_vertices(graph, origins, objective="total", tolerance_seconds=0,
                      weight="travel_time"):
    """Optimize mutually reachable vertices in a static weighted road graph.

    Total-objective tolerance is per-origin average slack. Maximum-objective
    tolerance is direct slack on the longest trip.
    """
    origins = tuple(origins)
    if not origins:
        raise ValueError("origins must not be empty")
    if objective not in {"total", "maximum"}:
        raise ValueError("objective must be 'total' or 'maximum'")
    try:
        tolerance_seconds = float(tolerance_seconds)
    except (TypeError, ValueError) as error:
        raise ValueError("tolerance_seconds must be a nonnegative number") from error
    if not isfinite(tolerance_seconds) or tolerance_seconds < 0:
        raise ValueError("tolerance_seconds must be a nonnegative number")

    times = [nx.single_source_dijkstra_path_length(graph, origin, weight=weight)
             for origin in origins]
    vertices = set.intersection(*(set(values) for values in times))
    if not vertices:
        raise nx.NetworkXNoPath("origins have no mutually reachable vertex")
    score = sum if objective == "total" else max
    scores = {vertex: score(values[vertex] for values in times) for vertex in vertices}
    vertex = min(vertices, key=lambda item: (scores[item], str(item)))
    slack = tolerance_seconds * (len(origins) if objective == "total" else 1)
    region = frozenset(item for item in vertices
                       if scores[item] <= scores[vertex] + slack)
    data = graph.nodes[vertex]
    try:
        coordinate = float(data["y"]), float(data["x"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("road vertices must have numeric x and y coordinates") from error
    return RoadResult(vertex, coordinate, origins, region, float(scores[vertex]),
                      tuple(float(values[vertex]) for values in times))


def nearest_vertices(graph, coordinates):
    """Snap coordinates to nearest graph vertices on a unit sphere."""
    try:
        points = tuple((float(lat), float(lon)) for lat, lon in coordinates)
    except (TypeError, ValueError) as error:
        raise ValueError("coordinates must contain (latitude, longitude) pairs") from error
    if not points:
        raise ValueError("coordinates must not be empty")
    if any(not isfinite(lat) or not isfinite(lon) or abs(lat) > 90 or abs(lon) > 180
           for lat, lon in points):
        raise ValueError("coordinates are out of range")
    vertices = tuple(graph)
    if not vertices:
        raise ValueError("road graph must not be empty")

    def vector(lat, lon):
        lat, lon = radians(lat), radians(lon)
        return cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat)

    try:
        tree = cKDTree([vector(float(graph.nodes[node]["y"]),
                                  float(graph.nodes[node]["x"])) for node in vertices])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("road vertices must have numeric x and y coordinates") from error
    return tuple(vertices[index] for index in tree.query([vector(*point) for point in points])[1])


def optimize_coordinates(graph, origins, objective="total", tolerance_seconds=0,
                         weight="travel_time"):
    """Snap origin coordinates to vertices and optimize the static road graph."""
    return optimize_vertices(graph, nearest_vertices(graph, origins), objective,
                             tolerance_seconds, weight)
