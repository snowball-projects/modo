# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
