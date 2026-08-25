import modo
import pytest
from geographiclib.geodesic import Geodesic

from modo import geographic_median, minimax_center


def distance(a, b):
    return Geodesic.WGS84.Inverse(*a, *b)["s12"]


def test_rejects_invalid_input():
    for coordinates in ([], [(91, 0)], [(0, 181)], [(float("nan"), 0)], [(1, 2, 3)]):
        with pytest.raises(ValueError):
            geographic_median(coordinates)


def test_returns_one_point():
    assert geographic_median([(41, -87)]) == (41.0, -87.0)


def test_returns_two_point_geodesic_midpoint():
    points = [(41.8781, -87.6298), (29.7604, -95.3698)]
    result = geographic_median(points)
    assert abs(distance(points[0], result) - distance(result, points[1])) < 0.001


def test_finds_known_median():
    center = (0.0, 0.0)
    points = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    assert distance(geographic_median(points), center) < 500


def test_is_independent_of_input_order():
    points = [(47.6062, -122.3321), (34.0522, -118.2437),
              (41.8781, -87.6298), (40.7128, -74.0060)]
    assert distance(geographic_median(points), geographic_median(points[::-1])) < 1


def test_handles_duplicates_and_dateline():
    assert distance(geographic_median([(10, 179), (10, -179), (10, 179)]), (10, 179)) < 500


def test_collinear_non_unique_result_is_optimal():
    points = [(0, -3), (0, -1), (0, 1), (0, 3)]
    result = geographic_median(points)
    objective = lambda candidate: sum(distance(candidate, point) for point in points)
    assert objective(result) - objective((0, 0)) < 1


@pytest.mark.parametrize("coordinates", [[], [(91, 0)], [(0, 181)], [(float("nan"), 0)], [(1, 2, 3)]])
def test_minimax_center_rejects_invalid_input(coordinates):
    with pytest.raises(ValueError):
        minimax_center(coordinates)


def test_minimax_center_is_public():
    assert "minimax_center" in modo.__all__


def test_minimax_center_returns_one_point_and_two_point_midpoint():
    assert minimax_center([(41, -87)]) == (41.0, -87.0)
    points = [(41.8781, -87.6298), (29.7604, -95.3698)]
    result = minimax_center(points)
    assert abs(distance(points[0], result) - distance(result, points[1])) < 0.001


def test_minimax_center_minimizes_the_farthest_distance():
    points = [(0, -3), (0, -1), (0, 1), (0, 3)]
    result = minimax_center(points)
    objective = lambda candidate: max(distance(candidate, point) for point in points)
    assert objective(result) - objective((0, 0)) < 0.01


def test_minimax_center_is_order_independent_and_ignores_duplicates():
    points = [(47.6062, -122.3321), (34.0522, -118.2437),
              (41.8781, -87.6298), (40.7128, -74.0060)]
    assert distance(minimax_center(points), minimax_center(points[::-1])) < 1
    assert distance(minimax_center(points), minimax_center(points + points)) < 1


def test_minimax_center_handles_dateline():
    points = [(10, 179), (10, -179), (11, 180)]
    result = minimax_center(points)
    assert max(distance(result, point) for point in points) < 112_000
