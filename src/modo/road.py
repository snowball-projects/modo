"""Exact static-road reference optimization."""

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from math import cos, isfinite, radians, sin
from types import MappingProxyType

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
    region_excess_seconds: Mapping[Hashable, float]


@dataclass(frozen=True)
class RoadTravelTimes:
    vertex: Hashable
    coordinate: tuple[float, float]
    origin_vertices: tuple[Hashable, ...]
    travel_times_seconds: tuple[float, ...]


class StaticRoadAnalysis:
    """Reusable shortest-path analysis for one graph and origin set."""

    def __init__(self, graph, origins, weight="travel_time"):
        origins = tuple(origins)
        if not origins:
            raise ValueError("origins must not be empty")
        self._graph = graph
        self.origin_vertices = origins
        self._times = tuple(nx.single_source_dijkstra_path_length(
            graph, origin, weight=weight) for origin in origins)
        self._vertices = frozenset.intersection(
            *(frozenset(values) for values in self._times))
        if not self._vertices:
            raise nx.NetworkXNoPath("origins have no mutually reachable vertex")

    def travel_times(self, vertex):
        """Return per-origin travel times to a mutually reachable vertex."""
        if vertex not in self._vertices:
            raise nx.NetworkXNoPath("vertex is not reachable from every origin")
        return RoadTravelTimes(vertex, _coordinate(self._graph, vertex),
                               self.origin_vertices,
                               tuple(float(values[vertex]) for values in self._times))

    def travel_times_at_coordinate(self, coordinate):
        """Snap one coordinate and return its per-origin travel times."""
        return self.travel_times(nearest_vertices(self._graph, [coordinate])[0])

    def optimize(self, objective="total", tolerance_seconds=0):
        """Optimize without repeating the shortest-path searches."""
        if objective not in {"total", "maximum"}:
            raise ValueError("objective must be 'total' or 'maximum'")
        try:
            tolerance_seconds = float(tolerance_seconds)
        except (TypeError, ValueError) as error:
            raise ValueError("tolerance_seconds must be a nonnegative number") from error
        if not isfinite(tolerance_seconds) or tolerance_seconds < 0:
            raise ValueError("tolerance_seconds must be a nonnegative number")

        score = sum if objective == "total" else max
        scores = {vertex: score(values[vertex] for values in self._times)
                  for vertex in self._vertices}
        vertex = min(self._vertices, key=lambda item: (scores[item], str(item)))
        region = frozenset(item for item in self._vertices
                           if scores[item] <= scores[vertex] + tolerance_seconds)
        excess = MappingProxyType({
            item: float(scores[item] - scores[vertex]) for item in region
        })
        travel_times = self.travel_times(vertex)
        return RoadResult(vertex, travel_times.coordinate, self.origin_vertices, region,
                          float(scores[vertex]), travel_times.travel_times_seconds,
                          excess)


def _coordinate(graph, vertex):
    data = graph.nodes[vertex]
    try:
        return float(data["y"]), float(data["x"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("road vertices must have numeric x and y coordinates") from error


def analyze_vertices(graph, origins, weight="travel_time"):
    """Prepare reusable static-road calculations for vertex origins."""
    return StaticRoadAnalysis(graph, origins, weight)


def optimize_vertices(graph, origins, objective="total", tolerance_seconds=0,
                      weight="travel_time"):
    """Optimize mutually reachable vertices in a static weighted road graph."""
    return analyze_vertices(graph, origins, weight).optimize(objective, tolerance_seconds)


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
    return analyze_coordinates(graph, origins, weight).optimize(objective, tolerance_seconds)


def analyze_coordinates(graph, origins, weight="travel_time"):
    """Snap coordinate origins and prepare reusable static-road calculations."""
    return analyze_vertices(graph, nearest_vertices(graph, origins), weight)
