# HTTP API

ARGUS serves JSON under `/api`. All responses include `X-Request-ID`; errors use `{error, code, request_id}`. Public reads are briefly cacheable. Admin responses are not cached and require `X-Argus-Token`.

## Service endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Process liveness only; does not touch storage |
| GET | `/api/ready` | SQLite readiness plus technology, snapshot, source-failure, and discovery counts |

## Public endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/overview` | Current active-technology estimates and weekly/monthly movement |
| GET | `/api/v1/activity` | Twelve most recent collection/publication runs |
| GET | `/api/v1/technologies` | Active technology profiles |
| GET | `/api/v1/technologies/{id}` | One active profile |
| GET | `/api/v1/technologies/{id}/snapshots` | Ordered history |
| GET | `/api/v1/technologies/{id}/snapshots/current` | Current estimate |
| GET | `/api/v1/technologies/{id}/snapshots/{week}` | Stable historical estimate (`YYYY-MM-DD`) |
| GET | `/api/v1/technologies/{id}/evidence?dimension=&week=` | Public, non-excluded evidence; defaults to the current week |
| GET | `/api/v1/technologies/{id}/coverage` | Current coverage and source warnings |
| GET | `/api/v1/methodology` | Versioned definitions, phases, limitations, and tooltip glossary |
| GET | `/api/v1/sources/disclosure` | Source classes and weighting interpretation |

## Admin endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/admin/overview` | Portfolio, run, and source operational summary |
| GET | `/api/v1/admin/runs[?technology_id=]` | Run history |
| GET | `/api/v1/admin/runs/{id}` | One run |
| GET | `/api/v1/admin/evidence[?technology_id=&review_status=]` | Review ledger |
| POST | `/api/v1/admin/evidence/{id}/review` | Set `unreviewed`, `approved`, or `excluded` |
| GET/POST | `/api/v1/admin/technologies` | List all profiles or create a draft |
| POST | `/api/v1/admin/technologies/enrich` | Prepare an editable draft profile from an administrator-provided name and description; requires `OPENROUTER_API_KEY` |
| POST | `/api/v1/admin/technologies/{id}/validate` | Validate draft lifecycle state |
| POST | `/api/v1/admin/technologies/{id}/backfill` | Collect a 52-week baseline and current evidence |
| POST | `/api/v1/admin/technologies/{id}/activate` | Publish a validated profile with snapshots |
| POST | `/api/v1/admin/technologies/{id}/cadence` | Set `weekly` or `quarterly` analysis |
| POST | `/api/v1/admin/refresh` | Collect weekly and due-quarterly technologies, or one supplied `technology_id` |
| GET | `/api/v1/admin/sources` | Source health |
| GET | `/api/v1/admin/audit?limit=` | Audit events, capped at 500 |
| GET | `/api/v1/admin/discovery[?status=]` | Discovery runs and suggestions |
| POST | `/api/v1/admin/suggestions/{id}/accept` | Convert a suggestion to a draft technology |
| POST | `/api/v1/admin/suggestions/{id}/dismiss` | Retain and dismiss a suggestion |

Mutating operations are deliberately not retried by the browser client. Full refreshes are mutually exclusive and return HTTP 409 when one is already running.
