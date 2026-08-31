from hashlib import sha256
from types import SimpleNamespace

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
        assert timeout == fetch_snapshot.DOWNLOAD_TIMEOUT_SECONDS
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
