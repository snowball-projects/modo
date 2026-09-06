import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from experiments.tomtom.probe import probe


def test_probe_makes_only_two_bounded_requests():
    calls = []

    def open_request(request, *, timeout):
        calls.append(request.full_url)
        assert timeout == 20
        payload = (
            {"routes": [{}]}
            if "calculateRoute/" in request.full_url
            else {"reachableRange": {"boundary": [{}, {}, {}]}}
        )
        response = BytesIO(json.dumps(payload).encode())
        response.status = 200
        return response

    result = probe("test-secret", open_request)
    assert len(calls) == 2
    assert all("matrix" not in url for url in calls)
    assert result[0]["route_count"] == 1
    assert result[1]["boundary_points"] == 3
    assert "test-secret" not in json.dumps(result)


@pytest.mark.parametrize("http_error", [False, True])
def test_failures_never_echo_credentials_or_provider_bodies(http_error):
    def fail(request, *, timeout):
        if http_error:
            raise HTTPError(request.full_url, 403, "test-secret", {}, None)
        raise URLError("test-secret")

    result = probe("test-secret", fail)
    assert len(result) == 2
    assert "test-secret" not in json.dumps(result)
    assert all(
        item.get("status") == 403 if http_error else "error" in item for item in result
    )
