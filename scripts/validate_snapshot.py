"""Verify one configured snapshot artifact and its production invariants."""

import os
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path

from modo import CompactRoadGraph
from modo.snapshots import DEFAULT_CATALOG, load_catalog


def digest(path):
    result = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def validate(snapshot, path):
    """Validate the checksum, structure, costs, direction, and declared bounds."""
    if digest(path) != snapshot.sha256:
        raise RuntimeError("road snapshot checksum does not match catalog")
    return CompactRoadGraph.load(path).validate_snapshot(snapshot.graph_bounds)


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
    validate(
        snapshot,
        Path(os.environ.get("MODO_GRAPH", Path("data") / snapshot.file)),
    )


if __name__ == "__main__":
    main()
