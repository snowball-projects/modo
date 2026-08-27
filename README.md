# Multi Origin Distance Optimizer

`modo` is a headless Python library that optimizes geographic and static-road
destinations for multiple origins.

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
NetworkX road graph and exactly evaluates all mutually reachable vertices. Its
`total` mode minimizes combined travel time, while its `maximum` mode minimizes
the longest individual trip. Graph nodes need `x` longitude and `y` latitude
attributes. Edges use `travel_time` seconds by default.

```python
from modo import optimize_coordinates

result = optimize_coordinates(graph, origin_coordinates, "maximum",
                              tolerance_seconds=60)
```

`optimize_vertices` is the lower-level equivalent for origins that are already
snapped to graph vertex IDs. For the `total` objective, tolerance is
per-traveler average slack, so 60 seconds permits
`60 * len(origin_coordinates)` additional total seconds.

`result.region` contains every vertex within the tolerance. `result.vertex` and
`result.coordinate` provide one exact optimum when a single location is useful.

The current API receives the weighted graph as its first argument. It does not
download road data or call routing services. The [mathematical model](docs/model.md)
defines the objectives and region semantics.

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
