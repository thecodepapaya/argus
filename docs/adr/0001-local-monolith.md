# ADR 0001: Dependency-free modular monolith and SQLite

**Status:** Accepted · **Date:** 2026-07-27

ARGUS uses one dependency-free Python HTTP application and SQLite with WAL mode.
This keeps local setup, failure diagnosis, and data ownership simple at showcase
scale. Per-request connections, serialized writes, busy waits, and additive startup
migrations provide bounded concurrency.

Revisit when sustained write concurrency, multi-host deployment, or operational
backup requirements exceed SQLite's scope. PostgreSQL is not implied until that
trigger is reached and a tested migration exists.
