"""Immutable road snapshot catalog."""

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_CATALOG = Path(__file__).with_name("snapshots.json")


@dataclass(frozen=True)
class Snapshot:
    identifier: str
    file: str
    url: str
    sha256: str
    cost_profile: str
    core_bounds: tuple[float, float, float, float]
    graph_bounds: tuple[float, float, float, float]

    def contains(self, coordinates):
        """Return whether every latitude, longitude pair is in the supported core."""
        south, west, north, east = self.core_bounds
        return all(
            south <= latitude <= north and west <= longitude <= east
            for latitude, longitude in coordinates
        )


def load_catalog(path):
    """Load and validate a versioned snapshot catalog."""
    try:
        value = json.loads(Path(path).read_text())
        if value["schema_version"] != 1 or not isinstance(value["snapshots"], list):
            raise ValueError
        snapshots = tuple(_snapshot(item) for item in value["snapshots"])
    except (KeyError, OverflowError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid road snapshot catalog") from error
    if not snapshots or len({item.identifier for item in snapshots}) != len(snapshots):
        raise ValueError("invalid road snapshot catalog")
    return snapshots


def _snapshot(value):
    bounds = tuple(map(float, value["core_bounds"]))
    graph_bounds = tuple(map(float, value["graph_bounds"]))
    if (
        len(bounds) != 4
        or len(graph_bounds) != 4
        or not all(map(isfinite, (*bounds, *graph_bounds)))
        or abs(bounds[0]) > 90
        or abs(bounds[2]) > 90
        or abs(bounds[1]) > 180
        or abs(bounds[3]) > 180
        or abs(graph_bounds[0]) > 90
        or abs(graph_bounds[2]) > 90
        or abs(graph_bounds[1]) > 180
        or abs(graph_bounds[3]) > 180
        or bounds[0] > bounds[2]
        or bounds[1] > bounds[3]
        or graph_bounds[0] > bounds[0]
        or graph_bounds[1] > bounds[1]
        or graph_bounds[2] < bounds[2]
        or graph_bounds[3] < bounds[3]
        or Path(value["file"]).name != value["file"]
        or _unsafe_text(value["file"])
        or _unsafe_text(value["id"])
        or not is_https_url(value["url"])
        or _unsafe_text(value["cost_profile"])
        or not isinstance(value["sha256"], str)
        or len(value["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in value["sha256"])
    ):
        raise ValueError
    return Snapshot(
        value["id"],
        value["file"],
        value["url"],
        value["sha256"],
        value["cost_profile"],
        bounds,
        graph_bounds,
    )


def _unsafe_text(value):
    return (
        not isinstance(value, str)
        or not value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def is_https_url(value):
    """Return whether a URL is credential-free HTTPS with a valid host and port."""
    if _unsafe_text(value) or any(character.isspace() for character in value):
        return False
    try:
        parsed = urlparse(value)
        _port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
    )
