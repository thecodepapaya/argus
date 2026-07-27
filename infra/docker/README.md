# Docker Compose

ARGUS is packaged as one dependency-free Python image. Compose runs that image as
the HTTP service and as a weekly discovery scheduler. The repository-root
`Dockerfile` uses Python 3.14 slim and the app listens on port 8000.

The application state is intentionally mounted at `/app/data/state`, not the full
`/app/data` directory. This keeps the versioned public-data fixture available for
bootstrap while persisting the operational SQLite database in the `argus_data`
named volume.

Copy `.env.example` to `.env` and set `ARGUS_ADMIN_TOKEN` before starting:

```bash
docker compose up --build
```

Set `GEMINI_API_KEY` to enable discovery. Without it, the web tracker remains fully
functional and the discovery service records a clear disabled/failure state rather
than inventing suggestions. Both services share the `argus_data` SQLite volume.
