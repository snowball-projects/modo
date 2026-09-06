import pytest

from experiments.time_dependent_traffic.experiment import (
    FifoProfile,
    bounded_minimize_longest_drive,
    graph_with_irrelevant_tail,
    minimize_longest_drive,
    summary,
    synthetic_graph,
)


def test_profile_enforces_fifo_arrivals():
    with pytest.raises(ValueError, match="violates FIFO"):
        FifoProfile(((0, 10), (1, 0)))
    arrivals = summary()["fifo_arrivals"]
    assert arrivals == sorted(arrivals)


def test_common_departure_time_changes_minimax_result():
    graph = synthetic_graph()
    assert (
        bounded_minimize_longest_drive(graph, departure_seconds=0).result.vertex
        == "center"
    )
    result = bounded_minimize_longest_drive(graph, departure_seconds=2700).result
    assert result.vertex == "north"
    assert result.objective_seconds == 840
    assert result.travel_times_seconds == (360, 840)


def test_constant_profile_matches_current_static_engine():
    assert summary()["constant_profile_matches_static"] is True


def test_bounded_frontier_matches_reference_without_scanning_remote_tail():
    graph = graph_with_irrelevant_tail()
    bounded = bounded_minimize_longest_drive(graph)

    assert bounded.result == minimize_longest_drive(graph)
    assert bounded.settled_labels < len(graph) * 2
    assert summary()["bounded_matches_exhaustive"] is True
