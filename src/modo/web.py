"""Small WSGI application for the modo meeting-region interface."""

import json
import logging
import mimetypes
import os
from hashlib import sha256
from math import asin, cos, isfinite, radians, sin, sqrt
from pathlib import Path

import networkx as nx

from . import CompactRoadGraph, __version__
from .snapshots import DEFAULT_CATALOG, load_catalog

STATIC = Path(__file__).with_name("static")
CATALOG_PATH = Path(os.environ.get("MODO_CATALOG", DEFAULT_CATALOG))
CATALOG = load_catalog(CATALOG_PATH)
SNAPSHOT = os.environ.get("MODO_SNAPSHOT", "chicago-static-v1")
try:
    SNAPSHOT_METADATA = next(item for item in CATALOG if item.identifier == SNAPSHOT)
except StopIteration as error:
    raise RuntimeError(f"unknown configured road snapshot: {SNAPSHOT}") from error
GRAPH_PATH = os.environ.get("MODO_GRAPH", str(Path("data") / SNAPSHOT_METADATA.file))
REGION_TOLERANCE_SECONDS = 60
MAX_REQUEST_BYTES = 32_768
MAX_ORIGINS = 32
MAX_REGION_POINTS = 5_000
MAX_ROUTE_POINTS = 100_000
MAX_SNAP_DISTANCE_KILOMETERS = 5
LOGGER = logging.getLogger(__name__)
_graph = None
_SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Permissions-Policy", "camera=(), geolocation=(), microphone=()"),
    ("Strict-Transport-Security", "max-age=31536000"),
    ("X-Frame-Options", "DENY"),
)
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "connect-src 'self' https://photon.komoot.io; "
    "form-action 'none'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data: https://tile.openstreetmap.org; "
    "object-src 'none'; "
    "script-src 'self' https://unpkg.com; "
    "style-src 'self' 'unsafe-inline'"
)


class _BadRequest(Exception):
    """A request whose JSON or input values are invalid."""


class _UnprocessableRequest(Exception):
    """A valid request that the current snapshot cannot calculate."""


class _PayloadTooLarge(Exception):
    """A request body that exceeds the hosted-service byte limit."""


class _UnsupportedMediaType(Exception):
    """A request body that is not JSON."""


def _road():
    global _graph
    if _graph is None:
        digest = sha256()
        with Path(GRAPH_PATH).open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != SNAPSHOT_METADATA.sha256:
            raise RuntimeError("configured road snapshot checksum does not match catalog")
        _graph = CompactRoadGraph.load(GRAPH_PATH)
    return _graph


def _json(start_response, status, value, headers=()):
    body = json.dumps(value, separators=(",", ":")).encode()
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            *headers,
            *_SECURITY_HEADERS,
        ],
    )
    return [body]


def _body(environ):
    content_type = environ.get("CONTENT_TYPE", "").partition(";")[0].strip().lower()
    if content_type != "application/json":
        raise _UnsupportedMediaType("content type must be application/json")
    declared_length = environ.get("CONTENT_LENGTH")
    if declared_length in (None, ""):
        body = environ["wsgi.input"].read(MAX_REQUEST_BYTES + 1)
    else:
        try:
            length = int(declared_length)
        except (TypeError, ValueError) as error:
            raise _BadRequest("invalid content length") from error
        if length < 0:
            raise _BadRequest("invalid content length")
        if length > MAX_REQUEST_BYTES:
            raise _PayloadTooLarge("request is too large")
        body = environ["wsgi.input"].read(length)
        if len(body) != length:
            raise _BadRequest("request body is shorter than content length")
    if len(body) > MAX_REQUEST_BYTES:
        raise _PayloadTooLarge("request is too large")
    try:
        request = json.loads(body or b"{}")
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise _BadRequest("request body must be valid UTF-8 JSON") from error
    if not isinstance(request, dict):
        raise _BadRequest("JSON body must be an object")
    return request


def _coordinates(value):
    if not isinstance(value, list):
        raise _BadRequest("origins must be a list")
    if any(not isinstance(point, (list, tuple)) or len(point) != 2 for point in value):
        raise _BadRequest("origins must contain latitude, longitude pairs")
    if any(
        isinstance(coordinate, bool) or not isinstance(coordinate, (int, float))
        for point in value
        for coordinate in point
    ):
        raise _BadRequest("origin coordinates must be JSON numbers")
    try:
        points = tuple((float(latitude), float(longitude))
                       for latitude, longitude in value)
    except (OverflowError, TypeError, ValueError) as error:
        raise _BadRequest("origins must contain latitude, longitude pairs") from error
    if any(
        not isfinite(latitude)
        or not isfinite(longitude)
        or abs(latitude) > 90
        or abs(longitude) > 180
        for latitude, longitude in points
    ):
        raise _BadRequest("origin coordinates are out of range")
    return points


def _distance_kilometers(first, second):
    first_latitude, first_longitude = map(radians, first)
    second_latitude, second_longitude = map(radians, second)
    latitude_delta = second_latitude - first_latitude
    longitude_delta = second_longitude - first_longitude
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(first_latitude) * cos(second_latitude) * sin(longitude_delta / 2) ** 2
    )
    return 12_742.0176 * asin(sqrt(min(1, haversine)))


def _snap_origins(road, coordinates):
    vertices = road.nearest_vertices(coordinates)
    snapped = road.coordinates(vertices)
    if any(
        _distance_kilometers(point, match) > MAX_SNAP_DISTANCE_KILOMETERS
        for point, match in zip(coordinates, snapped, strict=True)
    ):
        raise _UnprocessableRequest(
            "An origin is too far from a road in modo's current snapshot."
        )
    return vertices, snapped


def _region(road, result):
    points = sorted(
        result.region_excess_seconds.items(),
        key=lambda item: road.coordinate(item[0]),
    )
    return [
        {
            "coordinate": list(road.coordinate(vertex)),
            "excess_seconds": excess,
        }
        for vertex, excess in points
    ]


def _evaluate(environ, start_response):
    origins = _body(environ).get("origins", [])
    coordinates = _coordinates(origins)
    if not 2 <= len(coordinates) <= MAX_ORIGINS:
        raise _BadRequest(f"provide between 2 and {MAX_ORIGINS} origins")
    if not SNAPSHOT_METADATA.contains(coordinates):
        raise _UnprocessableRequest(
            "An origin is outside modo's current Chicago-area coverage."
        )
    road = _road()
    origin_vertices, snapped_origins = _snap_origins(road, coordinates)
    try:
        analysis = road.analyze_vertices(origin_vertices)
        result = analysis.optimize("maximum", REGION_TOLERANCE_SECONDS)
    except nx.NetworkXNoPath as error:
        raise _UnprocessableRequest(
            "These origins have no mutually reachable road location."
        ) from error
    if len(result.region) > MAX_REGION_POINTS:
        raise _UnprocessableRequest(
            "The one-minute region is too large for this hosted interface."
        )
    routes = analysis.routes(result.vertex)
    if sum(len(route.coordinates) for route in routes) > MAX_ROUTE_POINTS:
        raise _UnprocessableRequest(
            "The routes are too large for this hosted interface."
        )
    return _json(
        start_response,
        "200 OK",
        {
            "origins": [list(point) for point in coordinates],
            "snapped_origins": [list(point) for point in snapped_origins],
            "objective_seconds": result.objective_seconds,
            "travel_times_seconds": list(result.travel_times_seconds),
            "region": _region(road, result),
            "routes": [[list(point) for point in route.coordinates] for route in routes],
            "provenance": {
                "snapshot": SNAPSHOT,
                "snapshot_sha256": SNAPSHOT_METADATA.sha256,
                "cost_profile": SNAPSHOT_METADATA.cost_profile,
                "core_bounds": list(SNAPSHOT_METADATA.core_bounds),
                "graph_bounds": list(SNAPSHOT_METADATA.graph_bounds),
                "modo": __version__,
                "tolerance_seconds": REGION_TOLERANCE_SECONDS,
            },
        },
    )


def _static_file(path):
    name = "index.html" if path == "/" else path.removeprefix("/")
    try:
        file = (STATIC / name).resolve()
        valid = file.is_relative_to(STATIC.resolve()) and file.is_file()
    except (OSError, RuntimeError, ValueError):
        return None
    if not valid:
        return None
    return file


def _static(start_response, file):
    body = file.read_bytes()
    content_type = mimetypes.guess_type(file)[0] or "application/octet-stream"
    start_response(
        "200 OK",
        [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-cache"),
            ("Content-Security-Policy", _CONTENT_SECURITY_POLICY),
            *_SECURITY_HEADERS,
        ],
    )
    return [body]


def _method_not_allowed(start_response, allowed):
    return _json(
        start_response,
        "405 Method Not Allowed",
        {"error": "method not allowed"},
        (("Allow", ", ".join(allowed)),),
    )


def _application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    try:
        if path == "/health":
            if method not in {"GET", "HEAD"}:
                return _method_not_allowed(start_response, ("GET", "HEAD"))
            _road()
            return _json(start_response, "200 OK", {"status": "ok"})
        if path == "/api/config":
            if method not in {"GET", "HEAD"}:
                return _method_not_allowed(start_response, ("GET", "HEAD"))
            return _json(
                start_response,
                "200 OK",
                {
                    "snapshot": SNAPSHOT,
                    "cost_profile": SNAPSHOT_METADATA.cost_profile,
                    "core_bounds": list(SNAPSHOT_METADATA.core_bounds),
                    "graph_bounds": list(SNAPSHOT_METADATA.graph_bounds),
                    "max_origins": MAX_ORIGINS,
                    "tolerance_seconds": REGION_TOLERANCE_SECONDS,
                },
            )
        if path == "/api/evaluations":
            if method != "POST":
                return _method_not_allowed(start_response, ("POST",))
            return _evaluate(environ, start_response)
        file = _static_file(path)
        if file is None:
            return _json(start_response, "404 Not Found", {"error": "not found"})
        if method not in {"GET", "HEAD"}:
            return _method_not_allowed(start_response, ("GET", "HEAD"))
        return _static(start_response, file)
    except _PayloadTooLarge as error:
        return _json(start_response, "413 Payload Too Large", {"error": str(error)})
    except _UnsupportedMediaType as error:
        return _json(
            start_response, "415 Unsupported Media Type", {"error": str(error)}
        )
    except _UnprocessableRequest as error:
        return _json(start_response, "422 Unprocessable Entity", {"error": str(error)})
    except _BadRequest as error:
        return _json(start_response, "400 Bad Request", {"error": str(error)})
    except Exception:
        LOGGER.exception("Unhandled modo request failure: %r %r", method, path)
        return _json(
            start_response,
            "500 Internal Server Error",
            {"error": "modo could not calculate this request"},
        )


def application(environ, start_response):
    """Serve the modo interface and same-origin evaluation API."""
    body = _application(environ, start_response)
    return [] if environ.get("REQUEST_METHOD", "GET") == "HEAD" else body
