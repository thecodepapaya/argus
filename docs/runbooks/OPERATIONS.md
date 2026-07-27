# ARGUS operations runbook

## Service checks

- `GET /api/health` verifies process liveness without touching dependencies.
- `GET /api/ready` verifies SQLite plus active/weekly technology, snapshot,
  source-failure, and open-discovery-suggestion counts.
- Run `python3 scripts/smoke_test.py` against the default local service.
- Use `python3 scripts/operations_status.py` for database-level source and run status.

Every HTTP response includes `X-Request-ID`. API error bodies include the same ID,
an error code, and a safe user-facing message. Server output is newline-delimited
JSON containing request IDs, paths, durations, and exception types. Use the request
ID to correlate a browser-visible error with the corresponding server event.

## Source failures

1. Inspect failures with `python3 scripts/operations_status.py`.
2. Preview retry scope with `python3 scripts/retry_failed_sources.py --dry-run`.
3. Retry failed technologies with `python3 scripts/retry_failed_sources.py`.
4. Re-run `python3 scripts/smoke_test.py` and confirm `/api/ready` is healthy.

Public-source failures produce partial runs rather than discarding successful source
results. A concurrent full refresh is rejected with HTTP 409 so overlapping runs do
not race to publish snapshots.

## Data integrity

ARGUS validates technology metadata, ordered weekly snapshots, feature ranges,
phase names, and evidence identity before loading or writing the fixture. Invalid
fixtures fail startup with a specific validation error instead of serving malformed
pages. SQLite uses WAL mode, bounded busy waits, per-request connections, serialized
writes, and rollback on failed mutations.

## Weekly discovery and lifecycle cadence

1. Run `python3 scripts/discover_technologies.py --dry-run` to verify scope,
   model selection, plateau threshold, and whether an OpenRouter key is detected.
2. Inspect discovery runs and suggestions in `/admin` or
   `GET /api/v1/admin/discovery`.
3. Failed OpenRouter calls are persisted and logged; the scheduler survives the cycle
   and retries at its next interval.
4. Accepting a suggestion creates a draft only. Collect, validate, and activate it
   through the normal technology workflow.
5. Technologies with 12 consecutive productivity-plateau snapshots move to
   quarterly analysis. Use the technology card in `/admin` to restore weekly scope.

See [the discovery guide](../DISCOVERY.md) for credentials and guardrails.

## Recovery

- The committed fixture allows a clean database to bootstrap without network access.
- Operational state lives in `data/argus.sqlite3` locally or the `argus_data` Docker
  volume. Back it up before intentional migrations or volume removal.
- `docker compose down` preserves state. `docker compose down -v` deletes it and
  should only be used for an intentional clean bootstrap.
