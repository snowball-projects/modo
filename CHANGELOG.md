# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.4] - 2026-09-06

### Added

- Added deterministic time-dependent minimax and optional Valhalla benchmark
  experiments without adding either engine or traffic data to production.
- Added a two-request TomTom capability probe; route and reachable-range access
  succeeded with the configured key while production remains exact and static.

### Security

- Parse pathological JSON numbers as bad requests and load a verified road
  snapshot from the same open file handle.
- Enforce HTTPS on every snapshot redirect, a whole-download deadline, and an
  exact declared content length.

### Changed

- Fail clearly when the hosted bounded search exhausts its work budget instead
  of falling back to a full-graph scan, and reuse its predecessor labels for
  route reconstruction without a second graph traversal.
- Consolidate agent instructions through `AGENTS.md` and a `CLAUDE.md` import.
- Collect core and experiment tests together without module-name collisions.

### Fixed

- Include snapshot tools and linked documentation in source distributions so
  their tests and setup instructions work outside a Git checkout.
- Credit the locally served Leaflet JavaScript alongside its stylesheet and
  align the model's implementation description with the bounded search.

## [0.3.3] - 2026-08-31

### Changed

- Streamed only the maximum objective in the hosted calculation, deduplicated
  identical snapped origins, and bounded region and route materialization.
- Added a budgeted exact simultaneous-frontier fast path for local groups with
  an exact streaming fallback when the frontier grows.
- Added source and artifact manifests for future builds, a production snapshot
  validator, and a live-artifact CI smoke check.
- Inset the supported Chicago core by about two kilometers to preserve a
  routing halo and reduced the maximum road snap from five kilometers to one.
- Updated the hosted runtime to Python 3.14 and Gunicorn 26.
- Added an identifier-free global evaluation rate budget for the free service.
- Served Leaflet JavaScript locally and removed executable CDN permission from
  the content security policy.

### Fixed

- Stopped address-field typing and unchanged confirmed origins from repeating
  calculations.
- Added a screen-reader result location, corrected the Origins heading
  contrast, and rejected undirected or implicitly weighted production data.

## [0.3.2] - 2026-08-31

### Changed

- Removed the redundant best-time summary card while retaining per-origin
  times, routes, and the one-minute region.
- Defined regional snapshots with routing halos as the next geographic
  expansion boundary.

## [0.3.1] - 2026-08-31

### Security

- Restricted snapshot downloads to verified HTTPS metadata, bounded their
  size and duration, and rejected unsafe redirects.
- Added a content security policy, transport and browser security headers,
  JSON-only evaluation requests, and bounded route responses.
- Pinned CI actions, disabled persisted checkout credentials, and reproduced
  deployments from the checked-in dependency lock.

### Fixed

- Added correct `HEAD` responses and `Allow` headers for unsupported methods.
- Updated the test dependency with a disclosed vulnerability and improved
  keyboard focus, color contrast, and result announcements.

## [0.3.0] - 2026-08-30

### Added

- A minimax-only web interface with persistent origin colors, dynamic pins,
  one-minute road regions, and colored routes.
- On-demand shortest road-vertex path reconstruction for both road backends.
- A checksummed Chicago snapshot catalog, fetch tooling, hosted-service policy,
  and free-plan Render blueprint.
- A locally served Leaflet stylesheet so map layout does not depend on CDN CSS.

### Changed

- Made the one-minute maximum-time region the public product direction while
  retaining total-time APIs for library compatibility.

## [0.2.0] - 2026-08-29

### Fixed

- Kept compact and NetworkX results equivalent at floating-point tolerance
  boundaries and for tied mixed-type vertex IDs.
- Restored compact analysis compatibility with SciPy 1.12 and aligned input
  validation across both road backends.

### Added

- `minimax_center` for the WGS84 geodesic minimax center.
- Exact static-road optimization from coordinates or vertices for total and
  maximum travel time.
- An exact memory-bounded compact analysis mode that does not retain the full
  origin-by-vertex distance matrix.
- The architecture boundary between modo and fairway.

### Changed

- Relicensed modo from MPL-2.0 to Apache-2.0 and credited its public metadata
  to snowball.
- Changed total-time tolerance from per-traveler average slack to direct slack
  on the combined-time objective.
- Vectorized compact-graph snapping and objective selection, and removed the
  objective scan's origin-by-vertex matrix copy.

## [0.1.0] - 2026-08-13

### Added

- Initial `geographic_median` function with WGS84 geodesic distances.
- Input validation and explicit one-point and two-point behavior.
