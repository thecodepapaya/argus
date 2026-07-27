# ARGUS

ARGUS is an evidence-led technology hype and maturity tracker. It compares public attention with observable adoption and maturity signals, then places a technology on an explainable five-stage lifecycle.

The included showcase covers AI agent harnesses, Model Context Protocol (MCP), and AI browser agents. It runs on a dependency-free Python service, SQLite, public GitHub/Hacker News/Google News metadata, and a static web interface.

## What is included

- Public overview, technology detail pages, methodology, and FAQ
- Admin console for source health, evidence review, analysis runs, and technology lifecycle management
- 52-week historical baseline from public metadata
- OpenRouter-assisted candidate discovery and editable draft-profile preparation
- Docker Compose, GitHub Container Registry, and VM deployment support

## Local run

```bash
python3 scripts/refresh_data.py
python3 scripts/run_local.py --port 8000
```

The public interface is available at `http://127.0.0.1:8000`; `/admin` is the operations console and `/faq` explains the model.

## Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

`ARGUS_ADMIN_TOKEN` is required for shared environments. Compose stores operational state in the named `argus_data` volume. `docker compose down -v` removes that state.

## Configuration

| Variable | Purpose |
| --- | --- |
| `ARGUS_ADMIN_TOKEN` | Admin API token. Defaults to `argus-local` only outside Compose. |
| `GITHUB_TOKEN` | Optional fine-grained read-only GitHub token for more reliable collection. |
| `OPENROUTER_API_KEY` | Optional key for weekly discovery and admin draft-profile preparation. |
| `ARGUS_LLM_MODEL` | OpenRouter model for the draft-profile assistant. |
| `ARGUS_DISCOVERY_MODEL` | OpenRouter model for weekly discovery. |

## Data boundaries

ARGUS retains public metadata, feed titles, short permitted summaries, and source links—not article bodies. Historical signals use GitHub activity and dated Hacker News discussion; current coverage also includes Google News RSS. Repository activity is a limited adoption proxy, not production evidence. The result is a research estimate, not investment advice or an official Gartner classification.

The committed showcase cache was generated on 2026-07-27. `scripts/refresh_data.py` refreshes it from the configured public sources.

## Validation

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s backend/tests -v
```

## Documentation

- [Methodology](docs/METHODOLOGY.md)
- [HTTP API](docs/API.md)
- [Operations runbook](docs/runbooks/OPERATIONS.md)
- [Technology discovery](docs/DISCOVERY.md)
- [Production deployment](docs/DEPLOYMENT.md)
- [Runtime technology profiles](config/technologies/)
- [Source and maintenance scripts](scripts/README.md)
- [Architecture plan](docs/PLAN.md)

## Repository layout

```text
ARGUS/
├── backend/     API, collection, inference, storage, and tests
├── config/      versioned technology profiles and source policy
├── data/        local state policy and committed fixtures
├── docs/        methodology, operations, API, and deployment reference
├── frontend/    public and admin web interfaces
├── infra/       container and reverse-proxy assets
└── scripts/     local collection and maintenance commands
```

ARGUS is independent of Gartner. Public copy uses “technology hype and maturity” terminology and does not reproduce proprietary Gartner graphics.
