# Fixtures

Only small synthetic fixtures or attributable public-metadata caches belong here.
`live_snapshot.json` contains repository/feed metadata and short permitted summaries;
it must not contain article bodies, credentials, or personal data. Refresh it with
`python3 scripts/refresh_data.py` and review the diff before committing.
