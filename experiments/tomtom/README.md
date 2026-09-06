# TomTom capability check

This optional, non-production probe verifies the provided modo key against
Routing and Calculate Reachable Range. It sends exactly two requests using
public Chicago street intersections: one short route and one five-minute range,
both with `traffic=true` and `departAt=now`. It never calls Matrix Routing.

From the repository root, set `TOMTOM_API_KEY` in the environment or copy
`.env.example` to the ignored `.env`, then run:

```sh
python experiments/tomtom/probe.py
```

The script does not execute `.env` contents, follow redirects, or retry. Each
request has a 20-second socket timeout and a 1 MiB response limit. Output contains
only status, elapsed time, and route/boundary counts. It does not print the key,
request URL, provider error body, travel data, or returned geometry. Do not save
raw provider responses or use personal locations for this check.

On September 6, 2026, both requests returned HTTP 200: the route contained one
route (0.239 seconds), and the range contained 50 boundary points (0.146 seconds).
These single observations establish endpoint access, not a latency guarantee.

The [current pricing page](https://docs.tomtom.com/pricing) advertises 20,000
free Routing requests monthly. Account entitlements, shared usage, and billing
settings still govern actual availability; inspect them before ongoing use.
This check did not enable billing or inspect account-level limits.

[Calculate Reachable Range](https://docs.tomtom.com/routing-api/documentation/tomtom-maps/v1/calculate-reachable-range)
returns a polygon boundary, not the complete exact road-vertex set used by modo.
Successful calls do not establish rights to extract or redistribute traffic
data. Production stays on its identified static Chicago graph until an approach
preserves its exact contract or the founder approves a clearly labeled
approximation with an operating budget and provider privacy/terms review.
