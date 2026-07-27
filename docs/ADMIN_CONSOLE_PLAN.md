# Admin console implementation status

**Status:** Implemented baseline with explicit follow-up scope

**Current route:** `/admin`

**API contract:** [API.md](API.md)

The console is intentionally not linked from the public homepage. Operators enter
through `/admin` and authenticate with `ARGUS_ADMIN_TOKEN`.

## Implemented

- Operational summary, recent runs, run errors, and source health
- Evidence review states: unreviewed, approved, and excluded
- Configuration-driven draft technology creation
- Draft validation, 52-week collection/backfill, and activation guardrails
- Weekly versus quarterly analysis cadence controls
- Gemini/Google Search discovery suggestions with accept/dismiss decisions
- Conversion of accepted suggestions into draft technology profiles
- Audit-event persistence and a protected audit API
- Inline success/error states; mutations are not automatically retried

## Lifecycle rules

New profiles move `draft → validated → active`. Activation requires at least one
snapshot. Active technologies default to weekly analysis. Twelve consecutive
productivity-plateau snapshots spanning the expected period move a technology to
quarterly analysis; due quarterly checks are included every 12 weeks. An operator
can restore weekly analysis, and quarterly technologies remain public.

## Deliberately not implemented

The local console is not a production identity system. It does not yet provide
role-based access, multi-user sessions, CSRF-protected cookies, run cancellation,
stage-level reprocessing, snapshot retraction, semantic evidence editing, or cost
budgets. These are deployment/product features, not implied by the current UI.

Before internet exposure, place `/api/v1/admin/*` behind managed identity and rate
limiting, replace the shared header token, configure TLS, and centralize audit logs.
