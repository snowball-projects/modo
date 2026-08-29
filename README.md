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

Use one analysis to reuse the same shortest-path searches across objectives and
selected destinations:

```python
from modo import analyze_coordinates

analysis = analyze_coordinates(graph, origin_coordinates)
total = analysis.optimize("total", tolerance_seconds=60)
maximum = analysis.optimize("maximum", tolerance_seconds=60)
selected = analysis.travel_times_at_coordinate(selected_coordinate)
```

`total.region` and `maximum.region` contain the complete qualifying vertex
sets. `selected.travel_times_seconds` contains one travel time per origin.

For a smaller static runtime, compile the caller's graph into a versioned,
compressed asset and load it without rebuilding a NetworkX graph:

```python
from modo import CompactRoadGraph

roads = CompactRoadGraph.from_networkx(graph)
roads.save("roads.npz")

roads = CompactRoadGraph.load("roads.npz")
analysis = roads.analyze_coordinates(origin_coordinates)
total = analysis.optimize("total", tolerance_seconds=60)
region_coordinates = roads.coordinates(total.region)
```

Saved compact graphs support integer and string vertex IDs. The compact and
NetworkX analyses use the same result, tolerance, and tie-breaking semantics.

`optimize_vertices` is the lower-level equivalent for origins that are already
snapped to graph vertex IDs. Tolerance is direct slack on the selected
objective, so 60 seconds permits one additional minute of combined time in
`total` mode or one additional minute on the longest trip in `maximum` mode.

`result.region` contains every vertex within the tolerance. `result.vertex` and
`result.coordinate` provide one exact optimum when a single location is useful.
`result.region_excess_seconds` maps every region vertex to the number of seconds
its objective exceeds the optimum.

The current API receives the weighted graph as its first argument. It does not
download road data or call routing services. The [mathematical model](docs/model.md)
defines the objectives and region semantics. The [architecture](docs/architecture.md)
defines the boundary between MODO and the future Fairway Dashboard.

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

## License

MODO is a snowball project licensed under the [Apache License 2.0](LICENSE).
See [NOTICE](NOTICE) for attribution, [CONTRIBUTING.md](CONTRIBUTING.md) before
submitting work, and snowball's [licensing and identity
policy](https://snowball-projects.github.io/licensing/).
