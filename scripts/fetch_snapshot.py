"""Fetch and verify modo's configured immutable road snapshot."""

import os
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

from modo.snapshots import DEFAULT_CATALOG, is_https_url, load_catalog

MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60


def digest(path):
    result = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def fetch(snapshot, destination, opener=urlopen):
    """Download one HTTPS snapshot atomically and verify its checksum."""
    if not is_https_url(snapshot.url):
        raise RuntimeError("road snapshot URL must use HTTPS without credentials")
    destination = Path(destination)
    if destination.exists() and digest(destination) == snapshot.sha256:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with (
            opener(snapshot.url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response,
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
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                if received > MAX_SNAPSHOT_BYTES:
                    raise RuntimeError("road snapshot exceeds the download limit")
                result.update(chunk)
                output.write(chunk)
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
