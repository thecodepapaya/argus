# Backend

ARGUS currently runs as a dependency-free Python modular monolith. The HTTP service
serves versioned public/admin JSON APIs and static assets; SQLite stores technology
profiles, snapshots, evidence, runs, source health, and audit events.

Runtime reliability features include per-request SQLite connections, WAL mode,
serialized writes with rollback, bounded busy waits, consistent JSON errors,
request IDs, structured access/error logs, refresh exclusion, readiness checks,
and validation of cached snapshots before startup.

`methodology.py` is the canonical public glossary and methodology contract.
`discovery.py` is an optional Gemini/Google Search adapter that only produces
reviewable suggestions. Phase inference remains deterministic and does not use an
LLM. See [the API inventory](../docs/API.md) and [implemented methodology](../docs/METHODOLOGY.md).

Run all unit and live-server integration tests with:

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s backend/tests -v
```
