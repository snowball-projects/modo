# Hosted service

This policy applies to any official snowball deployment of modo. Operators of
independent deployments set their own service policies.

## Behavior

- modo has no accounts, advertising, or analytics.
- Confirmed coordinates are used for one calculation and are not stored.
- Results use an identified static road snapshot and cost profile. Traffic,
  depart-at, and arrive-by are not supported.
- Results are stored road vertices, not venues or assurances of a safe stopping
  place. Routes may omit curves between adjacent vertices.

## Browser services

- Address text goes directly from the browser to the public Photon service.
  Photon receives the query, IP address, and ordinary request metadata.
  Manually entered coordinates do not go to Photon.
- Leaflet JavaScript loads from unpkg and map tiles from OpenStreetMap. Both
  receive IP and request metadata; tile requests reveal the viewed map area.

## Current limits

The interface accepts between two and 32 origins and at most 32 KiB of an
`application/json` request. Coordinates must be inside the active snapshot's
supported core and within 5 km of one of its road vertices. The initial
snapshot covers the Chicago area specified in `src/modo/snapshots.json`.

The one-minute region is limited to 5,000 vertices and returned routes to
100,000 vertices in total. modo rejects larger results rather than truncating
them.

## Acceptable use

Use the service for ordinary interactive meeting-region calculations. Do not
intentionally disrupt it, evade its limits, send automated bulk traffic, or
use it in violation of law or another person's rights. Report good-faith
security research privately and avoid harm.

snowball may reject, limit, or block abusive traffic. The service is provided
without a guarantee of availability.

Report security issues through GitHub's private vulnerability reporting form
for the modo repository.
