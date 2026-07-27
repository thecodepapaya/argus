# Weekly emerging-technology discovery

ARGUS has a separate `discovery` Compose service. Once per week it asks an OpenRouter model to search the web for distinct emerging AI technologies that could support evidence-led lifecycle tracking.

## Credentials

Create an OpenRouter API key and set `OPENROUTER_API_KEY` in `.env` for Docker Compose, or export it in the shell when running Python scripts directly. The key is sent only as a bearer credential to OpenRouter; it is never stored in SQLite or returned by the API. Restrict the key's budget and model access, and configure spend alerts appropriate to the project.

The default model is `openai/gpt-4.1-mini`, configurable through `ARGUS_DISCOVERY_MODEL` (and `ARGUS_LLM_MODEL` for the admin assistant). Choose a model that supports structured output and the OpenRouter web-search server tool. OpenRouter web search can incur charges per request in addition to model usage.

## Guardrails

- Discovery is isolated from phase inference; OpenRouter never decides lifecycle placement.
- Existing names and definitions are supplied to prevent duplicates.
- Output must satisfy a JSON schema and local semantic validation.
- Every candidate needs a distinct slug, a verified repository, relevance terms, and at least two direct evidence URLs.
- A suggestion cannot appear publicly. An administrator must accept it, collect data, validate it, and activate it.
- Dismissed suggestions remain dismissed if rediscovered, while their evidence and score can be refreshed.

## Operations

```bash
# Verify scope and credential detection without an API call
python3 scripts/discover_technologies.py --dry-run

# Run discovery once
python3 scripts/discover_technologies.py

# Run the web and weekly scheduler services
docker compose up --build
```

The scheduler records completed and failed runs in SQLite and emits newline-delimited JSON logs. Its interval defaults to 604800 seconds. It reads the latest persisted run before calling OpenRouter, so a container restart does not trigger another billable discovery before the interval is due. The admin console shows whether credentials are configured, the latest run, source links, and actions to create a draft or dismiss a candidate.
