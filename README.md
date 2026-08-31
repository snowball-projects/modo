# modo

`modo` is an interactive map and Python library for multi-origin road meeting
regions. Confirm two or more origins and the map shows every stored road vertex
where the longest individual drive is within one minute of the shortest
possible longest drive.

[Founder-directed. Built entirely by AI agents.](https://snowball-projects.github.io/licensing/#how-snowball-is-built)

The interface has one objective and one fixed tolerance. Each confirmed origin
keeps its own color across the input, map pin, route, and travel time. Routes
converge at one deterministic exact optimum inside the region, but the region
is the primary result. Pins stay at confirmed coordinates, with dotted lines
showing any snap to the nearest stored road vertex where routing begins.

The initial interface covers a Chicago-area static road snapshot. It does not
use live or historical traffic, recommend a venue, or imply that a displayed
road point is safe to stop at. Route lines connect stored road vertices and can
omit detailed curves between them.

## Run the interface locally

Python 3.11 or newer is required.

```sh
python -m pip install uv==0.12.6
uv sync --extra app --extra test --locked
uv run --locked python scripts/fetch_snapshot.py
uv run --locked gunicorn modo.web:application
```

Open `http://127.0.0.1:8000`. Address suggestions come from the public Photon
service. Coordinates can also be confirmed as `latitude, longitude`.

The included `render.yaml` describes a separate free-plan Render web service.
It is deployment-ready, but the repository does not claim that a service is
live until snowball publishes one.

## Python library

The public app is intentionally minimax-only. The package retains its general
geographic functions and existing total-time road API for library users.

```python
from modo import CompactRoadGraph

roads = CompactRoadGraph.load("roads.npz")
analysis = roads.analyze_coordinates(origin_coordinates)
result = analysis.optimize("maximum", tolerance_seconds=60)
routes = analysis.routes(result.vertex)
region_coordinates = roads.coordinates(result.region)
```

`result.region` is the complete qualifying road-vertex set.
`result.region_excess_seconds` reports how far each vertex is above the exact
optimum. `analysis.routes` returns one shortest road-vertex path per origin.

The lower-level NetworkX backend provides the same result and route contracts
through `analyze_coordinates` and `analyze_vertices`. Compact snapshots can use
`retain_distances=False` to stream shortest-path fields when memory is tighter.

The package also keeps `geographic_median`, `minimax_center`, and the existing
`total` road objective. The [mathematical model](docs/model.md) defines their
semantics. The [architecture](docs/architecture.md) defines the boundary
between the library, the modo interface, and fairway.

## Checks

```sh
uv run --locked ruff check .
uv run --locked python -m pytest
uv run --locked python -m build
```

The test suite uses synthetic fixtures and does not require geographic data or
external services.

## License

modo is a snowball project licensed under the [Apache License 2.0](LICENSE).
The OpenStreetMap-derived road snapshot is separately available under the Open
Database License. See [data/README.md](data/README.md), [NOTICE](NOTICE),
[CONTRIBUTING.md](CONTRIBUTING.md), and the [hosted-service policy](SERVICE.md).
The locally served Leaflet stylesheet remains under BSD-2-Clause; see
[LEAFLET-LICENSE.txt](src/modo/static/LEAFLET-LICENSE.txt).
