# Architecture

modo has two deliberately small layers:

- The Python package calculates geographic centers, exact static-road
  objectives, near-optimal vertex sets, travel times, and road-vertex paths.
- The web interface presents one product opinion: minimize the longest drive
  and show the fixed one-minute near-optimal region.

The interface is not a generic destination finder. It has no venue categories,
rankings, booking, accounts, advertising, analytics, or total-time control.

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

The browser gives each origin a persistent color and uses it for the input,
pin, route, and travel time. The pin remains at the user-confirmed coordinate;
a dotted connector shows any snap to the stored road vertex where the route
begins. It draws the region as overlapping translucent road points. It does not
wrap disconnected points in a polygon, which would invent coverage between
them.

Origin addresses are converted to coordinates in the browser through Photon.
Only confirmed coordinates are sent to modo. The process does not use a
database or retain application state between evaluations.

## Engine contract

The NetworkX reference backend and compact sparse backend implement the same
optimization and route contracts. For one graph and origin set they can:

- compute total-time or maximum-time results from reusable shortest-path
  fields;
- return the complete road-vertex region for a nonnegative objective
  tolerance;
- evaluate travel times at any mutually reachable stored vertex; and
- return one shortest road-vertex path per origin to that vertex.

The total-time API remains available to existing library consumers. It is not
part of modo's public web experience or product direction.

Compact snapshots retain vertex coordinates and weighted adjacency, not full
OpenStreetMap edge geometry. A displayed route therefore truthfully represents
the chosen sequence of road vertices but can omit a curve between adjacent
vertices. Preserving detailed edge geometry would require a new snapshot
format and is not implied by the current result.

## Data and deployment

The road data is a separately versioned release artifact, not source code. The
catalog binds an identifier to its URL, checksum, supported core, graph bounds,
and cost profile. The fetch script verifies the checksum before installing an
artifact, and the runtime verifies it again before loading the graph or claiming
catalog provenance. The initial snapshot uses static free-flow travel times and
supports the Chicago area described in [the data notes](../data/README.md).

`render.yaml` defines one self-contained free-plan service. A new deployment
can use that blueprint if the owner's Render account permits another free web
service. Its Python environment is reproduced from the checked-in `uv.lock`.
The application does not require a separate routing service or database.

## fairway boundary

fairway is a separate golf-course chooser. It ranks a finite catalog of real
courses for a group of golfers. modo instead searches every mutually reachable
road vertex and returns a mathematical region.

fairway may reuse stable package-level routing or matrix capabilities, but it
does not call the modo web application and modo does not own course discovery,
golf filters, course data, or course ranking.
