# Hosted service

This policy applies to any official snowball deployment of modo. Operators of
independent deployments set their own service policies.

## Behavior

- modo has no accounts, advertising, or analytics.
- Confirmed origin coordinates are sent to modo for one calculation. They are
  not written to a database or retained as application state.
- Results use an identified static road snapshot and cost profile. Traffic,
  scheduled departure, and scheduled arrival are not supported.
- The displayed region contains stored road vertices, not venue
  recommendations or assurances that a location is safe to stop at.
- Route lines connect stored road vertices and can omit detailed curves between
  adjacent vertices.

## Browser services

- Address text goes directly from the browser to the public Photon service.
  Photon receives the query and ordinary request metadata such as the browser's
  IP address. Manually entered coordinates do not go to Photon.
- Leaflet JavaScript loads from unpkg; modo serves its Leaflet stylesheet
  locally. Map tiles load directly from OpenStreetMap. Those external services
  receive ordinary request metadata, and tile requests identify the viewed map
  area.

## Current limits

The interface accepts between two and 32 origins and at most 32 KiB of JSON.
Coordinates must be inside the active snapshot's supported core and within 5
km of one of its road vertices. The initial snapshot covers the Chicago area
specified in `src/modo/snapshots.json`.

The fixed one-minute region may contain at most 5,000 road vertices. modo
rejects a larger result instead of truncating the mathematical region.

## Acceptable use

Use the service for ordinary interactive meeting-region calculations. Do not
intentionally disrupt it, evade its limits, send automated bulk traffic,
access another person's data, or use it in violation of applicable law or
another person's rights. Good-faith security research is welcome when it
avoids harm and is reported privately.

snowball may reject, limit, or block abusive traffic. The service is provided
without a guarantee of availability.

Report security issues through GitHub's private vulnerability reporting form
for the modo repository.
