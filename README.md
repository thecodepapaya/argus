# ARGUS

ARGUS is a **Technology Hype & Maturity Tracker**. It estimates the gap between what the internet promises about a technology and what public adoption and maturity evidence demonstrates.

The showcase tracks **AI agent harnesses**, **Model Context Protocol (MCP)**, and **AI browser agents**. It combines current news/community coverage with public repository activity, produces weekly phase estimates, and explains both supporting and contradictory evidence on a web-based curve.

The application remains dependency-free at runtime: a Python API, explainable phase inference, 52 weeks of public-metadata-derived history, SQLite operations storage, an interactive dashboard, and an optional Gemini/Google Search discovery scheduler.

## Start here

- [Implementation plan](docs/PLAN.md)
- [Runtime technology profiles](config/technologies/)
- [Data-directory policy](data/README.md)
- [Operations runbook](docs/runbooks/OPERATIONS.md)
- [Implemented methodology](docs/METHODOLOGY.md)
- [HTTP API](docs/API.md)
- [Weekly technology discovery](docs/DISCOVERY.md)
- [Production VM deployment](docs/DEPLOYMENT.md)

## Run locally

```bash
python3 scripts/refresh_data.py
python3 scripts/run_local.py --port 8000
```

Open `http://127.0.0.1:8000`. The public overview is the homepage, technology detail routes are available at `/technologies/<technology-id>`, the model FAQ is at `/faq`, and the operations console is at `/admin`.

The console stores technology configuration, run history, source health, evidence-review decisions, and audit events in `data/argus.sqlite3` (ignored by Git). Its default local access token is `argus-local`; set `ARGUS_ADMIN_TOKEN` before a shared or deployed run. The console can create a draft technology with repositories, queries, and relevance terms without a code change, validate it, collect/backfill evidence, and activate it for the public overview.

A committed public-data cache lets the showcase start offline; `refresh_data.py` replaces it using the latest GitHub, Hacker News, and Google News RSS metadata. The **Run due technologies** console action collects weekly profiles plus quarterly profiles whose 12-week interval has elapsed.

`GEMINI_API_KEY` is required only for weekly emerging-technology discovery. `GITHUB_TOKEN` is optional but recommended for reliable scheduled collection; use a fine-grained read-only token. Hacker News and Google News RSS use public endpoints. Discovery writes suggestions to the admin review queue and never changes public tracking automatically. See [the discovery guide](docs/DISCOVERY.md).

For local source-health inspection and retry commands, see [scripts/README.md](scripts/README.md).

## Run with Docker Compose

```bash
cp .env.example .env
# Set ARGUS_ADMIN_TOKEN in .env to a strong local secret.
docker compose up --build
```

Open `http://127.0.0.1:8000`. Docker Compose persists the operational SQLite database in the named `argus_data` volume, while the curated real-data fixture remains baked into the image. Stop with `docker compose down`; include `-v` only when you intentionally want to remove all operational history.

## Data and limitations

ARGUS retains public metadata, feed titles, short permitted summaries, and source links—not article bodies. The historical signal currently uses 52 weeks of public GitHub commit activity and dated Hacker News discussion; current coverage also includes Google News RSS results. Repository activity is capped as an adoption proxy and is not presented as production proof. It is an explainable research estimate, not investment advice or an official Gartner classification.

The collection cache was generated on 2026-07-27. Refresh before a live demonstration where recency matters.

## Validation

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s backend/tests -v
```

## GitHub publishing checklist

- Refresh the data cache immediately before publishing a demo.
- Set a strong `ARGUS_ADMIN_TOKEN`, put `/api/v1/admin/*` behind real identity-aware authentication, and rate-limit refresh endpoints before exposing them publicly.
- Add a project license that matches your intended distribution model.
- Add secrets only through GitHub or deployment settings. Weekly discovery requires `GEMINI_API_KEY`; scheduled GitHub collection should use a read-only `GITHUB_TOKEN`.

For a production VM, use the [deployment runbook](docs/DEPLOYMENT.md). It builds an immutable image in GitHub Container Registry, keeps database state on the VM, and deploys only after the GitHub `production` environment is approved.

## Repository layout

```text
ARGUS/
├── backend/                 Python API, workers, inference, and tests
├── config/                  Versioned technology, source, and model policy
├── data/                    Local development data and committed fixtures
├── docs/                    Plan, architectural decisions, and runbooks
├── frontend/                Web experience and visualization
├── infra/                   Containers, database migrations, deployment files
└── scripts/                 Developer and operational scripts
```

## Product-language note

ARGUS should not present itself as an official Gartner product or reproduce a proprietary Gartner graphic. Public-facing copy should use terms such as “technology hype and maturity,” while explaining that its five qualitative stages are inspired by the widely understood technology-adoption lifecycle.
