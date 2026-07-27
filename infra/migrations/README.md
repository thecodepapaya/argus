# Database migrations

ARGUS uses additive, idempotent SQLite migrations in
`backend/src/argus/storage/operations.py`. Startup creates missing tables and adds
new nullable/defaulted columns while preserving existing data. Migration behavior
is covered by store and integration tests.

Before a future non-additive schema change, introduce numbered migration files in
this directory, a schema-version table, backup instructions, and rollback tests.
