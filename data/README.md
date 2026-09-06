# Road snapshot

`src/modo/snapshots.json` is modo's packaged, versioned artifact catalog. The
fetch script and web runtime use it as the canonical binding between a snapshot
identifier, file, release URL, checksum, cost profile, supported core, and
graph bounds.

`chicago-static-v1.npz` is an immutable compact road graph built from
OpenStreetMap data. It is distributed as a GitHub release artifact and is not
tracked in this source repository. modo currently reuses the identical
checksummed artifact originally published for fairway.

- Snapshot: `chicago-static-v1`
- Cost profile: `static-free-flow-seconds-v1`
- Created: 2026-08-23 with OSMnx 2.1.1
- Graph bounds: 41.8500077 to 42.1799662 latitude, -88.1399989 to -87.6012705 longitude
- Supported core: 41.868 to 42.162 latitude, -88.116 to -87.6253 longitude
- Graph: 63,413 vertices and 169,189 directed source edges
- Artifact: 2,603,992 bytes
- SHA-256: `c095461796adda233387c66f5b32c433c0d8a76d184902daf848fed1a3f2d39c`
- Source: OpenStreetMap contributors
- Data license: Open Database License 1.0

Build a compact asset from an OSMnx-style GraphML export with:

```sh
python scripts/build_snapshot.py local-chicago.graphml data/roads.npz \
  --source-url https://example.org/immutable-source.graphml
```

The source graph must be directed and every edge must have an explicit,
finite, positive `travel_time`. The builder writes `roads.npz.build.json` with
source and artifact checksums, tool versions, graph counts, bounds, and
available GraphML creation metadata. Keep that manifest with every future
published artifact, along with the extract geometry, OpenStreetMap source date,
road filter, speed assumptions, and a supported core strictly inside the graph
bounds. `scripts/validate_snapshot.py` rechecks the catalog checksum,
structure, direction, costs, and declared graph bounds.

The Chicago artifact predates the build-manifest requirement. Its catalog and
runtime provenance are verified, but the repository does not contain enough
source acquisition detail to reproduce it byte for byte. Replace it rather
than inferring missing build inputs when Chicago is rebuilt with a routing
halo.

The supported core is inset by approximately two kilometers on every side of
the existing graph. This provides an honest routing halo for current service
inputs but does not claim equivalence to a graph containing roads beyond the
artifact. Catalog validation rejects future snapshots whose core touches any
graph boundary.

Copyright OpenStreetMap contributors. OpenStreetMap data is available under the
[Open Database License](https://www.openstreetmap.org/copyright).
