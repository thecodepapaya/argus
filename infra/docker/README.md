# Docker Compose

ARGUS is packaged as one dependency-free Python image. Compose runs that image as
the HTTP service and as a weekly discovery scheduler. The repository-root
`Dockerfile` uses Python 3.14 slim and the app listens on port 8000.

The application state is intentionally mounted at `/app/data/state`, not the full
`/app/data` directory. This keeps the versioned public-data fixture available for
bootstrap while persisting the operational SQLite database in the `argus_data`
named volume.

With `.env` populated from `.env.example`, local Compose startup is:

```bash
docker compose up --build
```

`ARGUS_ADMIN_TOKEN` is required in `.env`. `OPENROUTER_API_KEY` enables discovery
and draft-profile assistance; without it, the tracker remains available and
discovery records a disabled state. Both services share the `argus_data` SQLite volume.
