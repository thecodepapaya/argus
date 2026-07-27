# Runtime configuration

`technologies/*.json` contains the built-in showcase profiles loaded by
`argus.live` for fixture refreshes and clean-database bootstrap. Files are parsed
with Python's standard JSON library and validated at startup; invalid or duplicate
profiles fail fast.

Technologies created in `/admin` are stored in SQLite and use the same required
fields. They do not require a source-controlled JSON file. A profile intended for
clean-install bootstrap belongs here only after review and export to JSON.

Executable scoring and source-weight policies live in code and are documented in
[the implemented methodology](../docs/METHODOLOGY.md). Inactive configuration is
not retained when it no longer reflects runtime behavior.
