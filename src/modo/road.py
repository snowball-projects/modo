"""Exact static-road reference optimization."""

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from math import cos, isfinite, radians, sin
from numbers import Number
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


@dataclass(frozen=True)
class RoadRoute:
    origin_vertex: Hashable
    destination_vertex: Hashable
    vertices: tuple[Hashable, ...]
    coordinates: tuple[tuple[float, float], ...]
    travel_time_seconds: float


class StaticRoadAnalysis:
    """Reusable shortest-path analysis for one graph and origin set."""

    def __init__(self, graph, origins, weight="travel_time"):
        origins = tuple(origins)
        if not origins:
            raise ValueError("origins must not be empty")
        _validate_weights(graph, weight)
        self._graph = graph
        self._order = {vertex: index for index, vertex in enumerate(graph)}
        for vertex in graph:
            _coordinate(graph, vertex)
        self.origin_vertices = origins
        normalized_weight = _networkx_weight(graph, weight)
        self._weight = normalized_weight
        self._times = tuple(nx.single_source_dijkstra_path_length(
            graph, origin, weight=normalized_weight) for origin in origins)
        self._vertices = frozenset.intersection(
            *(frozenset(values) for values in self._times))
        self._vertices = frozenset(vertex for vertex in self._vertices
                                   if all(isfinite(float(values[vertex]))
                                          for values in self._times))
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

    def routes(self, vertex):
        """Return one shortest road-vertex path per origin to a vertex."""
        travel_times = self.travel_times(vertex).travel_times_seconds
        routes = []
        for origin, travel_time in zip(
                self.origin_vertices, travel_times, strict=True):
            vertices = tuple(nx.shortest_path(
                self._graph, origin, vertex, weight=self._weight))
            routes.append(RoadRoute(
                origin,
                vertex,
                vertices,
                tuple(_coordinate(self._graph, item) for item in vertices),
                travel_time,
            ))
        return tuple(routes)

    def optimize(self, objective="total", tolerance_seconds=0):
        """Optimize without repeating the shortest-path searches."""
        if objective not in {"total", "maximum"}:
            raise ValueError("objective must be 'total' or 'maximum'")
        tolerance_seconds = _tolerance(tolerance_seconds)

        score = _total if objective == "total" else max
        scores = {vertex: score(values[vertex] for values in self._times)
                  for vertex in self._vertices}
        if not all(isfinite(value) for value in scores.values()):
            raise ValueError("road objective scores must be finite")
        vertex = min(self._vertices, key=lambda item: (
            scores[item], _vertex_key(item, self._order[item])))
        region = frozenset(item for item in self._vertices
                           if scores[item] - scores[vertex] <= tolerance_seconds)
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
        latitude, longitude = float(data["y"]), float(data["x"])
    except (KeyError, OverflowError, TypeError, ValueError) as error:
        raise ValueError(
            "road vertices must have numeric x and y coordinates in geographic ranges"
        ) from error
    if (not isfinite(latitude) or not isfinite(longitude)
            or abs(latitude) > 90 or abs(longitude) > 180):
        raise ValueError(
            "road vertices must have numeric x and y coordinates in geographic ranges")
    return latitude, longitude


def _edge_weight(data, weight):
    try:
        value = 1.0 if weight is None else float(data.get(weight, 1))
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError("road edge weights must be nonnegative numbers") from error
    if not isfinite(value) or value < 0:
        raise ValueError("road edge weights must be nonnegative numbers")
    return value


def _validate_weights(graph, weight):
    if weight is not None and not isinstance(weight, str):
        raise TypeError("weight must be an edge-attribute name or None")
    for _, _, data in graph.edges(data=True):
        _edge_weight(data, weight)


def _networkx_weight(graph, weight):
    if weight is None:
        return None
    if graph.is_multigraph():
        return lambda start, end, data: min(
            _edge_weight(attributes, weight) for attributes in data.values())
    return lambda start, end, data: _edge_weight(data, weight)


def _tolerance(value):
    try:
        value = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError("tolerance_seconds must be a nonnegative number") from error
    if not isfinite(value) or value < 0:
        raise ValueError("tolerance_seconds must be a nonnegative number")
    return value


def _total(values):
    total = correction = 0.0
    for value in values:
        adjusted = float(value) - correction
        updated = total + adjusted
        correction = (updated - total) - adjusted
        total = updated
    return total


def _vertex_key(vertex, position):
    kind = type(vertex)
    label = str(vertex) if isinstance(vertex, (Number, str, bytes)) else ""
    return label, kind.__module__, kind.__qualname__, position


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
    except (OverflowError, TypeError, ValueError) as error:
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

    tree = cKDTree([vector(*_coordinate(graph, node)) for node in vertices])
    return tuple(vertices[index] for index in tree.query([vector(*point) for point in points])[1])


def optimize_coordinates(graph, origins, objective="total", tolerance_seconds=0,
                         weight="travel_time"):
    """Snap origin coordinates to vertices and optimize the static road graph."""
    return analyze_coordinates(graph, origins, weight).optimize(objective, tolerance_seconds)


def analyze_coordinates(graph, origins, weight="travel_time"):
    """Snap coordinate origins and prepare reusable static-road calculations."""
    return analyze_vertices(graph, nearest_vertices(graph, origins), weight)
