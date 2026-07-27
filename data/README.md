# Data directories

ARGUS keeps only the data directories used by the current application.

| Directory | Purpose | Git policy |
|---|---|---|
| `fixtures/` | Reviewed public-metadata bootstrap cache and fixture notes | Committed |
| `argus.sqlite3` | Local operational state: technologies, runs, evidence, reviews, discovery, and audit events | Ignored |
| `argus.sqlite3-wal` / `-shm` | SQLite WAL runtime files | Ignored |

Evidence retains source, URL, publication date, claim classification, and weight.
The current collector does not store article bodies or raw provider responses.

Do not commit scraped article bodies, tokens, API responses containing personal data, or production exports.
