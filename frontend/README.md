# Frontend

The frontend is a dependency-free set of accessible HTML, CSS, and JavaScript
modules under `frontend/public`. It includes the public overview, explanatory FAQ, focused technology
analysis, and protected operations console.

`client.js` is the shared API boundary. It provides bounded GET retries, request
timeouts, consistent API-error handling, HTML escaping, text normalization, and URL
validation. Mutating admin requests are never automatically retried, preventing
duplicate writes.

Ambiguous analytical terms use one accessible tooltip component backed by the
versioned `/api/v1/methodology` glossary. Tooltips work with hover and keyboard
focus and do not replace the full methodology documentation.
