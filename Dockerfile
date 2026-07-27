FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend/src \
    ARGUS_HOST=0.0.0.0 \
    ARGUS_PORT=8000 \
    ARGUS_DB_PATH=/app/data/state/argus.sqlite3

WORKDIR /app
COPY . /app

RUN useradd --create-home --uid 10001 argus \
    && mkdir -p /app/data/state \
    && chown -R argus:argus /app

USER argus
EXPOSE 8000

CMD ["python", "scripts/run_local.py"]
