"""Offline hosted-API budget comparison; each case uses a fresh process."""

import io
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
from argparse import ArgumentParser
from time import perf_counter


def grid(rows, columns, latitude, longitude, step):
    return [
        [latitude + row * step, longitude + column * step]
        for row in range(rows)
        for column in range(columns)
    ]


CASES = {
    "ordinary_two": [[41.881, -87.630], [41.9484, -87.6553]],
    "nearby_two": [[41.93, -87.70], [41.94, -87.69]],
    "nearby_six": grid(2, 3, 41.93, -87.70, 0.003),
    "nearby_eight": grid(2, 4, 41.93, -87.70, 0.003),
    "nearby_thirty_two": grid(4, 8, 41.93, -87.72, 0.003),
    "regional_eight": grid(2, 4, 41.89, -88.04, 0.08),
    "regional_thirty_two": grid(4, 8, 41.89, -88.08, 0.04),
    "opposite_corners_two": [[41.875, -88.105], [42.15, -87.635]],
}


def worker(name, minimum):
    from modo import web

    web.MIN_SPARSE_LABELS = minimum
    road = web._road()
    coordinates = CASES[name]
    # Regional grid points are synthetic. Move them onto the nearest stored
    # road vertex before benchmarking so water/off-road validation is not the
    # limiting condition. This changes no graph or production configuration.
    if name.startswith("regional_") or name == "opposite_corners_two":
        coordinates = road.coordinates(road.nearest_vertices(coordinates))
    assert web.SNAPSHOT_METADATA.contains(coordinates)
    vertices, _ = web._snap_origins(road, coordinates)
    unique, _ = web._unique_origins(vertices)
    unit = 1024 * 1024 if sys.platform == "darwin" else 1024
    baseline = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / unit
    payload = json.dumps({"origins": coordinates}).encode()
    timings = []
    replies = []
    for _ in range(3):
        status = []
        environ = {
            "PATH_INFO": "/api/evaluations",
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
        }
        start = perf_counter()
        body = b"".join(
            web.application(
                environ, lambda value, _, status=status: status.append(value)
            )
        )
        timings.append(1000 * (perf_counter() - start))
        response = json.loads(body)
        replies.append((status[0], response))
    assert all(reply == replies[0] for reply in replies)
    status, response = replies[0]
    return {
        "case": name,
        "minimum": minimum,
        "unique_origins": len(unique),
        "label_budget": web._sparse_label_budget(road, len(unique)),
        "status": status,
        "region_vertices": len(response.get("region", [])),
        "objective_seconds": response.get("objective_seconds"),
        "error": response.get("error"),
        "median_ms": round(statistics.median(timings), 3),
        "max_ms": round(max(timings), 3),
        "baseline_peak_rss_mib": round(baseline, 3),
        "peak_rss_mib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / unit, 3
        ),
    }


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--minimum", type=int, choices=(5000, 10000), default=10000)
    args = parser.parse_args()
    if args.case:
        print(json.dumps(worker(args.case, args.minimum)))
        return
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "repeats": 3,
            }
        )
    )
    for case in CASES:
        for minimum in (5000, 10000):
            completed = subprocess.run(
                [sys.executable, __file__, "--case", case, "--minimum", str(minimum)],
                text=True,
                capture_output=True,
                env=os.environ,
                check=True,
                timeout=30,
            )
            print(completed.stdout, end="", flush=True)


if __name__ == "__main__":
    main()
