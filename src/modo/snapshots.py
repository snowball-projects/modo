"""Immutable road snapshot catalog."""

import json
from dataclasses import dataclass
from pathlib import Path

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
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
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
        or bounds[0] > bounds[2]
        or bounds[1] > bounds[3]
        or graph_bounds[0] > bounds[0]
        or graph_bounds[1] > bounds[1]
        or graph_bounds[2] < bounds[2]
        or graph_bounds[3] < bounds[3]
        or Path(value["file"]).name != value["file"]
        or not isinstance(value["id"], str)
        or not isinstance(value["url"], str)
        or not isinstance(value["cost_profile"], str)
        or not isinstance(value["sha256"], str)
        or len(value["sha256"]) != 64
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
