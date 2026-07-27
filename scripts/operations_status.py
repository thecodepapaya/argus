"""Print ARGUS source health and recent run outcomes from the local operations store."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from argus.live import load_live_cache  # noqa: E402
from argus.storage.operations import OperationsStore  # noqa: E402


def main() -> None:
    store = OperationsStore()
    try:
        cache = load_live_cache()
        if cache:
            store.bootstrap(cache)
        sources = store.sources()
        failed = [source for source in sources if source["last_error"]]
        technologies = store.technologies()
        weekly = [item for item in technologies if item["analysis_cadence"] == "weekly"]
        quarterly = [item for item in technologies if item["analysis_cadence"] == "quarterly"]
        print(f"Analysis cadence: {len(weekly)} weekly, {len(quarterly)} quarterly")
        print(f"Sources: {len(sources) - len(failed)} healthy, {len(failed)} with errors")
        for source in failed:
            print(f"- {source['technology_id']} / {source['name']}: {source['last_error']}")
        suggestions = store.suggestions("new")
        discovery_runs = store.discovery_runs(1)
        latest_discovery = discovery_runs[0]["status"] if discovery_runs else "not run"
        print(f"Discovery: {latest_discovery}, {len(suggestions)} suggestion(s) awaiting review")
        print("Recent analysis runs:")
        for run in store.runs()[:10]:
            print(f"- {run['started_at'][:19]} {run['technology_id'] or 'system'}: {run['status']} ({len(run['errors'])} errors)")
    finally:
        store.close()


if __name__ == "__main__":
    main()
