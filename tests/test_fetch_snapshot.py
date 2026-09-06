from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from scripts import fetch_snapshot


class Response:
    def __init__(
        self, body=b"roads", *, url="https://cdn.example.test/roads", headers=None
    ):
        self.body = body
        self.url = url
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def geturl(self):
        return self.url

    def read(self, _size):
        body, self.body = self.body, b""
        return body


def snapshot(body=b"roads"):
    return SimpleNamespace(
        url="https://example.test/roads",
        sha256=sha256(body).hexdigest(),
    )


def opener(response):
    def open_url(url, *, timeout):
        assert url == "https://example.test/roads"
        assert 0 < timeout <= fetch_snapshot.DOWNLOAD_TIMEOUT_SECONDS
        return response

    return open_url


def test_fetches_verifies_and_reuses_snapshot(tmp_path):
    destination = tmp_path / "roads.npz"
    assert fetch_snapshot.fetch(snapshot(), destination, opener(Response())) is True
    assert destination.read_bytes() == b"roads"

    def fail(*_args, **_kwargs):
        raise AssertionError("a verified snapshot must not be downloaded again")

    assert fetch_snapshot.fetch(snapshot(), destination, fail) is False


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/roads.npz",
        "http://example.test/roads.npz",
        "https://user:secret@example.test/roads.npz",
        "https://example.test/roads\n.npz",
    ],
)
def test_rejects_unsafe_url_before_opening(tmp_path, url):
    value = snapshot()
    value.url = url

    def fail(*_args, **_kwargs):
        raise AssertionError("unsafe URLs must not be opened")

    with pytest.raises(RuntimeError, match="must use HTTPS without credentials"):
        fetch_snapshot.fetch(value, tmp_path / "roads.npz", fail)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (Response(url="http://cdn.example.test/roads"), "left HTTPS"),
        (Response(url="https:///roads"), "left HTTPS"),
        (Response(url="https://user:secret@example.test/roads"), "left HTTPS"),
        (Response(url="https://example.test/roads\n"), "left HTTPS"),
        (Response(url="https://example.test:invalid/roads"), "left HTTPS"),
        (Response(headers={"Content-Length": "invalid"}), "invalid content length"),
        (Response(headers={"Content-Length": "6"}), "exceeds the download limit"),
        (Response(body=b"larger"), "exceeds the download limit"),
    ],
)
def test_rejects_unsafe_or_oversized_downloads(
    monkeypatch, tmp_path, response, message
):
    monkeypatch.setattr(fetch_snapshot, "MAX_SNAPSHOT_BYTES", 5)
    destination = tmp_path / "roads.npz"
    with pytest.raises(RuntimeError, match=message):
        fetch_snapshot.fetch(snapshot(), destination, opener(response))
    assert list(tmp_path.iterdir()) == []


def test_rejects_checksum_mismatch_without_replacing_destination(tmp_path):
    destination = tmp_path / "roads.npz"
    with pytest.raises(RuntimeError, match="checksum does not match"):
        fetch_snapshot.fetch(snapshot(), destination, opener(Response(b"other")))
    assert list(tmp_path.iterdir()) == []


def redirect(url, location, code=302):
    return HTTPError(url, code, "redirect", {"Location": location}, BytesIO())


def test_follows_only_bounded_https_redirects(tmp_path):
    calls = []

    def open_url(url, *, timeout):
        calls.append((url, timeout))
        if len(calls) == 1:
            raise redirect(url, "/immutable/roads.npz")
        return Response(url=url)

    destination = tmp_path / "roads.npz"
    assert fetch_snapshot.fetch(snapshot(), destination, open_url) is True
    assert [url for url, _timeout in calls] == [
        "https://example.test/roads",
        "https://example.test/immutable/roads.npz",
    ]


def test_rejects_redirect_outside_https(tmp_path):
    def open_url(url, *, timeout):
        raise redirect(url, "http://example.test/roads.npz")

    with pytest.raises(RuntimeError, match="redirected outside HTTPS"):
        fetch_snapshot.fetch(snapshot(), tmp_path / "roads.npz", open_url)
    assert list(tmp_path.iterdir()) == []


def test_rejects_too_many_redirects(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_snapshot, "MAX_REDIRECTS", 1)

    def open_url(url, *, timeout):
        raise redirect(url, "/again")

    with pytest.raises(RuntimeError, match="too many redirects"):
        fetch_snapshot.fetch(snapshot(), tmp_path / "roads.npz", open_url)
    assert list(tmp_path.iterdir()) == []


def test_rejects_non_redirect_http_errors(tmp_path):
    def open_url(url, *, timeout):
        raise HTTPError(url, 503, "unavailable", {}, BytesIO())

    with pytest.raises(RuntimeError, match="failed with status 503"):
        fetch_snapshot.fetch(snapshot(), tmp_path / "roads.npz", open_url)
    assert list(tmp_path.iterdir()) == []


def test_rejects_download_past_total_deadline(tmp_path):
    readings = iter((0, 0, 61))

    with pytest.raises(RuntimeError, match="timed out"):
        fetch_snapshot.fetch(
            snapshot(),
            tmp_path / "roads.npz",
            opener(Response()),
            clock=lambda: next(readings),
        )
    assert list(tmp_path.iterdir()) == []


def test_rejects_content_length_mismatch(tmp_path):
    response = Response(headers={"Content-Length": "6"})

    with pytest.raises(RuntimeError, match="content length does not match"):
        fetch_snapshot.fetch(snapshot(), tmp_path / "roads.npz", opener(response))
    assert list(tmp_path.iterdir()) == []
