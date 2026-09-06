"""Deterministic time-dependent minimax routing experiment."""

import heapq
import json
from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

import networkx as nx

from modo import CompactRoadGraph


@dataclass(frozen=True)
class FifoProfile:
    """Piecewise-linear edge travel times with FIFO arrival behavior."""

    points: tuple[tuple[float, float], ...]

    def __post_init__(self):
        if not self.points:
            raise ValueError("a profile needs at least one point")
        previous_departure = previous_arrival = None
        for departure, travel in self.points:
            if not isfinite(departure) or not isfinite(travel) or travel < 0:
                raise ValueError("profile values must be finite and nonnegative")
            arrival = departure + travel
            if previous_departure is not None and departure <= previous_departure:
                raise ValueError("profile departures must increase")
            if previous_arrival is not None and arrival < previous_arrival:
                raise ValueError("profile violates FIFO")
            previous_departure, previous_arrival = departure, arrival

    @classmethod
    def constant(cls, travel_seconds):
        return cls(((0.0, float(travel_seconds)),))

    def travel_seconds(self, departure_seconds):
        times = tuple(point[0] for point in self.points)
        position = bisect_right(times, departure_seconds)
        if position == 0:
            return self.points[0][1]
        if position == len(self.points):
            return self.points[-1][1]
        left_time, left_travel = self.points[position - 1]
        right_time, right_travel = self.points[position]
        fraction = (departure_seconds - left_time) / (right_time - left_time)
        return left_travel + fraction * (right_travel - left_travel)


@dataclass(frozen=True)
class Edge:
    destination: str
    profile: FifoProfile


@dataclass(frozen=True)
class Result:
    vertex: str
    region: frozenset[str]
    objective_seconds: float
    travel_times_seconds: tuple[float, ...]


@dataclass(frozen=True)
class SearchResult:
    result: Result
    settled_labels: int


Graph = Mapping[str, tuple[Edge, ...]]
ORIGINS = ("west", "east")
TOLERANCE_SECONDS = 60


def shortest_times(graph: Graph, origin: str, departure_seconds: float):
    """Return elapsed shortest times using FIFO time-dependent Dijkstra."""
    arrivals = {origin: departure_seconds}
    frontier = [(departure_seconds, origin)]
    while frontier:
        arrival, vertex = heapq.heappop(frontier)
        if arrival != arrivals[vertex]:
            continue
        for edge in graph[vertex]:
            candidate = arrival + edge.profile.travel_seconds(arrival)
            if candidate < arrivals.get(edge.destination, float("inf")):
                arrivals[edge.destination] = candidate
                heapq.heappush(frontier, (candidate, edge.destination))
    return {vertex: arrival - departure_seconds for vertex, arrival in arrivals.items()}


def minimize_longest_drive(
    graph: Graph,
    origins=ORIGINS,
    departure_seconds=0,
    tolerance_seconds=TOLERANCE_SECONDS,
):
    """Minimize the longest trip when every origin leaves at the same time."""
    fields = tuple(
        shortest_times(graph, origin, departure_seconds) for origin in origins
    )
    reachable = set.intersection(*(set(field) for field in fields))
    scores = {vertex: max(field[vertex] for field in fields) for vertex in reachable}
    vertex = min(scores, key=lambda candidate: (scores[candidate], candidate))
    region = frozenset(
        candidate
        for candidate, score in scores.items()
        if score <= scores[vertex] + tolerance_seconds
    )
    return Result(
        vertex, region, scores[vertex], tuple(field[vertex] for field in fields)
    )


def bounded_minimize_longest_drive(
    graph: Graph,
    origins=ORIGINS,
    departure_seconds=0,
    tolerance_seconds=TOLERANCE_SECONDS,
):
    """Interleave FIFO searches and stop after the qualifying radius settles."""
    origins = tuple(origins)
    if not origins:
        raise ValueError("origins must not be empty")
    arrivals = [{origin: departure_seconds} for origin in origins]
    frontier = [
        (departure_seconds, origin_number, origin)
        for origin_number, origin in enumerate(origins)
    ]
    heapq.heapify(frontier)
    full_mask = (1 << len(origins)) - 1
    settled_masks = {}
    maxima = {}
    scores = {}
    optimum = None
    settled_labels = 0

    while frontier:
        arrival, origin_number, vertex = heapq.heappop(frontier)
        if arrival != arrivals[origin_number][vertex]:
            continue
        elapsed = arrival - departure_seconds
        if optimum is not None and elapsed > optimum + tolerance_seconds:
            break
        settled_labels += 1
        settled_masks[vertex] = settled_masks.get(vertex, 0) | (1 << origin_number)
        maxima[vertex] = max(maxima.get(vertex, 0), elapsed)
        if settled_masks[vertex] == full_mask:
            score = maxima[vertex]
            scores[vertex] = score
            if optimum is None:
                optimum = score

        for edge in graph[vertex]:
            candidate = arrival + edge.profile.travel_seconds(arrival)
            if (
                optimum is not None
                and candidate - departure_seconds > optimum + tolerance_seconds
            ):
                continue
            previous = arrivals[origin_number].get(edge.destination)
            if previous is None or candidate < previous:
                arrivals[origin_number][edge.destination] = candidate
                heapq.heappush(frontier, (candidate, origin_number, edge.destination))

    if optimum is None:
        raise ValueError("origins have no mutually reachable vertex")
    vertex = min((candidate for candidate, score in scores.items() if score == optimum))
    result = Result(
        vertex,
        frozenset(scores),
        optimum,
        tuple(
            arrivals[origin_number][vertex] - departure_seconds
            for origin_number in range(len(origins))
        ),
    )
    return SearchResult(result, settled_labels)


def synthetic_graph(traffic=True):
    west_center = (
        FifoProfile(
            (
                (0, 540),
                (2400, 540),
                (2700, 1080),
                (3600, 1080),
                (4500, 540),
            )
        )
        if traffic
        else FifoProfile.constant(540)
    )
    constant = FifoProfile.constant
    return {
        "west": (Edge("center", west_center), Edge("north", constant(360))),
        "east": (Edge("center", constant(540)), Edge("north", constant(840))),
        "center": (),
        "north": (),
    }


def graph_with_irrelevant_tail(length=100):
    """Add mutually reachable vertices far beyond the one-minute region."""
    graph = dict(synthetic_graph())
    graph["center"] = (Edge("remote-0", FifoProfile.constant(10_000)),)
    for index in range(length):
        vertex = f"remote-{index}"
        graph[vertex] = (
            (Edge(f"remote-{index + 1}", FifoProfile.constant(1)),)
            if index + 1 < length
            else ()
        )
    return graph


def current_static_result(graph: Graph):
    roads = nx.DiGraph()
    for position, vertex in enumerate(graph):
        roads.add_node(vertex, x=position, y=0)
    for start, edges in graph.items():
        for edge in edges:
            roads.add_edge(
                start, edge.destination, travel_time=edge.profile.travel_seconds(0)
            )
    return (
        CompactRoadGraph.from_networkx(roads)
        .analyze_vertices(ORIGINS)
        .optimize("maximum", TOLERANCE_SECONDS)
    )


def summary():
    traffic = synthetic_graph()
    quiet = bounded_minimize_longest_drive(traffic, departure_seconds=0).result
    peak = bounded_minimize_longest_drive(traffic, departure_seconds=2700).result
    constant = bounded_minimize_longest_drive(synthetic_graph(traffic=False)).result
    static = current_static_result(synthetic_graph(traffic=False))
    tail_graph = graph_with_irrelevant_tail()
    bounded_tail = bounded_minimize_longest_drive(tail_graph)
    exhaustive_tail = minimize_longest_drive(tail_graph)
    profile = traffic["west"][0].profile
    departures = (0, 2400, 2700, 3600, 4500)
    return {
        "fifo_arrivals": [
            departure + profile.travel_seconds(departure) for departure in departures
        ],
        "quiet": _result_dict(quiet),
        "peak": _result_dict(peak),
        "constant_profile_matches_static": (
            constant.vertex == static.vertex
            and constant.region == static.region
            and constant.objective_seconds == static.objective_seconds
            and constant.travel_times_seconds == static.travel_times_seconds
        ),
        "bounded_matches_exhaustive": bounded_tail.result == exhaustive_tail,
        "bounded_settled_labels": bounded_tail.settled_labels,
        "exhaustive_possible_labels": len(tail_graph) * len(ORIGINS),
    }


def _result_dict(result):
    return {
        "vertex": result.vertex,
        "region": sorted(result.region),
        "objective_seconds": result.objective_seconds,
        "travel_times_seconds": result.travel_times_seconds,
    }


if __name__ == "__main__":
    print(json.dumps(summary(), indent=2))
