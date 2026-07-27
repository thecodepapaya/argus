# ARGUS local scripts

All scripts run from the repository root using Python 3.11+.

```bash
# Refresh the committed public-data fixture (GitHub, Hacker News, Google News RSS).
python3 scripts/refresh_data.py

# Start the local web app.
python3 scripts/run_local.py --port 8000

# Verify a running service and its core public contracts.
python3 scripts/smoke_test.py

# Inspect source health and the latest operational runs.
python3 scripts/operations_status.py

# See which failed source collections would be retried.
python3 scripts/retry_failed_sources.py --dry-run

# Retry only technologies with failed source collection.
python3 scripts/retry_failed_sources.py

# Retry a named technology regardless of its current source status.
python3 scripts/retry_failed_sources.py --technology model-context-protocol

# Inspect discovery configuration and weekly scope without an external call.
python3 scripts/discover_technologies.py --dry-run

# Run one OpenRouter web-search emerging-technology discovery.
OPENROUTER_API_KEY=... python3 scripts/discover_technologies.py

# Run the interval scheduler used by Docker Compose (weekly by default).
python3 scripts/discovery_scheduler.py
```

`retry_failed_sources.py` makes live outbound calls to the configured public sources and saves a new operational run in the local SQLite database. It does not alter the committed fixture; use `refresh_data.py` when you intentionally want to update that showcase cache.

Discovery is optional, requires `OPENROUTER_API_KEY`, and writes suggestions rather
than activating technologies. See [the discovery runbook](../docs/DISCOVERY.md).
