import json

import pytest

from experiments.routing_engines.benchmark import (
    CASES_SCHEMA,
    benchmark,
    parse_sizes,
    validate_cases,
)


class FakeActor:
    def __init__(self, calls):
        self.calls = calls

    def route(self, request):
        self.calls.append(("route", request))
        return {"trip": {}}

    def matrix(self, request):
        self.calls.append(("matrix", request))
        return {"sources_to_targets": []}

    def isochrone(self, request):
        self.calls.append(("isochrone", request))
        return {"type": "FeatureCollection", "features": []}


def valid_document():
    return {
        "schema": CASES_SCHEMA,
        "cases": [
            {
                "name": "small",
                "costing": "auto",
                "origins": [
                    {"lat": 41.0, "lon": -87.0},
                    {"lat": 42.0, "lon": -88.0},
                ],
                "targets": [{"lat": 41.5, "lon": -87.5}],
                "route": {"origin": 1, "target": 0},
                "isochrone_minutes": 12,
                "date_time": {"type": 1, "value": "2026-09-04T08:00"},
            }
        ],
    }


def test_fake_actor_runs_every_phase_without_valhalla(tmp_path):
    config = tmp_path / "valhalla.json"
    config.write_text("{}\n")
    calls = []
    ticks = iter(range(0, 15_000_000, 1_000_000))
    result = benchmark(
        config,
        validate_cases(valid_document()),
        lambda path: FakeActor(calls),
        "fake",
        warm_runs=2,
        sizes={"graph": 10, "traffic": 2},
        clock=lambda: next(ticks),
        rss=lambda: 4096,
    )

    assert result["assets_bytes"] == {"graph": 10, "traffic": 2}
    case = result["cases"][0]
    assert case["timings_ms"] == {
        "actor_startup": 1.0,
        "route_cold": 1.0,
        "route_warm": {"samples": [1.0, 1.0], "median": 1.0},
        "matrix": 1.0,
        "isochrone_per_origin": [1.0, 1.0],
    }
    assert case["process_peak_rss_bytes"] == 4096
    assert [name for name, _ in calls] == [
        "route",
        "route",
        "route",
        "matrix",
        "isochrone",
        "isochrone",
    ]
    assert calls[0][1]["locations"] == [
        {"lat": 42.0, "lon": -88.0},
        {"lat": 41.5, "lon": -87.5},
    ]
    assert calls[3][1]["sources"] == valid_document()["cases"][0]["origins"]
    assert all(call[1]["contours"] == [{"time": 12}] for call in calls[-2:])
    assert json.dumps(result, sort_keys=True)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda value: value.update(schema="wrong"), "schema"),
        (lambda value: value["cases"][0].update(name=""), "names"),
        (
            lambda value: value["cases"][0]["origins"][0].update(lat=91),
            "coordinates",
        ),
        (
            lambda value: value["cases"][0].update(route={"origin": 2}),
            "route origin",
        ),
        (
            lambda value: value["cases"][0].update(extra=True),
            "unknown fields",
        ),
    ],
)
def test_invalid_cases_fail_clearly(change, message):
    document = valid_document()
    change(document)
    with pytest.raises(ValueError, match=message):
        validate_cases(document)


def test_size_metadata_is_strict_and_sorted():
    assert parse_sizes(["traffic=2", "graph=10"]) == {"graph": 10, "traffic": 2}
    with pytest.raises(ValueError, match="unique names"):
        parse_sizes(["graph=1", "graph=2"])
    with pytest.raises(ValueError, match="nonnegative"):
        parse_sizes(["graph=-1"])
    with pytest.raises(ValueError, match="NAME=BYTES"):
        parse_sizes(["graph=unknown"])
