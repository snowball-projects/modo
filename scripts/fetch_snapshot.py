"""Fetch and verify modo's configured immutable road snapshot."""

import os
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, build_opener

from modo.snapshots import DEFAULT_CATALOG, is_https_url, load_catalog

MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60
DOWNLOAD_CHUNK_BYTES = 64 * 1024
MAX_REDIRECTS = 5
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


_OPENER = build_opener(_NoRedirectHandler())


def digest(path):
    result = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def _redirect_target(current_url, headers):
    location = headers.get("Location") or headers.get("URI")
    try:
        target = urljoin(current_url, location)
    except (TypeError, ValueError) as error:
        raise RuntimeError("road snapshot redirect is invalid") from error
    if not is_https_url(target):
        raise RuntimeError("road snapshot redirected outside HTTPS")
    return target


def _open_snapshot(url, deadline, opener, clock):
    for _redirect in range(MAX_REDIRECTS + 1):
        remaining = deadline - clock()
        if remaining <= 0:
            raise RuntimeError("road snapshot download timed out")
        try:
            return opener(url, timeout=remaining)
        except HTTPError as error:
            try:
                if error.code not in REDIRECT_CODES:
                    raise RuntimeError(
                        f"road snapshot download failed with status {error.code}"
                    ) from error
                url = _redirect_target(url, error.headers)
            finally:
                error.close()
    raise RuntimeError("road snapshot has too many redirects")


def fetch(snapshot, destination, opener=None, clock=monotonic):
    """Download one HTTPS snapshot atomically and verify its checksum."""
    if not is_https_url(snapshot.url):
        raise RuntimeError("road snapshot URL must use HTTPS without credentials")
    destination = Path(destination)
    if destination.exists() and digest(destination) == snapshot.sha256:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        deadline = clock() + DOWNLOAD_TIMEOUT_SECONDS
        opener = _OPENER.open if opener is None else opener
        with (
            _open_snapshot(snapshot.url, deadline, opener, clock) as response,
            NamedTemporaryFile(dir=destination.parent, delete=False) as output,
        ):
            temporary = Path(output.name)
            if not is_https_url(response.geturl()):
                raise RuntimeError("road snapshot download left HTTPS")
            declared_length = response.headers.get("Content-Length")
            if declared_length is not None:
                try:
                    declared_length = int(declared_length)
                except ValueError as error:
                    raise RuntimeError(
                        "road snapshot has an invalid content length"
                    ) from error
                if not 0 <= declared_length <= MAX_SNAPSHOT_BYTES:
                    raise RuntimeError("road snapshot exceeds the download limit")
            result = sha256()
            received = 0
            read = response.read1 if hasattr(response, "read1") else response.read
            while True:
                if clock() >= deadline:
                    raise RuntimeError("road snapshot download timed out")
                chunk = read(DOWNLOAD_CHUNK_BYTES)
                if clock() > deadline:
                    raise RuntimeError("road snapshot download timed out")
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_SNAPSHOT_BYTES:
                    raise RuntimeError("road snapshot exceeds the download limit")
                result.update(chunk)
                output.write(chunk)
            if declared_length is not None and received != declared_length:
                raise RuntimeError("road snapshot content length does not match")
        if result.hexdigest() != snapshot.sha256:
            raise RuntimeError("road snapshot checksum does not match")
        temporary.replace(destination)
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = ArgumentParser()
    parser.add_argument(
        "snapshot",
        nargs="?",
        default=os.environ.get("MODO_SNAPSHOT", "chicago-static-v1"),
    )
    args = parser.parse_args()
    catalog = load_catalog(os.environ.get("MODO_CATALOG", DEFAULT_CATALOG))
    try:
        snapshot = next(item for item in catalog if item.identifier == args.snapshot)
    except StopIteration as error:
        raise SystemExit(f"unknown road snapshot: {args.snapshot}") from error
    fetch(snapshot, Path("data") / snapshot.file)


if __name__ == "__main__":
    main()
