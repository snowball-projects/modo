import io
import json
import logging
from dataclasses import replace
from hashlib import sha256

import networkx as nx
import pytest

from modo import CompactRoadGraph, __version__, web


def request(
    path="/",
    method="GET",
    payload=None,
    *,
    raw_body=None,
    content_length="auto",
    content_type="application/json",
):
    body = (
        raw_body
        if raw_body is not None
        else json.dumps(payload).encode()
        if payload is not None
        else b""
    )
    status = None
    headers = None

    def start_response(value, values):
        nonlocal status, headers
        status, headers = value, dict(values)

    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "wsgi.input": io.BytesIO(body),
    }
    if content_type is not None:
        environ["CONTENT_TYPE"] = content_type
    if content_length == "auto":
        environ["CONTENT_LENGTH"] = str(len(body))
    elif content_length is not None:
        environ["CONTENT_LENGTH"] = str(content_length)
    result = b"".join(web.application(environ, start_response))
    return status, headers, result


@pytest.fixture(autouse=True)
def clear_graph(monkeypatch):
    monkeypatch.setattr(web, "_graph", None)
    monkeypatch.setattr(web, "EVALUATION_BURST", 100)
    monkeypatch.setattr(web, "_evaluation_tokens", 100)
    monkeypatch.setattr(web, "_evaluation_refill", web.monotonic())


def road_graph():
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    graph.add_node("b", y=41.88, x=-87.70)
    graph.add_node("best", y=41.89, x=-87.76)
    graph.add_node("near", y=41.90, x=-87.75)
    graph.add_edge("a", "best", travel_time=4)
    graph.add_edge("b", "best", travel_time=5)
    graph.add_edge("a", "near", travel_time=54)
    graph.add_edge("b", "near", travel_time=65)
    return CompactRoadGraph.from_networkx(graph)


def test_serves_single_objective_interface():
    status, headers, body = request()
    assert status == "200 OK"
    assert headers["Cache-Control"] == "no-cache"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Strict-Transport-Security"] == "max-age=31536000"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "https://photon.komoot.io" in headers["Content-Security-Policy"]
    assert "script-src 'self';" in headers["Content-Security-Policy"]
    assert "unpkg.com" not in headers["Content-Security-Policy"]
    assert b"modo" in body
    assert b"Best possible longest drive" not in body
    assert b'id="result"' not in body
    assert b'id="best-time"' not in body
    assert b"within 60 seconds" in body
    assert b"total driving time" not in body
    assert b"Region tolerance" not in body
    assert b"Service policy" in body
    assert f'href="/styles.css?v={__version__}"'.encode() in body
    assert b'href="/leaflet.css?v=1.9.4"' in body
    assert b'src="/leaflet.js?v=1.9.4"' in body
    assert b"unpkg.com" not in body
    assert f'src="/app.js?v={__version__}"'.encode() in body

    status, headers, body = request("/app.js")
    assert status == "200 OK"
    assert headers["Cache-Control"] == "no-cache"
    assert b'fetch("/api/evaluations"' in body
    assert b"result.routes.forEach" in body
    assert b"const PALETTE" in body
    assert b"looksLikeCoordinateInput(query)" in body
    assert b"map.stop()" in body
    assert b"animate: false" in body
    assert b"clearTimeout(row.timer)" in body
    assert b"result.routes.flat()" in body
    assert b'"aria-activedescendant"' in body
    assert b'event.key === "ArrowDown"' in body
    assert b'event.key === "ArrowUp"' in body
    assert b'event.key === "Escape"' in body
    assert b"result.snapped_origins" in body
    assert b"result.travel_times_seconds" in body
    assert b'fillColor: "#00A98F"' in body
    assert b"One-minute region ready." in body
    assert b"resultSignature" in body
    assert b"Best road location at" in body
    assert b"bindPopup" not in body
    assert b"view.bestTime" not in body
    assert b"view.result" not in body

    status, _headers, body = request("/styles.css")
    assert status == "200 OK"
    assert b".origin-pin" in body
    assert b".result" not in body
    assert b".eyebrow" not in body
    assert b".sr-only" in body

    status, headers, body = request("/leaflet.css")
    assert status == "200 OK"
    assert headers["Cache-Control"] == "no-cache"
    assert b".leaflet-pane" in body
    assert b"position: absolute" in body

    status, headers, body = request("/leaflet.js")
    assert status == "200 OK"
    assert headers["Cache-Control"] == "no-cache"
    assert b"Leaflet 1.9.4" in body


def test_config_describes_fixed_region():
    status, _headers, body = request("/api/config")
    result = json.loads(body)
    assert status == "200 OK"
    assert result == {
        "snapshot": "chicago-static-v1",
        "cost_profile": "static-free-flow-seconds-v1",
        "core_bounds": [41.868, -88.116, 42.162, -87.6253],
        "graph_bounds": [41.8500077, -88.1399989, 42.1799662, -87.6012705],
        "max_origins": 32,
        "tolerance_seconds": 60,
    }


def test_calculates_only_minimax_region_and_routes(monkeypatch):
    monkeypatch.setattr(web, "_graph", road_graph())
    status, _headers, body = request(
        "/api/evaluations",
        "POST",
        {
            "origins": [[41.8801, -87.8001], [41.8801, -87.7001]],
            "tolerance_seconds": 0,
        },
    )
    result = json.loads(body)
    assert status == "200 OK"
    assert "total" not in result
    assert "maximum" not in result
    assert result["origins"] == [[41.8801, -87.8001], [41.8801, -87.7001]]
    assert result["snapped_origins"] == [[41.88, -87.8], [41.88, -87.7]]
    assert result["objective_seconds"] == 5
    assert result["travel_times_seconds"] == [4, 5]
    assert result["region"] == [
        {"coordinate": [41.89, -87.76], "excess_seconds": 0.0},
        {"coordinate": [41.9, -87.75], "excess_seconds": 60.0},
    ]
    assert result["routes"] == [
        [[41.88, -87.8], [41.89, -87.76]],
        [[41.88, -87.7], [41.89, -87.76]],
    ]
    assert result["provenance"]["tolerance_seconds"] == 60
    assert result["provenance"]["modo"] == __version__


def test_deduplicates_snapped_origins_without_changing_response(monkeypatch):
    import modo.compact

    sparse_dijkstra = modo.compact.dijkstra
    calls = []

    def counted(*args, **kwargs):
        calls.append(kwargs["indices"])
        return sparse_dijkstra(*args, **kwargs)

    monkeypatch.setattr(modo.compact, "dijkstra", counted)
    monkeypatch.setattr(web, "_graph", road_graph())
    status, _headers, body = request(
        "/api/evaluations",
        "POST",
        {"origins": [[41.8801, -87.8001], [41.8802, -87.8002]]},
    )
    result = json.loads(body)
    assert status == "200 OK"
    assert result["snapped_origins"] == [[41.88, -87.8], [41.88, -87.8]]
    assert result["travel_times_seconds"] == [0, 0]
    assert result["routes"] == [
        [[41.88, -87.8]],
        [[41.88, -87.8]],
    ]
    assert calls == []


def test_hosted_success_does_not_run_full_graph_dijkstra(monkeypatch):
    import modo.compact

    def fail(*_args, **_kwargs):
        raise AssertionError("hosted bounded search must not run full Dijkstra")

    monkeypatch.setattr(modo.compact, "dijkstra", fail)
    monkeypatch.setattr(web, "_graph", road_graph())

    status, _headers, body = request(
        "/api/evaluations",
        "POST",
        {"origins": [[41.8801, -87.8001], [41.8801, -87.7001]]},
    )

    assert status == "200 OK"
    assert json.loads(body)["travel_times_seconds"] == [4, 5]


def test_sparse_budget_abort_fails_without_full_graph_search(monkeypatch):
    import modo.compact

    sparse_dijkstra = modo.compact.dijkstra
    calls = []

    def counted(*args, **kwargs):
        calls.append(kwargs["indices"])
        return sparse_dijkstra(*args, **kwargs)

    monkeypatch.setattr(modo.compact, "dijkstra", counted)
    monkeypatch.setattr(web, "_graph", road_graph())
    monkeypatch.setattr(web, "MIN_SPARSE_LABELS", 1)
    monkeypatch.setattr(web, "MAX_SPARSE_LABELS", 1)
    status, _headers, body = request(
        "/api/evaluations",
        "POST",
        {"origins": [[41.8801, -87.8001], [41.8801, -87.7001]]},
    )
    assert status == "422 Unprocessable Entity"
    assert b"exact-search limit" in body
    assert calls == []


def test_route_limit_counts_duplicate_response_routes(monkeypatch):
    monkeypatch.setattr(web, "_graph", road_graph())
    monkeypatch.setattr(web, "MAX_ROUTE_POINTS", 1)
    status, _headers, body = request(
        "/api/evaluations",
        "POST",
        {"origins": [[41.8801, -87.8001], [41.8802, -87.8002]]},
    )
    assert status == "422 Unprocessable Entity"
    assert b"routes are too large" in body


def test_health_loads_the_snapshot(monkeypatch):
    monkeypatch.setattr(web, "_graph", road_graph())
    status, _headers, body = request("/health")
    assert status == "200 OK"
    assert json.loads(body) == {"status": "ok"}


@pytest.mark.parametrize(
    "origins",
    [
        [],
        [[41.88, -87.8]],
        {"first": [41.88, -87.8]},
        ["41.88,-87.8", "41.88,-87.7"],
        [[True, -87.8], [41.88, -87.7]],
        [["41.88", -87.8], [41.88, -87.7]],
        [[91, 0], [41.88, -87.7]],
    ],
)
def test_rejects_invalid_origins(origins):
    status, _headers, _body = request("/api/evaluations", "POST", {"origins": origins})
    assert status == "400 Bad Request"


def test_rejects_origins_too_far_from_snapshot_roads(monkeypatch):
    monkeypatch.setattr(web, "_graph", road_graph())
    status, _headers, body = request(
        "/api/evaluations",
        "POST",
        {"origins": [[42.15, -87.64], [41.88, -87.7]]},
    )
    assert status == "422 Unprocessable Entity"
    assert b"too far from a road" in body


def test_rejects_an_origin_outside_the_supported_core():
    status, _headers, body = request(
        "/api/evaluations",
        "POST",
        {"origins": [[42.18, -87.8], [41.88, -87.7]]},
    )
    assert status == "422 Unprocessable Entity"
    assert b"outside modo's current Chicago-area coverage" in body


def test_refuses_to_claim_provenance_for_an_unverified_graph(monkeypatch, tmp_path):
    path = tmp_path / "roads.npz"
    road_graph().save(path)
    monkeypatch.setattr(web, "GRAPH_PATH", str(path))
    with pytest.raises(RuntimeError, match="checksum does not match catalog"):
        web._road()


def test_loads_the_same_snapshot_handle_that_was_verified(monkeypatch, tmp_path):
    path = tmp_path / "roads.npz"
    road_graph().save(path)
    replacement = tmp_path / "replacement.npz"
    replacement.write_bytes(b"replaced after verification")
    expected = sha256(path.read_bytes()).hexdigest()
    bounds = (41.88, -87.8, 41.9, -87.7)
    original_load = web.CompactRoadGraph.load

    def replace_then_load(source):
        replacement.replace(path)
        return original_load(source)

    monkeypatch.setattr(web, "GRAPH_PATH", str(path))
    monkeypatch.setattr(
        web,
        "SNAPSHOT_METADATA",
        replace(web.SNAPSHOT_METADATA, sha256=expected, graph_bounds=bounds),
    )
    monkeypatch.setattr(web.CompactRoadGraph, "load", replace_then_load)

    assert web._road().analyze_vertices(("a",)).travel_times(
        "best"
    ).travel_times_seconds == (4.0,)
    assert path.read_bytes() == b"replaced after verification"


def test_rejects_unreachable_origins(monkeypatch):
    graph = nx.DiGraph()
    graph.add_node("a", y=41.88, x=-87.80)
    graph.add_node("b", y=41.88, x=-87.70)
    monkeypatch.setattr(web, "_graph", CompactRoadGraph.from_networkx(graph))
    status, _headers, body = request(
        "/api/evaluations",
        "POST",
        {"origins": [[41.88, -87.8], [41.88, -87.7]]},
    )
    assert status == "422 Unprocessable Entity"
    assert b"no mutually reachable road location" in body


def test_rejects_oversized_region(monkeypatch):
    monkeypatch.setattr(web, "_graph", road_graph())
    monkeypatch.setattr(web, "MAX_REGION_POINTS", 1)
    status, _headers, body = request(
        "/api/evaluations",
        "POST",
        {"origins": [[41.88, -87.8], [41.88, -87.7]]},
    )
    assert status == "422 Unprocessable Entity"
    assert b"one-minute region is too large" in body


def test_rejects_oversized_routes(monkeypatch):
    monkeypatch.setattr(web, "_graph", road_graph())
    monkeypatch.setattr(web, "MAX_ROUTE_POINTS", 3)
    status, _headers, body = request(
        "/api/evaluations",
        "POST",
        {"origins": [[41.88, -87.8], [41.88, -87.7]]},
    )
    assert status == "422 Unprocessable Entity"
    assert b"routes are too large" in body


def test_request_body_limits_and_json_validation():
    status, _headers, _body = request(
        "/api/evaluations",
        "POST",
        raw_body=b"{}",
        content_length=web.MAX_REQUEST_BYTES + 1,
    )
    assert status == "413 Payload Too Large"
    assert request("/api/evaluations", "POST", raw_body=b"[]")[0] == "400 Bad Request"
    huge_integer = b'{"origins":' + (b"1" * 5_000) + b"}"
    assert request("/api/evaluations", "POST", raw_body=huge_integer)[0] == (
        "400 Bad Request"
    )
    assert request("/api/evaluations", "POST", raw_body=b'{"origins":\xff}')[0] == (
        "400 Bad Request"
    )
    assert (
        request("/api/evaluations", "POST", raw_body=b"{}", content_type="text/plain")[
            0
        ]
        == "415 Unsupported Media Type"
    )
    assert (
        request("/api/evaluations", "POST", raw_body=b"{}", content_type=None)[0]
        == "415 Unsupported Media Type"
    )


def test_globally_rate_limits_evaluations_without_identifiers(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(web, "monotonic", lambda: clock[0])
    monkeypatch.setattr(web, "EVALUATION_BURST", 1)
    monkeypatch.setattr(web, "_evaluation_tokens", 1)
    monkeypatch.setattr(web, "_evaluation_refill", 0)
    monkeypatch.setattr(web, "_graph", road_graph())
    payload = {"origins": [[41.8801, -87.8001], [41.8801, -87.7001]]}
    assert request("/api/evaluations", "POST", payload)[0] == "200 OK"
    status, headers, body = request("/api/evaluations", "POST", payload)
    assert status == "429 Too Many Requests"
    assert headers["Retry-After"] == "1"
    assert json.loads(body) == {"error": "modo is busy; retry shortly"}
    clock[0] = 1
    assert request("/api/evaluations", "POST", payload)[0] == "200 OK"


def test_invalid_request_does_not_consume_evaluation_token(monkeypatch):
    monkeypatch.setattr(web, "monotonic", lambda: 0)
    monkeypatch.setattr(web, "EVALUATION_BURST", 1)
    monkeypatch.setattr(web, "_evaluation_tokens", 1)
    monkeypatch.setattr(web, "_evaluation_refill", 0)
    monkeypatch.setattr(web, "_graph", road_graph())
    assert request("/api/evaluations", "POST", raw_body=b"[]")[0] == ("400 Bad Request")
    payload = {"origins": [[41.8801, -87.8001], [41.8801, -87.7001]]}
    assert request("/api/evaluations", "POST", payload)[0] == "200 OK"
    assert request("/api/evaluations", "POST", payload)[0] == ("429 Too Many Requests")


def test_logs_unexpected_failures(monkeypatch, caplog):
    def fail():
        raise ValueError("corrupt snapshot")

    monkeypatch.setattr(web, "_road", fail)
    with caplog.at_level(logging.ERROR, logger="modo.web"):
        status, _headers, body = request(
            "/api/evaluations",
            "POST",
            {"origins": [[41.88, -87.8], [41.88, -87.7]]},
        )
    assert status == "500 Internal Server Error"
    assert b"modo could not calculate this request" in body
    assert b"corrupt snapshot" not in body
    assert "Unhandled modo request failure" in caplog.text


def test_unknown_and_unsupported_routes():
    assert request("/missing")[0] == "404 Not Found"
    assert request("/missing", "POST")[0] == "404 Not Found"

    status, headers, _body = request("/api/config", "POST")
    assert status == "405 Method Not Allowed"
    assert headers["Allow"] == "GET, HEAD"

    status, headers, _body = request("/api/evaluations", "GET")
    assert status == "405 Method Not Allowed"
    assert headers["Allow"] == "POST"

    status, headers, _body = request("/app.js", "POST")
    assert status == "405 Method Not Allowed"
    assert headers["Allow"] == "GET, HEAD"


@pytest.mark.parametrize("path", ["/", "/app.js", "/api/config", "/health"])
def test_head_matches_get_headers_without_a_body(monkeypatch, path):
    monkeypatch.setattr(web, "_graph", road_graph())
    get_status, get_headers, get_body = request(path)
    head_status, head_headers, head_body = request(path, "HEAD")
    assert head_status == get_status == "200 OK"
    assert head_headers == get_headers
    assert int(head_headers["Content-Length"]) == len(get_body)
    assert head_body == b""
