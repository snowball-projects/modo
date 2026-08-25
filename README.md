# Multi Origin Distance Optimizer

`modo` is a headless Python library that optimizes geographic and static-road
destinations for equally weighted origins.

```python
from modo import geographic_median, minimax_center

median = geographic_median([(10.0, 20.0), (12.0, 24.0)])
center = minimax_center([(10.0, 20.0), (12.0, 24.0)])
```

`geographic_median` minimizes the sum of distances. `minimax_center` returns
only the `(latitude, longitude)` center that minimizes the greatest distance,
or equivalently the center of the smallest enclosing geodesic circle.
Coordinates use `(latitude, longitude)` order. Both return a single input as a
float tuple and return the WGS84 geodesic midpoint for two inputs. Empty,
malformed, and out-of-range inputs raise `ValueError`.

The functions target ordinary regional datasets. `minimax_center` uses
deterministic, order-independent starting points. Global inputs are supported
on a best-effort basis, but antipodal and other pathological configurations may
not have a unique answer. In particular, `minimax_center` uses numerical
optimization and can converge to a non-global solution for such inputs.

## Static-road reference optimizer

`optimize_coordinates` snaps `(latitude, longitude)` origins to a weighted
NetworkX road graph, exactly evaluates all mutually reachable vertices, and
returns a representative coordinate plus the near-optimal vertex region. It
supports `total` and `maximum` travel-time objectives. Graph nodes need `x`
longitude and `y` latitude attributes. Edges use `travel_time` seconds by
default.

```python
from modo import optimize_coordinates

result = optimize_coordinates(graph, origin_coordinates, "maximum",
                              tolerance_seconds=60)
```

`optimize_vertices` is the lower-level equivalent for origins that are already
snapped to graph vertex IDs. For the `total` objective, tolerance is
per-traveler average slack, so 60 seconds permits
`60 * len(origin_coordinates)` additional total seconds.

Street addresses are intentionally a product-layer input. That layer validates
and geocodes each address to a coordinate before calling MODO, and can reverse
geocode the result for display.

MODO does not download road data or call routing services. Callers provide the
weighted graph, so the reference optimizer remains deterministic and testable.

## Development

MODO requires Python 3.11 or newer. The lockfile makes the development and CI
environment reproducible:

```sh
python -m pip install uv==0.12.6
uv sync --extra test --locked
uv run --locked ruff check .
uv run --locked python -m pytest
uv run --locked python -m build
```

The standard checks use only synthetic fixtures and do not require external
services or local geographic data.
