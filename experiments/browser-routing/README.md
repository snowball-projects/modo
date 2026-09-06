# Browser-routing experiment

This is a non-production, data-free proof that modo's exact minimax objective
and fixed one-minute region can run in a browser Worker from immutable static
files. It does not change or import the production runtime. Generated graphs,
baselines, summaries, and recorded local results are not committed.

## Offline verification

From the modo repository root:

```sh
uv run --locked pytest experiments/browser-routing/tests
node --check experiments/browser-routing/site/engine.js
node --check experiments/browser-routing/site/worker.js
node --check experiments/browser-routing/site/app.js
```

The test generates a six-vertex directed fixture in a temporary directory. It
checks the build format and hashes, runs both engines through the Worker message
handler under Node, compares their exact outputs with SciPy, rejects an unpinned
manifest, and detects a corrupted array. It needs no browser or network.

## Build and run

The builder accepts any directed modo compact snapshot and a separate case
file. The output directory must be new or empty.

```sh
uv run --locked python experiments/browser-routing/build.py \
  --source data/chicago-static-v1.npz \
  --cases /path/to/cases.json \
  --output experiments/browser-routing/site/generated
uv run --locked python experiments/browser-routing/serve.py \
  --directory experiments/browser-routing/site --port 8765
```

Open `http://127.0.0.1:8765/?case=example`. Cases use source vertex IDs and are
remapped after deterministic row canonicalization:

```json
{
  "schema": "modo-browser-cases-v1",
  "cases": {
    "example": {"origin_ids": ["source-id-1", "source-id-2"]}
  }
}
```

For a cross-origin payload check, serve the generated directory separately:

```sh
uv run --locked python experiments/browser-routing/serve.py \
  --directory experiments/browser-routing/site/generated --port 8766 --cors
```

Then supply `summary`, `full`, and `tiles` query parameters as needed. The
runner also accepts `full_sha256` and `tiles_sha256` to override the manifest
pins recorded in the local build summary.

## Proof retained

The completed Chicago proof compared full-graph and adaptive-tile Workers with
SciPy across clustered, local, extreme, and wide origin sets. Every case
matched the objective, deterministic optimum, region count, and region SHA-256.
The local eight-origin case loaded 6 of 69 tiles and 0.35 MB. The wide
32-origin case correctly expanded to all 69 tiles. A cross-origin payload run
also passed with explicit CORS headers.

The full `modo-browser-csr-v1` payload stores raw little-endian arrays:

- float64 travel seconds for every directed arc;
- uint32 arc targets and CSR row offsets; and
- interleaved E7 int32 latitude and longitude coordinates.

Rows follow modo's deterministic vertex key, so the row number is also the tie
rank. The Worker verifies the pinned root manifest, its schema and dimensions,
every array length and SHA-256, CSR structure, coordinates, and nonnegative
weights before calculation.

Each `modo-browser-tiles-v1` tile retains every outgoing arc from its source
vertices, including arcs into unloaded tiles. The Worker starts with origin
tiles. Once it has a feasible upper bound `U`, it searches each origin through
`U + 60` seconds and loads every tile reachable across a boundary within that
limit. It repeats until no qualifying boundary remains. This preserves the
exact result over the named immutable snapshot and may load every tile.

## Limits

- The checked-in code contains no road data or benchmark results.
- The build summary supplies manifest hashes for this local runner, but it is
  not an authenticity root. A product must embed or otherwise trust the root
  manifest hashes independently of the replaceable payload host.
- Exactness covers only the named source snapshot, not roads outside it.
- Version 1 uses uint16 tile indices and therefore supports at most 65,536
  tiles. A national bundle needs a hierarchical or range-addressed directory.
- The experiment accepts already snapped vertices. Production still needs
  snapping, route reconstruction, progress and cancellation, durable caching,
  accessibility and browser testing, and a graceful unsupported-input path.
- Nationwide delivery is not implied. A lower-48 graph would be roughly
  gigabytes and requires measured partition, cache, and boundary designs.
