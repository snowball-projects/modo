"""Fetch and verify modo's configured immutable road snapshot."""

import os
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

from modo.snapshots import DEFAULT_CATALOG, load_catalog


def digest(path):
    result = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


parser = ArgumentParser()
parser.add_argument(
    "snapshot", nargs="?", default=os.environ.get("MODO_SNAPSHOT", "chicago-static-v1")
)
args = parser.parse_args()
catalog = load_catalog(os.environ.get("MODO_CATALOG", DEFAULT_CATALOG))
try:
    snapshot = next(item for item in catalog if item.identifier == args.snapshot)
except StopIteration as error:
    raise SystemExit(f"unknown road snapshot: {args.snapshot}") from error

destination = Path("data") / snapshot.file
if destination.exists() and digest(destination) == snapshot.sha256:
    raise SystemExit

destination.parent.mkdir(exist_ok=True)
temporary = None
try:
    with (
        urlopen(snapshot.url) as response,
        NamedTemporaryFile(dir=destination.parent, delete=False) as output,
    ):
        temporary = Path(output.name)
        result = sha256()
        while chunk := response.read(1024 * 1024):
            result.update(chunk)
            output.write(chunk)
    if result.hexdigest() != snapshot.sha256:
        raise RuntimeError("road snapshot checksum does not match")
    temporary.replace(destination)
finally:
    if temporary is not None:
        temporary.unlink(missing_ok=True)
