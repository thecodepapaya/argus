# Infrastructure

ARGUS currently ships as two processes from one image: the HTTP application and
the optional weekly discovery scheduler. Docker Compose persists their shared
SQLite database in a named volume. PostgreSQL is not implemented or required.

Production hardening—managed identity, TLS termination, rate limiting, backups,
and centralized logs—is environment-specific. The VM reference is in
[docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).
