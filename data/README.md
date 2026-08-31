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
- Bounds: 41.8500077 to 42.1799662 latitude, -88.1399989 to -87.6012705 longitude
- Graph: 63,413 vertices and 169,189 directed source edges
- Artifact: 2,603,992 bytes
- SHA-256: `c095461796adda233387c66f5b32c433c0d8a76d184902daf848fed1a3f2d39c`
- Source: OpenStreetMap contributors
- Data license: Open Database License 1.0

Build an equivalent compact asset from an OSMnx-style GraphML export with:

```sh
python scripts/build_snapshot.py local-chicago.graphml data/chicago-static-v1.npz
```

Copyright OpenStreetMap contributors. OpenStreetMap data is available under the
[Open Database License](https://www.openstreetmap.org/copyright).
