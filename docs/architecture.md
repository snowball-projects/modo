# Architecture

MODO is a headless mathematical engine. It owns:

- optimization objectives and algorithms
- road-region semantics
- the routing contract required to evaluate travel times
- result provenance

The current static-road optimizer accepts a weighted NetworkX graph from its
caller. It is the exact reference implementation of that contract. MODO does
not bundle or maintain a national road network.

The authoritative result is the qualifying set of road vertices described by
the [mathematical model](model.md). A representative coordinate is a
convenience, and any polygon is a presentation derived outside MODO.

## Dashboard boundary

A future Dashboard has two parts:

- The browser collects inputs and visualizes results.
- The backend geocodes inputs, builds and validates immutable versioned road
  snapshots, operates the routing runtime, invokes MODO, and manages deployment
  and privacy.

The road data belongs to the backend runtime, not the browser, MODO package, or
source repository. The initial application should use one backend process and
load the graph once. A separate routing service or cache should be added only
after a demonstrated need.

Every published or persisted result must identify at least the road snapshot,
routing cost profile, and MODO version that produced it. Time-dependent results
must also identify the relevant departure or arrival time.
