"""Compact exact static-road optimization."""

import json
from math import cos, isfinite, radians, sin
from types import MappingProxyType

import networkx as nx
import numpy as np
from scipy.sparse import csr_array
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from .road import RoadResult, RoadTravelTimes

_FORMAT_VERSION = 1


class CompactRoadGraph:
    """CSR road graph with coordinates and stable NetworkX vertex identities."""

    def __init__(self, vertices, coordinates, matrix, directed):
        self._vertices = vertices
        self._indices = {vertex: index for index, vertex in enumerate(vertices)}
        self._coordinates = coordinates
        self._matrix = matrix
        self._directed = directed
        self._tree = None

    @classmethod
    def from_networkx(cls, graph, weight="travel_time"):
        """Compile a NetworkX graph using minimum parallel-edge weights."""
        if weight is not None and not isinstance(weight, str):
            raise TypeError("weight must be an edge-attribute name or None")
        vertices = tuple(graph)
        if not vertices:
            raise ValueError("road graph must not be empty")
        indices = {vertex: index for index, vertex in enumerate(vertices)}
        coordinates = np.empty((len(vertices), 2), dtype=np.float64)
        try:
            for index, vertex in enumerate(vertices):
                coordinates[index] = float(graph.nodes[vertex]["y"]), float(
                    graph.nodes[vertex]["x"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("road vertices must have numeric x and y coordinates") from error

        edge_count = graph.number_of_edges() * (1 if graph.is_directed() else 2)
        rows = np.empty(edge_count, dtype=np.int64)
        columns = np.empty(edge_count, dtype=np.int64)
        weights = np.empty(edge_count, dtype=np.float64)
        position = 0
        for start, end, data in graph.edges(data=True):
            try:
                value = 1.0 if weight is None else float(data.get(weight, 1))
            except (TypeError, ValueError) as error:
                raise ValueError("road edge weights must be nonnegative numbers") from error
            if not isfinite(value) or value < 0:
                raise ValueError("road edge weights must be nonnegative numbers")
            rows[position], columns[position], weights[position] = (
                indices[start], indices[end], value)
            position += 1
            if not graph.is_directed():
                rows[position], columns[position], weights[position] = (
                    indices[end], indices[start], value)
                position += 1

        if edge_count:
            order = np.lexsort((columns, rows))
            rows, columns, weights = rows[order], columns[order], weights[order]
            starts = np.r_[0, np.flatnonzero(
                (rows[1:] != rows[:-1]) | (columns[1:] != columns[:-1])) + 1]
            weights = np.minimum.reduceat(weights, starts)
            rows, columns = rows[starts], columns[starts]
        matrix = csr_array((weights, (rows, columns)),
                           shape=(len(vertices), len(vertices)))
        return cls(vertices, coordinates, matrix, graph.is_directed())

    @classmethod
    def load(cls, path):
        """Load a versioned compact graph without unsafe object deserialization."""
        with np.load(path, allow_pickle=False) as archive:
            if int(archive["format_version"]) != _FORMAT_VERSION:
                raise ValueError("unsupported compact road graph format")
            vertices = _decode_vertices(archive["vertices"])
            coordinates = np.array(archive["coordinates"], dtype=np.float64)
            matrix = csr_array((np.array(archive["data"], dtype=np.float64),
                                np.array(archive["indices"]),
                                np.array(archive["indptr"])),
                               shape=(len(vertices), len(vertices)))
            directed = bool(archive["directed"])
        if coordinates.shape != (len(vertices), 2):
            raise ValueError("invalid compact road graph coordinates")
        if np.any(~np.isfinite(matrix.data)) or np.any(matrix.data < 0):
            raise ValueError("invalid compact road graph weights")
        return cls(vertices, coordinates, matrix, directed)

    def save(self, path):
        """Save a versioned compressed graph with integer or string vertex IDs."""
        vertices = _encode_vertices(self._vertices)
        with open(path, "wb") as output:
            np.savez_compressed(
                output,
                format_version=np.array(_FORMAT_VERSION, dtype=np.uint8),
                vertices=vertices,
                coordinates=self._coordinates,
                data=self._matrix.data,
                indices=self._matrix.indices,
                indptr=self._matrix.indptr,
                directed=np.array(self._directed, dtype=np.bool_),
            )

    def coordinate(self, vertex):
        """Return one vertex coordinate as ``(latitude, longitude)``."""
        try:
            return tuple(map(float, self._coordinates[self._indices[vertex]]))
        except KeyError as error:
            raise nx.NodeNotFound(f"Node {error.args[0]} not found in graph") from error

    def coordinates(self, vertices):
        """Return coordinates in the same order as the supplied vertices."""
        return tuple(self.coordinate(vertex) for vertex in vertices)

    def nearest_vertices(self, coordinates):
        """Snap coordinates to the nearest compact-graph vertices."""
        points = _points(coordinates)
        if self._tree is None:
            self._tree = cKDTree([_vector(*point) for point in self._coordinates])
        return tuple(self._vertices[index]
                     for index in self._tree.query([_vector(*point) for point in points])[1])

    def analyze_vertices(self, origins):
        """Calculate one reusable distance matrix for vertex origins."""
        return CompactStaticRoadAnalysis(self, origins)

    def analyze_coordinates(self, origins):
        """Snap coordinate origins and calculate one reusable distance matrix."""
        return self.analyze_vertices(self.nearest_vertices(origins))


class CompactStaticRoadAnalysis:
    """Exact reusable analysis backed by one dense distance matrix."""

    def __init__(self, road, origins):
        origins = tuple(origins)
        if not origins:
            raise ValueError("origins must not be empty")
        try:
            origin_indices = [road._indices[origin] for origin in origins]
        except KeyError as error:
            raise nx.NodeNotFound(f"Node {error.args[0]} not found in graph") from error
        self._road = road
        self.origin_vertices = origins
        self._distances = np.atleast_2d(dijkstra(
            road._matrix, directed=road._directed, indices=origin_indices))
        self._reachable = np.all(np.isfinite(self._distances), axis=0)
        if not np.any(self._reachable):
            raise nx.NetworkXNoPath("origins have no mutually reachable vertex")

    def travel_times(self, vertex):
        """Return per-origin travel times to a mutually reachable vertex."""
        try:
            index = self._road._indices[vertex]
        except KeyError as error:
            raise nx.NetworkXNoPath("vertex is not reachable from every origin") from error
        if not self._reachable[index]:
            raise nx.NetworkXNoPath("vertex is not reachable from every origin")
        return RoadTravelTimes(
            vertex,
            self._road.coordinate(vertex),
            self.origin_vertices,
            tuple(map(float, self._distances[:, index])),
        )

    def travel_times_at_coordinate(self, coordinate):
        """Snap one coordinate and return its per-origin travel times."""
        return self.travel_times(self._road.nearest_vertices([coordinate])[0])

    def optimize(self, objective="total", tolerance_seconds=0):
        """Optimize without recalculating the sparse shortest paths."""
        if objective not in {"total", "maximum"}:
            raise ValueError("objective must be 'total' or 'maximum'")
        try:
            tolerance_seconds = float(tolerance_seconds)
        except (TypeError, ValueError) as error:
            raise ValueError("tolerance_seconds must be a nonnegative number") from error
        if not isfinite(tolerance_seconds) or tolerance_seconds < 0:
            raise ValueError("tolerance_seconds must be a nonnegative number")

        scores = (np.sum(self._distances, axis=0) if objective == "total"
                  else np.max(self._distances, axis=0))
        best_score = float(np.min(scores[self._reachable]))
        candidates = np.flatnonzero(self._reachable & (scores == best_score))
        best_index = min(candidates, key=lambda index: str(self._road._vertices[index]))
        region_indices = np.flatnonzero(
            self._reachable & (scores <= best_score + tolerance_seconds))
        region = frozenset(self._road._vertices[index] for index in region_indices)
        excess = MappingProxyType({
            self._road._vertices[index]: float(scores[index] - best_score)
            for index in region_indices
        })
        travel_times = self.travel_times(self._road._vertices[best_index])
        return RoadResult(travel_times.vertex, travel_times.coordinate,
                          self.origin_vertices, region, best_score,
                          travel_times.travel_times_seconds, excess)


def _points(coordinates):
    try:
        points = tuple((float(latitude), float(longitude))
                       for latitude, longitude in coordinates)
    except (TypeError, ValueError) as error:
        raise ValueError("coordinates must contain (latitude, longitude) pairs") from error
    if not points:
        raise ValueError("coordinates must not be empty")
    if any(not isfinite(latitude) or not isfinite(longitude)
           or abs(latitude) > 90 or abs(longitude) > 180
           for latitude, longitude in points):
        raise ValueError("coordinates are out of range")
    return points


def _vector(latitude, longitude):
    latitude, longitude = radians(latitude), radians(longitude)
    return (cos(latitude) * cos(longitude), cos(latitude) * sin(longitude),
            sin(latitude))


def _encode_vertices(vertices):
    encoded = []
    for vertex in vertices:
        if isinstance(vertex, str):
            encoded.append(["string", vertex])
        elif isinstance(vertex, (int, np.integer)) and not isinstance(vertex, bool):
            encoded.append(["integer", str(vertex)])
        else:
            raise TypeError("saved compact graph vertex IDs must be integers or strings")
    return np.frombuffer(json.dumps(encoded, separators=(",", ":")).encode(),
                         dtype=np.uint8)


def _decode_vertices(value):
    try:
        encoded = json.loads(value.tobytes().decode())
        vertices = []
        for item in encoded:
            if not isinstance(item, list) or len(item) != 2 or not isinstance(item[1], str):
                raise ValueError
            if item[0] == "string":
                vertices.append(item[1])
            elif item[0] == "integer":
                vertices.append(int(item[1]))
            else:
                raise ValueError
        vertices = tuple(vertices)
    except (IndexError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid compact road graph vertices") from error
    if len(vertices) != len(set(vertices)):
        raise ValueError("invalid compact road graph vertices")
    return vertices
