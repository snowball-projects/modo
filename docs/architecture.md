# Architecture

modo has two layers:

- The Python package calculates geographic centers, exact static-road
  objectives, near-optimal vertex sets, travel times, and road-vertex paths.
- The web interface minimizes the longest drive and shows the fixed one-minute
  near-optimal region. It has no venue search or total-time control.

## Interface contract

One Python WSGI process serves the browser assets and JSON API. It loads one
immutable compact road snapshot on first use. For each request it:

1. rejects origins outside the snapshot's supported core, then snaps between
   two and 32 confirmed origins to stored road vertices;
2. calculates the maximum-time objective over every mutually reachable vertex;
3. returns the complete vertex set within 60 seconds of the optimum;
4. reconstructs one shortest road-vertex path from every origin to a
   deterministic exact optimum inside that set; and
5. returns the snapshot, cost profile, package version, and tolerance with the
   result.

The browser uses one color per origin across its input, pin, route, and travel
time. Pins remain at confirmed coordinates; dotted connectors show road-vertex
snaps. The region is drawn as separate road points so disconnected components
are not joined into invented coverage.

The browser sends address queries directly to Photon. modo receives only
confirmed coordinates and retains no application state between evaluations.

## Engine contract

The NetworkX reference backend and compact sparse backend implement the same
optimization and route contracts. For one graph and origin set they can:

- compute total-time or maximum-time results from reusable shortest-path
  fields;
- return the complete road-vertex region for a nonnegative objective
  tolerance;
- evaluate travel times at any mutually reachable stored vertex; and
- return one shortest road-vertex path per origin to that vertex.

The total-time objective is a library API, not a web interface option.

Compact snapshots retain vertex coordinates and weighted adjacency, not full
OpenStreetMap edge geometry. Routes therefore show the chosen vertex sequence
but may omit curves between vertices.

## Data and deployment

Road data is a versioned release artifact. Its catalog records the URL,
checksum, bounds, and cost profile. The fetch script verifies the checksum
before installation, and the runtime verifies it again before loading the
graph or reporting provenance. The initial static Chicago snapshot is described
in the [data notes](../data/README.md).

`render.yaml` and `uv.lock` reproduce the hosted service. No database or
separate routing service is required.

## Geographic expansion

Lower-48 coverage should use immutable regional snapshots, each with an inner
supported core and outer routing halo. Build and benchmark each snapshot
offline, then deploy only bundles within measured memory and latency limits.

Requests must fit one active core. Reject cross-region inputs until prebuilt
partition and boundary routing can preserve the exact-over-the-named-graph
contract. Runtime road downloads or routing API calls are not interim coverage.

## fairway boundary

fairway ranks a finite golf-course catalog; modo searches mutually reachable
road vertices. fairway may reuse package-level routing code, but the web
applications remain independent and do not call one another.
