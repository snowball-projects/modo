"""Compact exact static-road optimization."""

import json
from math import isfinite
from types import MappingProxyType

import networkx as nx
import numpy as np
from scipy.sparse import csr_array
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from .road import (
    RoadResult,
    RoadTravelTimes,
    _coordinate,
    _edge_weight,
    _tolerance,
    _vertex_key,
)

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
        for index, vertex in enumerate(vertices):
            coordinates[index] = _coordinate(graph, vertex)

        edge_count = graph.number_of_edges() * (1 if graph.is_directed() else 2)
        rows = np.empty(edge_count, dtype=np.int32)
        columns = np.empty(edge_count, dtype=np.int32)
        weights = np.empty(edge_count, dtype=np.float64)
        position = 0
        for start, end, data in graph.edges(data=True):
            value = _edge_weight(data, weight)
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
            data = np.array(archive["data"], dtype=np.float64)
            indices = _csr_indices(archive["indices"], "indices")
            indptr = _csr_indices(archive["indptr"], "indptr")
            directed = bool(archive["directed"])
        size = len(vertices)
        if not size:
            raise ValueError("invalid compact road graph vertices")
        if (coordinates.shape != (size, 2)
                or np.any(~np.isfinite(coordinates))
                or np.any(np.abs(coordinates[:, 0]) > 90)
                or np.any(np.abs(coordinates[:, 1]) > 180)):
            raise ValueError("invalid compact road graph coordinates")
        if (data.ndim != 1 or len(indices) != len(data)
                or len(indptr) != size + 1 or indptr[0] != 0
                or indptr[-1] != len(data)
                or np.any(indptr[1:] < indptr[:-1])
                or np.any(indices >= size)):
            raise ValueError("invalid compact road graph structure")
        matrix = csr_array((data, indices, indptr), shape=(size, size))
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
            self._tree = cKDTree(_vectors(self._coordinates))
        return tuple(self._vertices[index]
                     for index in self._tree.query(_vectors(points))[1])

    def analyze_vertices(self, origins, retain_distances=True):
        """Calculate reusable exact results for vertex origins."""
        return CompactStaticRoadAnalysis(self, origins, retain_distances)

    def analyze_coordinates(self, origins, retain_distances=True):
        """Snap coordinate origins and calculate reusable exact results."""
        return self.analyze_vertices(self.nearest_vertices(origins), retain_distances)


class CompactStaticRoadAnalysis:
    """Exact reusable compact-graph analysis."""

    def __init__(self, road, origins, retain_distances=True):
        origins = tuple(origins)
        if not origins:
            raise ValueError("origins must not be empty")
        if not isinstance(retain_distances, bool):
            raise TypeError("retain_distances must be a bool")
        try:
            origin_indices = [road._indices[origin] for origin in origins]
        except KeyError as error:
            raise nx.NodeNotFound(f"Node {error.args[0]} not found in graph") from error
        self._road = road
        self._origin_indices = np.array(origin_indices, dtype=np.int32)
        self.origin_vertices = origins
        self._distances = None
        self._scores = None
        if retain_distances:
            self._distances = np.atleast_2d(dijkstra(
                road._matrix, directed=road._directed, indices=origin_indices))
            self._reachable = np.all(np.isfinite(self._distances), axis=0)
        else:
            self._scores, self._reachable = _stream_scores(
                road._matrix, road._directed, origin_indices)
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
        if self._distances is None:
            matrix = self._road._matrix.T if self._road._directed else self._road._matrix
            values = dijkstra(matrix, directed=self._road._directed, indices=index)[
                self._origin_indices]
        else:
            values = self._distances[:, index]
        return RoadTravelTimes(
            vertex,
            self._road.coordinate(vertex),
            self.origin_vertices,
            tuple(map(float, values)),
        )

    def travel_times_at_coordinate(self, coordinate):
        """Snap one coordinate and return its per-origin travel times."""
        return self.travel_times(self._road.nearest_vertices([coordinate])[0])

    def optimize(self, objective="total", tolerance_seconds=0):
        """Optimize without recalculating the sparse shortest paths."""
        if objective not in {"total", "maximum"}:
            raise ValueError("objective must be 'total' or 'maximum'")
        tolerance_seconds = _tolerance(tolerance_seconds)

        reachable = np.flatnonzero(self._reachable)
        if self._distances is None:
            scores = self._scores[objective]
        else:
            with np.errstate(invalid="ignore", over="ignore"):
                scores = (_total_scores(self._distances) if objective == "total"
                          else np.max(self._distances, axis=0))
        if len(reachable) != len(scores):
            scores = scores[reachable]
        if np.any(~np.isfinite(scores)):
            raise ValueError("road objective scores must be finite")
        best_score = float(np.min(scores))
        tied_positions = np.flatnonzero(scores == best_score)
        best_position = min(tied_positions, key=lambda position: _vertex_key(
            self._road._vertices[reachable[position]], reachable[position]))
        region_positions = np.flatnonzero(scores - best_score <= tolerance_seconds)
        region_indices = reachable[region_positions]
        region = frozenset(self._road._vertices[index] for index in region_indices)
        excess = MappingProxyType({
            self._road._vertices[index]: float(scores[position] - best_score)
            for position, index in zip(region_positions, region_indices)
        })
        travel_times = self.travel_times(self._road._vertices[reachable[best_position]])
        return RoadResult(travel_times.vertex, travel_times.coordinate,
                          self.origin_vertices, region, best_score,
                          travel_times.travel_times_seconds, excess)


def _points(coordinates):
    try:
        points = tuple((float(latitude), float(longitude))
                       for latitude, longitude in coordinates)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError("coordinates must contain (latitude, longitude) pairs") from error
    if not points:
        raise ValueError("coordinates must not be empty")
    if any(not isfinite(latitude) or not isfinite(longitude)
           or abs(latitude) > 90 or abs(longitude) > 180
           for latitude, longitude in points):
        raise ValueError("coordinates are out of range")
    return points


def _vectors(coordinates):
    values = np.radians(np.asarray(coordinates, dtype=np.float64))
    latitude, longitude = values[:, 0], values[:, 1]
    latitude_cosine = np.cos(latitude)
    return np.column_stack((latitude_cosine * np.cos(longitude),
                            latitude_cosine * np.sin(longitude),
                            np.sin(latitude)))


def _total_scores(distances):
    scores = np.zeros(distances.shape[1], dtype=np.float64)
    correction = np.zeros(distances.shape[1], dtype=np.float64)
    for values in distances:
        adjusted = values - correction
        updated = scores + adjusted
        correction = (updated - scores) - adjusted
        scores = updated
    return scores


def _stream_scores(matrix, directed, origin_indices):
    size = matrix.shape[0]
    total = np.zeros(size, dtype=np.float64)
    correction = np.zeros(size, dtype=np.float64)
    maximum = np.zeros(size, dtype=np.float64)
    reachable = np.ones(size, dtype=np.bool_)
    for origin in origin_indices:
        values = dijkstra(matrix, directed=directed, indices=int(origin))
        finite = np.isfinite(values)
        reachable &= finite
        values[~finite] = 0
        with np.errstate(invalid="ignore", over="ignore"):
            adjusted = values - correction
            updated = total + adjusted
            correction = (updated - total) - adjusted
        total = updated
        np.maximum(maximum, values, out=maximum)
    return {"total": total, "maximum": maximum}, reachable


def _csr_indices(value, name):
    values = np.asarray(value)
    if (values.ndim != 1 or not np.issubdtype(values.dtype, np.integer)
            or np.any(values < 0)
            or np.any(values > np.iinfo(np.int32).max)):
        raise ValueError(f"invalid compact road graph {name}")
    converted = values.astype(np.int32)
    if not np.array_equal(values, converted):
        raise ValueError(f"invalid compact road graph {name}")
    return converted


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
