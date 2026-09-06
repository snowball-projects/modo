"""Minimal, optional Valhalla routing benchmark."""

from __future__ import annotations

import json
import platform
import sys
from argparse import ArgumentParser
from hashlib import sha256
from importlib.metadata import version
from math import isfinite
from pathlib import Path
from statistics import median
from time import perf_counter_ns

CASES_SCHEMA = "modo-valhalla-cases-v1"
RESULT_SCHEMA = "modo-valhalla-benchmark-v1"


def _location(value, label):
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    latitude, longitude = value.get("lat"), value.get("lon")
    if (
        isinstance(latitude, bool)
        or not isinstance(latitude, (int, float))
        or not isfinite(latitude)
        or not -90 <= latitude <= 90
        or isinstance(longitude, bool)
        or not isinstance(longitude, (int, float))
        or not isfinite(longitude)
        or not -180 <= longitude <= 180
    ):
        raise ValueError(f"{label} needs finite lat/lon coordinates")
    return dict(value)


def _locations(value, label, minimum):
    if not isinstance(value, list) or len(value) < minimum:
        raise ValueError(f"{label} needs at least {minimum} locations")
    return [_location(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _index(value, label, length):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < length:
        raise ValueError(f"{label} must index an available location")
    return value


def validate_cases(document):
    if not isinstance(document, dict) or document.get("schema") != CASES_SCHEMA:
        raise ValueError(f"case input must use schema {CASES_SCHEMA!r}")
    raw_cases = document.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("cases must be a nonempty list")
    cases, names = [], set()
    allowed = {
        "name",
        "costing",
        "origins",
        "targets",
        "route",
        "isochrone_minutes",
        "date_time",
    }
    for position, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise TypeError(f"cases[{position}] must be an object")
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ValueError(f"case contains unknown fields: {', '.join(unknown)}")
        name = raw.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("case names must be nonempty and unique")
        names.add(name)
        costing = raw.get("costing", "auto")
        if not isinstance(costing, str) or not costing:
            raise ValueError(f"case {name!r} has invalid costing")
        origins = _locations(raw.get("origins"), f"case {name!r} origins", 2)
        targets = _locations(raw.get("targets"), f"case {name!r} targets", 1)
        route = raw.get("route", {})
        if not isinstance(route, dict) or set(route) - {"origin", "target"}:
            raise ValueError(f"case {name!r} route must contain origin/target indexes")
        route_origin = _index(route.get("origin", 0), "route origin", len(origins))
        route_target = _index(route.get("target", 0), "route target", len(targets))
        minutes = raw.get("isochrone_minutes", 30)
        if (
            isinstance(minutes, bool)
            or not isinstance(minutes, (int, float))
            or not isfinite(minutes)
            or minutes <= 0
        ):
            raise ValueError(f"case {name!r} needs positive isochrone_minutes")
        date_time = raw.get("date_time")
        if date_time is not None and not isinstance(date_time, dict):
            raise ValueError(f"case {name!r} date_time must be an object")
        cases.append(
            {
                "name": name,
                "costing": costing,
                "origins": origins,
                "targets": targets,
                "route_origin": route_origin,
                "route_target": route_target,
                "isochrone_minutes": minutes,
                "date_time": dict(date_time) if date_time is not None else None,
            }
        )
    return cases


def load_cases(path):
    try:
        document = json.loads(Path(path).read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid case JSON: {error.msg}") from error
    return validate_cases(document)


def parse_sizes(values):
    sizes = {}
    for value in values:
        name, separator, raw_size = value.partition("=")
        try:
            size = int(raw_size)
        except ValueError as error:
            raise ValueError("sizes must use NAME=BYTES") from error
        if not separator or not name or name in sizes or size < 0:
            raise ValueError("sizes must have unique names and nonnegative bytes")
        sizes[name] = size
    return dict(sorted(sizes.items()))


def peak_rss_bytes():
    if sys.platform not in {"darwin", "linux"}:
        return None
    try:
        from resource import RUSAGE_SELF, getrusage
    except ImportError:
        return None
    value = int(getrusage(RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _timed(call, request, clock):
    started = clock()
    call(request)
    elapsed = clock() - started
    if elapsed < 0:
        raise RuntimeError("benchmark clock moved backwards")
    return round(elapsed / 1_000_000, 6)


def _requests(case):
    common = {"costing": case["costing"]}
    if case["date_time"] is not None:
        common["date_time"] = case["date_time"]
    route = {
        **common,
        "locations": [
            case["origins"][case["route_origin"]],
            case["targets"][case["route_target"]],
        ],
    }
    matrix = {
        **common,
        "sources": case["origins"],
        "targets": case["targets"],
    }
    isochrones = [
        {
            **common,
            "locations": [origin],
            "contours": [{"time": case["isochrone_minutes"]}],
            "polygons": True,
        }
        for origin in case["origins"]
    ]
    return route, matrix, isochrones


def run_case(config, case, actor_factory, warm_runs, clock, rss):
    started = clock()
    actor = actor_factory(config)
    actor_ms = round((clock() - started) / 1_000_000, 6)
    route, matrix, isochrones = _requests(case)
    cold_ms = _timed(actor.route, route, clock)
    warm_ms = [_timed(actor.route, route, clock) for _ in range(warm_runs)]
    matrix_ms = _timed(actor.matrix, matrix, clock)
    isochrone_ms = [_timed(actor.isochrone, request, clock) for request in isochrones]
    result = {
        "name": case["name"],
        "origins": len(case["origins"]),
        "targets": len(case["targets"]),
        "timings_ms": {
            "actor_startup": actor_ms,
            "route_cold": cold_ms,
            "route_warm": {
                "samples": warm_ms,
                "median": round(median(warm_ms), 6),
            },
            "matrix": matrix_ms,
            "isochrone_per_origin": isochrone_ms,
        },
    }
    rss_value = rss()
    if rss_value is not None:
        result["process_peak_rss_bytes"] = rss_value
    return result


def benchmark(
    config,
    cases,
    actor_factory,
    engine_version,
    warm_runs=5,
    sizes=None,
    clock=perf_counter_ns,
    rss=peak_rss_bytes,
):
    if isinstance(warm_runs, bool) or not isinstance(warm_runs, int) or warm_runs < 1:
        raise ValueError("warm_runs must be a positive integer")
    config_path = Path(config)
    config_bytes = config_path.read_bytes()
    return {
        "schema": RESULT_SCHEMA,
        "engine": {
            "name": "Valhalla",
            "package": "pyvalhalla",
            "version": engine_version,
        },
        "environment": {
            "machine": platform.machine(),
            "python": platform.python_version(),
            "system": platform.system(),
        },
        "config": {
            "bytes": len(config_bytes),
            "sha256": sha256(config_bytes).hexdigest(),
        },
        "assets_bytes": sizes or {},
        "warm_runs": warm_runs,
        "cases": [
            run_case(config_path, case, actor_factory, warm_runs, clock, rss)
            for case in cases
        ],
    }


def load_valhalla():
    try:
        from valhalla import Actor
    except ImportError as error:
        raise RuntimeError(
            "pyvalhalla is optional; run this with an isolated pyvalhalla environment"
        ) from error
    return Actor, version("pyvalhalla")


def parser():
    value = ArgumentParser(description=__doc__)
    value.add_argument("--config", required=True, type=Path)
    value.add_argument("--cases", required=True, type=Path)
    value.add_argument("--warm-runs", type=int, default=5)
    value.add_argument(
        "--size",
        action="append",
        default=[],
        metavar="NAME=BYTES",
        help="record an input or graph size without exposing its local path",
    )
    return value


def main(argv=None):
    arguments = parser().parse_args(argv)
    try:
        cases = load_cases(arguments.cases)
        sizes = parse_sizes(arguments.size)
        actor_factory, engine_version = load_valhalla()
        result = benchmark(
            arguments.config,
            cases,
            actor_factory,
            engine_version,
            arguments.warm_runs,
            sizes,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        parser().error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
