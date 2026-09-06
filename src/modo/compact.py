"""Compact exact static-road optimization."""

import heapq
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
    RoadRoute,
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
                indices[start],
                indices[end],
                value,
            )
            position += 1
            if not graph.is_directed():
                rows[position], columns[position], weights[position] = (
                    indices[end],
                    indices[start],
                    value,
                )
                position += 1

        if edge_count:
            order = np.lexsort((columns, rows))
            rows, columns, weights = rows[order], columns[order], weights[order]
            starts = np.r_[
                0,
                np.flatnonzero((rows[1:] != rows[:-1]) | (columns[1:] != columns[:-1]))
                + 1,
            ]
            weights = np.minimum.reduceat(weights, starts)
            rows, columns = rows[starts], columns[starts]
        matrix = csr_array(
            (weights, (rows, columns)), shape=(len(vertices), len(vertices))
        )
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
        if (
            coordinates.shape != (size, 2)
            or np.any(~np.isfinite(coordinates))
            or np.any(np.abs(coordinates[:, 0]) > 90)
            or np.any(np.abs(coordinates[:, 1]) > 180)
        ):
            raise ValueError("invalid compact road graph coordinates")
        if (
            data.ndim != 1
            or len(indices) != len(data)
            or len(indptr) != size + 1
            or indptr[0] != 0
            or indptr[-1] != len(data)
            or np.any(indptr[1:] < indptr[:-1])
            or np.any(indices >= size)
        ):
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

    def validate_snapshot(self, graph_bounds=None):
        """Validate stricter invariants required by hosted road snapshots."""
        if not self._directed:
            raise ValueError("production road snapshots must be directed")
        if not self._matrix.nnz or np.any(self._matrix.data <= 0):
            raise ValueError("production road snapshot weights must be positive")
        if graph_bounds is not None:
            bounds = np.asarray(graph_bounds, dtype=np.float64)
            latitude, longitude = self._coordinates.T
            actual = np.array(
                [latitude.min(), longitude.min(), latitude.max(), longitude.max()]
            )
            if bounds.shape != (4,) or not np.allclose(
                bounds, actual, rtol=0, atol=1e-7
            ):
                raise ValueError("production road snapshot bounds do not match")
        return self

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
        return tuple(
            self._vertices[index] for index in self._tree.query(_vectors(points))[1]
        )

    def analyze_vertices(self, origins, retain_distances=True, *, objective=None):
        """Calculate reusable exact results for vertex origins."""
        return CompactStaticRoadAnalysis(self, origins, retain_distances, objective)

    def analyze_coordinates(self, origins, retain_distances=True, *, objective=None):
        """Snap coordinate origins and calculate reusable exact results."""
        return self.analyze_vertices(
            self.nearest_vertices(origins), retain_distances, objective=objective
        )

    def _bounded_maximum_result(
        self, origins, tolerance_seconds, max_region_vertices, label_budget
    ):
        origins, origin_indices = _origin_indices(self, origins)
        return _bounded_maximum_result(
            self,
            origins,
            origin_indices,
            _tolerance(tolerance_seconds),
            _positive_limit(max_region_vertices, "max_region_vertices"),
            _positive_limit(label_budget, "label_budget"),
        )

    def _bounded_maximum_result_and_routes(
        self, origins, tolerance_seconds, max_region_vertices, label_budget
    ):
        origins, origin_indices = _origin_indices(self, origins)
        return _bounded_maximum_result(
            self,
            origins,
            origin_indices,
            _tolerance(tolerance_seconds),
            _positive_limit(max_region_vertices, "max_region_vertices"),
            _positive_limit(label_budget, "label_budget"),
            include_routes=True,
        )

    def _routes_from_vertices(self, origins, vertex, max_points=None):
        origins, origin_indices = _origin_indices(self, origins)
        try:
            destination = self._indices[vertex]
        except KeyError as error:
            raise nx.NetworkXNoPath(
                "vertex is not reachable from every origin"
            ) from error
        return _routes(
            self,
            origin_indices,
            destination,
            _positive_limit(max_points, "max_points"),
        )


class CompactStaticRoadAnalysis:
    """Exact reusable compact-graph analysis."""

    def __init__(self, road, origins, retain_distances=True, objective=None):
        origins = tuple(origins)
        if not origins:
            raise ValueError("origins must not be empty")
        if not isinstance(retain_distances, bool):
            raise TypeError("retain_distances must be a bool")
        if objective not in {None, "total", "maximum"}:
            raise ValueError("objective must be 'total', 'maximum', or None")
        try:
            origin_indices = [road._indices[origin] for origin in origins]
        except KeyError as error:
            raise nx.NodeNotFound(f"Node {error.args[0]} not found in graph") from error
        self._road = road
        self._origin_indices = np.array(origin_indices, dtype=np.int32)
        self.origin_vertices = origins
        self._distances = None
        self._scores = None
        self._objective = objective if not retain_distances else None
        if retain_distances:
            self._distances = np.atleast_2d(
                dijkstra(road._matrix, directed=road._directed, indices=origin_indices)
            )
            self._reachable = np.all(np.isfinite(self._distances), axis=0)
        else:
            self._scores, self._reachable = _stream_scores(
                road._matrix, road._directed, origin_indices, objective
            )
        if not np.any(self._reachable):
            raise nx.NetworkXNoPath("origins have no mutually reachable vertex")

    def travel_times(self, vertex):
        """Return per-origin travel times to a mutually reachable vertex."""
        try:
            index = self._road._indices[vertex]
        except KeyError as error:
            raise nx.NetworkXNoPath(
                "vertex is not reachable from every origin"
            ) from error
        if not self._reachable[index]:
            raise nx.NetworkXNoPath("vertex is not reachable from every origin")
        if self._distances is None:
            matrix = (
                self._road._matrix.T if self._road._directed else self._road._matrix
            )
            values = dijkstra(matrix, directed=self._road._directed, indices=index)[
                self._origin_indices
            ]
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

    def routes(self, vertex, *, max_points=None):
        """Return one shortest road-vertex path per origin to a vertex."""
        try:
            destination = self._road._indices[vertex]
        except KeyError as error:
            raise nx.NetworkXNoPath(
                "vertex is not reachable from every origin"
            ) from error
        if not self._reachable[destination]:
            raise nx.NetworkXNoPath("vertex is not reachable from every origin")
        return _routes(
            self._road,
            self._origin_indices,
            destination,
            _positive_limit(max_points, "max_points"),
        )

    def optimize(
        self, objective="total", tolerance_seconds=0, *, max_region_vertices=None
    ):
        """Optimize without recalculating the sparse shortest paths."""
        if objective not in {"total", "maximum"}:
            raise ValueError("objective must be 'total' or 'maximum'")
        tolerance_seconds = _tolerance(tolerance_seconds)
        max_region_vertices = _positive_limit(
            max_region_vertices, "max_region_vertices"
        )
        if self._objective is not None and objective != self._objective:
            raise ValueError(f"{objective} objective was not calculated")

        if self._distances is None:
            scores = self._scores[objective]
        else:
            with np.errstate(invalid="ignore", over="ignore"):
                scores = (
                    _total_scores(self._distances)
                    if objective == "total"
                    else np.max(self._distances, axis=0)
                )
        finite = np.ones_like(self._reachable)
        np.isfinite(scores, out=finite, where=self._reachable)
        if not np.all(finite):
            raise ValueError("road objective scores must be finite")
        best_score = float(np.min(scores, where=self._reachable, initial=float("inf")))
        tied_indices = np.flatnonzero(self._reachable & (scores == best_score))
        best_index = min(
            tied_indices,
            key=lambda index: _vertex_key(self._road._vertices[index], index),
        )
        qualifies = self._reachable & (scores - best_score <= tolerance_seconds)
        if (
            max_region_vertices is not None
            and np.count_nonzero(qualifies) > max_region_vertices
        ):
            raise _ResultLimitExceeded("road result region exceeds max_region_vertices")
        region_indices = np.flatnonzero(qualifies)
        region = frozenset(self._road._vertices[index] for index in region_indices)
        excess = MappingProxyType(
            {
                self._road._vertices[index]: float(scores[index] - best_score)
                for index in region_indices
            }
        )
        travel_times = self.travel_times(self._road._vertices[best_index])
        return RoadResult(
            travel_times.vertex,
            travel_times.coordinate,
            self.origin_vertices,
            region,
            best_score,
            travel_times.travel_times_seconds,
            excess,
        )


def _points(coordinates):
    try:
        points = tuple(
            (float(latitude), float(longitude)) for latitude, longitude in coordinates
        )
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError(
            "coordinates must contain (latitude, longitude) pairs"
        ) from error
    if not points:
        raise ValueError("coordinates must not be empty")
    if any(
        not isfinite(latitude)
        or not isfinite(longitude)
        or abs(latitude) > 90
        or abs(longitude) > 180
        for latitude, longitude in points
    ):
        raise ValueError("coordinates are out of range")
    return points


def _vectors(coordinates):
    values = np.radians(np.asarray(coordinates, dtype=np.float64))
    latitude, longitude = values[:, 0], values[:, 1]
    latitude_cosine = np.cos(latitude)
    return np.column_stack(
        (
            latitude_cosine * np.cos(longitude),
            latitude_cosine * np.sin(longitude),
            np.sin(latitude),
        )
    )


def _total_scores(distances):
    scores = np.zeros(distances.shape[1], dtype=np.float64)
    correction = np.zeros(distances.shape[1], dtype=np.float64)
    for values in distances:
        adjusted = values - correction
        updated = scores + adjusted
        correction = (updated - scores) - adjusted
        scores = updated
    return scores


def _stream_scores(matrix, directed, origin_indices, objective=None):
    size = matrix.shape[0]
    total = correction = maximum = None
    if objective in {None, "total"}:
        total = np.zeros(size, dtype=np.float64)
        correction = np.zeros(size, dtype=np.float64)
    if objective in {None, "maximum"}:
        maximum = np.zeros(size, dtype=np.float64)
    reachable = np.ones(size, dtype=np.bool_)
    for origin in origin_indices:
        values = dijkstra(matrix, directed=directed, indices=int(origin))
        finite = np.isfinite(values)
        reachable &= finite
        values[~finite] = 0
        if total is not None:
            with np.errstate(invalid="ignore", over="ignore"):
                adjusted = values - correction
                updated = total + adjusted
                correction = (updated - total) - adjusted
            total = updated
        if maximum is not None:
            np.maximum(maximum, values, out=maximum)
    return {
        name: values
        for name, values in (("total", total), ("maximum", maximum))
        if values is not None
    }, reachable


def _origin_indices(road, origins):
    origins = tuple(origins)
    if not origins:
        raise ValueError("origins must not be empty")
    try:
        indices = np.array(
            [road._indices[origin] for origin in origins], dtype=np.int32
        )
    except KeyError as error:
        raise nx.NodeNotFound(f"Node {error.args[0]} not found in graph") from error
    return origins, indices


def _bounded_maximum_result(
    road,
    origins,
    origin_indices,
    tolerance,
    max_region_vertices,
    label_budget,
    include_routes=False,
):
    if len(origin_indices) > label_budget:
        return None
    full_mask = (1 << len(origin_indices)) - 1
    distances = [{int(origin): 0.0} for origin in origin_indices]
    predecessors = [{} for _origin in origin_indices] if include_routes else None
    heap = [(0.0, number, int(origin)) for number, origin in enumerate(origin_indices)]
    heapq.heapify(heap)
    masks = {}
    maxima = {}
    region_scores = {}
    optimum = None
    discovered = pushes = len(origin_indices)
    data, indices, indptr = (
        road._matrix.data,
        road._matrix.indices,
        road._matrix.indptr,
    )
    while heap:
        distance, origin_number, vertex = heapq.heappop(heap)
        if optimum is not None and distance - optimum > tolerance:
            break
        if distance != distances[origin_number].get(vertex):
            continue
        mask = masks.get(vertex, 0) | (1 << origin_number)
        masks[vertex] = mask
        maxima[vertex] = max(maxima.get(vertex, 0.0), distance)
        if mask == full_mask:
            optimum = distance if optimum is None else optimum
            region_scores[vertex] = maxima[vertex]
            if (
                max_region_vertices is not None
                and len(region_scores) > max_region_vertices
            ):
                raise _ResultLimitExceeded(
                    "road result region exceeds max_region_vertices"
                )
        start, end = indptr[vertex], indptr[vertex + 1]
        for position in range(start, end):
            neighbor = int(indices[position])
            candidate = distance + float(data[position])
            if optimum is not None and candidate - optimum > tolerance:
                continue
            previous = distances[origin_number].get(neighbor)
            if previous is None or candidate < previous:
                if previous is None:
                    if discovered >= label_budget:
                        return None
                    discovered += 1
                pushes += 1
                if pushes > label_budget * 4:
                    return None
                distances[origin_number][neighbor] = candidate
                if predecessors is not None:
                    predecessors[origin_number][neighbor] = vertex
                heapq.heappush(heap, (candidate, origin_number, neighbor))
    if optimum is None:
        raise nx.NetworkXNoPath("origins have no mutually reachable vertex")
    tied = (vertex for vertex, score in region_scores.items() if score == optimum)
    best_index = min(tied, key=lambda index: _vertex_key(road._vertices[index], index))
    region = frozenset(road._vertices[index] for index in region_scores)
    excess = MappingProxyType(
        {
            road._vertices[index]: float(score - optimum)
            for index, score in region_scores.items()
        }
    )
    values = tuple(
        distances[origin_number][best_index]
        for origin_number in range(len(origin_indices))
    )
    vertex = road._vertices[best_index]
    result = RoadResult(
        vertex,
        road.coordinate(vertex),
        origins,
        region,
        float(optimum),
        tuple(map(float, values)),
        excess,
    )
    if predecessors is None:
        return result
    return result, _routes_from_predecessors(
        road, origin_indices, best_index, distances, predecessors
    )


def _routes_from_predecessors(
    road, origin_indices, destination, distances, predecessors
):
    routes = []
    for origin_number, origin in enumerate(origin_indices):
        indices = [destination]
        while indices[-1] != origin:
            try:
                indices.append(predecessors[origin_number][indices[-1]])
            except KeyError as error:
                raise nx.NetworkXNoPath(
                    "vertex is not reachable from every origin"
                ) from error
            if len(indices) > len(road._vertices):
                raise nx.NetworkXNoPath("vertex is not reachable from every origin")
        indices.reverse()
        vertices = tuple(road._vertices[index] for index in indices)
        routes.append(
            RoadRoute(
                vertices[0],
                road._vertices[destination],
                vertices,
                road.coordinates(vertices),
                float(distances[origin_number][destination]),
            )
        )
    return tuple(routes)


def _routes(road, origin_indices, destination, max_points):
    matrix = road._matrix.T if road._directed else road._matrix
    distances, predecessors = dijkstra(
        matrix,
        directed=road._directed,
        indices=destination,
        return_predecessors=True,
    )
    routes = []
    point_count = 0
    for origin in origin_indices:
        indices = [int(origin)]
        if max_points is not None and point_count + 1 > max_points:
            raise _ResultLimitExceeded("road routes exceed max_points")
        while indices[-1] != destination:
            predecessor = int(predecessors[indices[-1]])
            if predecessor < 0 or len(indices) > len(road._vertices):
                raise nx.NetworkXNoPath("vertex is not reachable from every origin")
            indices.append(predecessor)
            if max_points is not None and point_count + len(indices) > max_points:
                raise _ResultLimitExceeded("road routes exceed max_points")
        point_count += len(indices)
        vertices = tuple(road._vertices[index] for index in indices)
        routes.append(
            RoadRoute(
                vertices[0],
                road._vertices[destination],
                vertices,
                road.coordinates(vertices),
                float(distances[origin]),
            )
        )
    return tuple(routes)


class _ResultLimitExceeded(ValueError):
    """A bounded calculation exceeded its configured response limit."""


def _positive_limit(value, name):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
        raise ValueError(f"{name} must be a positive integer or None")
    return int(value)


def _csr_indices(value, name):
    values = np.asarray(value)
    if (
        values.ndim != 1
        or not np.issubdtype(values.dtype, np.integer)
        or np.any(values < 0)
        or np.any(values > np.iinfo(np.int32).max)
    ):
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
            raise TypeError(
                "saved compact graph vertex IDs must be integers or strings"
            )
    return np.frombuffer(
        json.dumps(encoded, separators=(",", ":")).encode(), dtype=np.uint8
    )


def _decode_vertices(value):
    try:
        encoded = json.loads(value.tobytes().decode())
        vertices = []
        for item in encoded:
            if (
                not isinstance(item, list)
                or len(item) != 2
                or not isinstance(item[1], str)
            ):
                raise ValueError
            if item[0] == "string":
                vertices.append(item[1])
            elif item[0] == "integer":
                vertices.append(int(item[1]))
            else:
                raise ValueError
        vertices = tuple(vertices)
    except (
        IndexError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError("invalid compact road graph vertices") from error
    if len(vertices) != len(set(vertices)):
        raise ValueError("invalid compact road graph vertices")
    return vertices
