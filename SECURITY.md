# Security policy

Please do not file public issues for suspected vulnerabilities. Send a concise report to the repository owner with reproduction steps and impact instead.

ARGUS's local administration API uses the `X-Argus-Token` header and defaults to `argus-local` only for local development. Set `ARGUS_ADMIN_TOKEN` to a strong secret for any shared environment. The refresh endpoint can make outbound requests to configured public-data sources; put `/api/v1/admin/*` behind identity-aware authentication and rate limiting before deploying it to the public internet.

Weekly discovery optionally uses `GEMINI_API_KEY` (or `GOOGLE_API_KEY`). Supply it
through environment/secret management, restrict it to the Gemini API, set billing
alerts, and never commit it. ARGUS does not persist or return the key.

Scheduled source collection may use `GITHUB_TOKEN`. Prefer a fine-grained token
limited to read-only public repository metadata. It is sent only to
`api.github.com`, and ARGUS does not persist or return it.
