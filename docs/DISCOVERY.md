# Technology discovery

The optional `discovery` service runs weekly and proposes AI technologies for review. It searches for both emerging technologies and well-known or moderately established gaps in the tracked portfolio. It uses OpenRouter web search for research only; it does not score lifecycle phases or publish technologies.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | — | Enables discovery and the admin draft-profile assistant. |
| `ARGUS_DISCOVERY_MODEL` | `openai/gpt-4.1-mini` | Model used for weekly discovery. |
| `ARGUS_LLM_MODEL` | `openai/gpt-4.1-mini` | Model used for draft-profile preparation. |
| `ARGUS_DISCOVERY_INTERVAL_SECONDS` | `604800` | Scheduler interval. |
| `ARGUS_PLATEAU_WEEKS` | `12` | Consecutive plateau weeks before quarterly analysis. |

The selected model must support structured output and the OpenRouter web-search server tool. The API key is sent only to OpenRouter as a bearer credential; it is neither stored in SQLite nor exposed by the API.

## Boundaries

- Discovery is separate from evidence scoring and lifecycle inference.
- Candidates require a distinct slug, valid repository references, relevance terms, and at least two source URLs. Existing technologies and recognizable aliases are suppressed before suggestions are saved.
- Candidate priority reflects public signal quality and the value of recurring tracking; it is not a measure of novelty.
- Suggestions remain private until an administrator creates a draft, collects data, validates it, and activates it.
- Draft-profile preparation fills editable fields from an admin-provided name and description. Repository and query suggestions require review before draft creation.

## Commands

```bash
# Inspect scheduler scope and key detection without an API call.
python3 scripts/discover_technologies.py --dry-run

# Run one discovery cycle.
OPENROUTER_API_KEY=... python3 scripts/discover_technologies.py

# Start the application and scheduler with Compose.
docker compose up --build
```

Runs and failures are recorded in SQLite and emitted as JSON logs. The scheduler reads the latest persisted run on startup, preventing an extra discovery request after a container restart.
