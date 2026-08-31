import json

import pytest

from modo.snapshots import DEFAULT_CATALOG, load_catalog


def test_loads_published_catalog():
    catalog = load_catalog(DEFAULT_CATALOG)
    assert len(catalog) == 1
    assert catalog[0].identifier == "chicago-static-v1"
    assert catalog[0].contains([(41.8781, -87.6298)])
    assert not catalog[0].contains([(42.18, -87.8)])
    assert catalog[0].sha256 == (
        "c095461796adda233387c66f5b32c433c0d8a76d184902daf848fed1a3f2d39c"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"snapshots": []},
        {
            "snapshots": [
                {
                    "id": "bad",
                    "file": "../bad.npz",
                    "url": "https://example.test/roads",
                    "sha256": "short",
                    "cost_profile": "test",
                    "core_bounds": [0, 0, 1, 1],
                    "graph_bounds": [0, 0, 1, 1],
                }
            ]
        },
    ],
)
def test_rejects_invalid_catalog(tmp_path, change):
    value = {"schema_version": 1, "snapshots": []}
    value.update(change)
    path = tmp_path / "snapshots.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="invalid road snapshot catalog"):
        load_catalog(path)
