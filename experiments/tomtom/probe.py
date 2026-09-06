"""Make exactly two bounded TomTom capability checks with public coordinates."""

import json
import os
from argparse import ArgumentParser
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 20


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def load_key(env_file):
    key = os.environ.get("TOMTOM_API_KEY", "").strip()
    if not key and env_file.is_file():
        for line in env_file.read_text().splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == "TOMTOM_API_KEY":
                key = value.strip().strip("\"'")
                break
    if not key:
        raise ValueError("Set TOMTOM_API_KEY in the environment or the env file.")
    return key


def probe(key, opener=None):
    opener = opener or build_opener(NoRedirects()).open
    # Chicago public street intersections, not personal or user input locations.
    origin, destination = "41.8819,-87.6278", "41.8917,-87.6243"
    requests = (
        ("route", f"calculateRoute/{origin}:{destination}/json", {}),
        (
            "reachable_range",
            f"calculateReachableRange/{origin}/json",
            {"timeBudgetInSec": 300},
        ),
    )
    results = []
    for name, endpoint, options in requests:
        query = urlencode({"key": key, "traffic": "true", "departAt": "now", **options})
        request = Request(
            f"https://api.tomtom.com/routing/1/{endpoint}?{query}",
            headers={
                "Accept": "application/json",
                "User-Agent": "modo-capability-probe/1",
            },
        )
        started = perf_counter()
        result = {"endpoint": name}
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                payload = response.read(MAX_BYTES + 1)
                if len(payload) > MAX_BYTES:
                    raise ValueError("response too large")
                data = json.loads(payload)
                result["status"] = response.status
                if name == "route":
                    result["route_count"] = len(data["routes"])
                else:
                    result["boundary_points"] = len(data["reachableRange"]["boundary"])
        except HTTPError as error:
            result["status"] = error.code
            error.close()
        except (KeyError, OSError, TypeError, ValueError, URLError):
            result["error"] = "request failed or returned an invalid response"
        result["elapsed_seconds"] = round(perf_counter() - started, 3)
        results.append(result)
    return results


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    try:
        key = load_key(args.env_file)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    results = probe(key)
    print(json.dumps(results, indent=2))
    return 0 if all(result.get("status") == 200 for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
