# Architecture

MODO is a headless mathematical engine. It owns:

- optimization objectives and algorithms
- road-region semantics
- the routing contract required to evaluate travel times
- result provenance

The static-road optimizer accepts either a caller's weighted NetworkX graph or
a compact graph compiled from it. Both implement the same exact contract. MODO
does not bundle or maintain a national road network.

The compact graph can retain every origin's travel-time field or aggregate one
field at a time in memory-bounded mode. Both return the same exact objectives
and regions. Memory-bounded selected-point evaluation performs a reverse-graph
shortest-path search on demand.

The authoritative result is the qualifying set of road vertices described by
the [mathematical model](model.md). A representative coordinate is a
convenience, and any polygon is a presentation derived outside MODO.

## Engine contract

For one set of origins and one routing context, MODO's engine contract is to:

- compute the total-time and maximum-time results from the same per-origin
  travel-time fields
- return the complete road-vertex region for each objective and tolerance
- evaluate any caller-selected coordinate, after road-network snapping, and
  return its travel time from every origin
- recompute deterministically when origins, tolerance, road snapshot, cost
  profile, or time context changes

MODO does not retain application or session state between evaluations. The
routing context uses static costs today, but must allow future depart-at and
arrive-by traffic costs. The current NetworkX API implements the static contract
through a reusable `StaticRoadAnalysis`. Time-dependent routing remains a
future capability.

## fairway boundary

fairway is the dashboard that presents modo's results, with two parts:

- The browser collects inputs and visualizes results.
- The backend geocodes inputs, builds and validates immutable versioned road
  snapshots, operates the routing runtime, invokes MODO, and manages deployment
  and privacy.

fairway decides when changed inputs require a new evaluation and how to display
the results. MODO defines and performs the calculations.

The road data belongs to the backend runtime, not the browser, MODO package, or
source repository. The initial application should use one backend process and
load the graph once. A separate routing service or cache should be added only
after a demonstrated need.

Every published or persisted result must identify at least the road snapshot,
routing cost profile, and MODO version that produced it. Time-dependent results
must also identify the relevant departure or arrival time.
