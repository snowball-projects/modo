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
2. deduplicates identical snapped vertices and runs an exact, memory-budgeted
   simultaneous frontier, failing clearly if the group exceeds that budget;
3. returns the complete vertex set within 60 seconds of the optimum;
4. reconstructs one shortest road-vertex path from predecessor labels retained
   by that same bounded search; and
5. returns the snapshot, cost profile, package version, and tolerance with the
   result.

The browser uses one color per origin across its input, pin, route, and travel
time. Pins remain at confirmed coordinates; dotted connectors show road-vertex
snaps. The region is drawn as separate road points so disconnected components
are not joined into invented coverage.

The browser sends address queries directly to Photon and calculates only when
the confirmed origin signature changes. modo receives only confirmed
coordinates and retains no application state between evaluations.
Anonymous evaluation requests share an identifier-free process token bucket so
one client cannot continuously occupy the free service's only worker.

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

The simultaneous frontier stops only after every label through the optimum
plus 60 seconds is settled. Its label and heap budgets never truncate or
approximate a result. A request that exceeds them fails instead of starting a
full-graph fallback.

Compact snapshots retain vertex coordinates and weighted adjacency, not full
OpenStreetMap edge geometry. Routes therefore show the chosen vertex sequence
but may omit curves between vertices.

## Data and deployment

Road data is a versioned release artifact. Its catalog records the URL,
checksum, bounds, and cost profile. The fetch script verifies the checksum
before installation. CI and the runtime additionally validate directedness,
positive edge costs, structure, and declared graph bounds before reporting
provenance. Future builds emit a checksummed provenance manifest. The initial
static Chicago snapshot is described in the [data notes](../data/README.md).
Its supported core is inset from the graph boundary; the halo reduces boundary
exposure without claiming equivalence to roads outside the named graph.

`render.yaml` and `uv.lock` reproduce the hosted service. No database or
separate routing service is required.

## Geographic expansion

Any lower-48 static fallback should use immutable regional snapshots, each with
an inner supported core and outer routing halo. Build and benchmark each
snapshot offline, then deploy only bundles within measured limits.

Requests must fit one active core. Reject cross-region inputs until prebuilt
partition and boundary routing can preserve the exact-over-the-named-graph
contract. Runtime road downloads are not interim coverage.

An isolated [browser-routing experiment](../experiments/browser-routing/README.md)
tests exact static Worker delivery without changing the production design.

## Free-first rollout

Keep the current regional Python service as the deployed baseline. Render's free
web service currently supplies 512 MB RAM and 750 shared instance-hours per
workspace, but sleeps after 15 idle minutes. That is appropriate for measured
regional bundles, not an assumed lower-48 monolith.

The browser Worker experiment remains a traffic-unaware fallback. It moves
immutable road tiles to object storage so the browser owns calculation memory.
Cloudflare R2 currently includes 10 GB-month of Standard storage, 10 million
monthly reads, and free egress; Pages limits individual assets to 25 MiB, so the
shell can live on Pages while graph tiles live in R2. GitHub Pages is suitable
for the shell but caps a published site at 1 GB, so it is not the lower-48 graph
store. These limits were checked on 2026-08-31 and must be checked again before
deployment:

- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/)
- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [Render free-service limits](https://render.com/docs/free)

Do not create an account or publish data until a lower-48 build measures total
compressed size, file count and maximum tile size, cold and warm tile loads,
browser peak memory, latency, caching, snapping, route reconstruction, and
cancellation. If that gate fails, retain regional services.

Traffic-aware lower-48 coverage should use a tiled routing engine or external
provider rather than enlarge the current Python snapshot. A local Valhalla
3.8.3 Chicago probe loaded an 83.5 MB tile extract at about 184 MB peak process
memory. A separate copy-on-write test changed one route from 17.632 to 86.4
seconds at the synthetic peak, and changed its time-dependent matrix from 17 to
86 seconds. The unchanged baseline remained byte-identical.

That proves the engine path, not the data path. Valhalla needs a lawful national
historical or live traffic source. A bounded [TomTom capability
probe](../experiments/tomtom/README.md) on September 6, 2026 confirmed that modo's
key can calculate a traffic-aware route and reachable-range polygon. That
resolves access for those two endpoints, but it does not establish an exact
road-vertex region or a reusable traffic dataset. Mapbox explicitly excludes
its traffic profile from isochrones. Any external provider still needs verified
terms, privacy, failure behavior, and cost; any polygon approximation needs a
separate, explicit product decision.

- [Valhalla traffic experiment](../experiments/routing_engines/README.md)
- [TomTom reachable range](https://docs.tomtom.com/routing-api/documentation/tomtom-maps/v1/calculate-reachable-range)
- [TomTom pricing](https://docs.tomtom.com/pricing)
- [Mapbox traffic-profile limits](https://docs.mapbox.com/help/glossary/routing-profile/)

## fairway boundary

fairway ranks a finite golf-course catalog; modo searches mutually reachable
road vertices. fairway may reuse package-level routing code, but the web
applications remain independent and do not call one another.
