# Runtime configuration

`technologies/*.json` contains the built-in showcase profiles loaded by
`argus.live` for fixture refreshes and clean-database bootstrap. Files are parsed
with Python's standard JSON library and validated at startup; invalid or duplicate
profiles fail fast.

Technologies created in `/admin` are stored in SQLite and use the same required
fields. They do not need a source-controlled JSON file. To make an admin-created
profile part of clean installations, export and review it before adding a JSON
file here.

The executable scoring and source-weight policies live in code and are documented
in [the implemented methodology](../docs/METHODOLOGY.md). ARGUS deliberately does
not keep inactive configuration files that imply behavior the runtime does not use.
