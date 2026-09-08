# modo working agreements

## Scope and sources

- Read `README.md` for setup, `docs/model.md` for mathematical contracts,
  `docs/architecture.md` for boundaries, and `SERVICE.md` for the hosted policy.
- Follow the provisional [snowball principles](https://snowball-projects.github.io/principles/).
  Keep the simplest reliable design; measure before adding infrastructure.
- Keep the public interface minimax-only with a fixed 60-second region.
  Library APIs may retain other objectives. Experiments are not production.
- Keep modo and fairway independent. Preserve exact results over the named
  graph, complete regions, explicit provenance, and clear failures at limits.

## Development and verification

- Use Python 3.11+ and the checked-in `uv.lock`; install with
  `uv sync --extra app --extra test --locked`.
- Before shipping, run `uv run --locked ruff check .`,
  `uv run --locked ruff format --check .`, `uv run --locked python -m pytest tests experiments`,
  and `uv run --locked python -m build`.
- For touched experiments, run their documented checks. For browser changes,
  run `node --check` on changed JavaScript and inspect keyboard/mobile behavior.
- Snapshot changes also require `scripts/validate_snapshot.py`; production
  snapshots must remain checksummed, directed, and positively weighted.
- `.github/workflows/ci.yml` defines supported runtime and SciPy-floor checks;
  `render.yaml` defines deployment. Keep runtime pins and lockfiles consistent.
- Preserve existing local work. Remove code or tests only when their purpose
  is demonstrably obsolete; keep regression and backend-equivalence coverage.

## Privacy, attribution, and maintenance

- Never commit or print `.env` values, credentials, personal locations, or
  benchmark results. Keep `.env.example` to empty variable declarations.
- No accounts, analytics, advertising, or stored origin coordinates. Document
  provider disclosures and limits before introducing an external service.
- Do not run bulk provider calls or expand paid infrastructure without an
  explicit budget. A provider key does not establish data reuse rights.
- Write `snowball` in lowercase. Credit software to snowball; Nas Delevski is
  its founder. Do not add AI-builder labels or change product direction by assumption.
- Preserve MIT software licensing and separate road-data/Leaflet notices;
  `LICENSE`, `NOTICE`, and `CONTRIBUTING.md` are authoritative.
- Use regular hyphens instead of em dashes. Keep public copy terse and honest.
- Keep this file concise and current. Link to canonical documentation instead
  of duplicating it. `CLAUDE.md` imports this file as the shared instruction source.
