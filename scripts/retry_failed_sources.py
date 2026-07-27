"""Recollect technologies whose last run reports failed public data sources."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from argus.live import collect_technology, load_live_cache  # noqa: E402
from argus.storage.operations import OperationsStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry ARGUS technologies with failed source collection")
    parser.add_argument("--technology", help="Retry one technology slug, even if no source currently fails")
    parser.add_argument("--dry-run", action="store_true", help="List selected technologies without making network calls")
    args = parser.parse_args()
    store = OperationsStore()
    cache = load_live_cache()
    if cache:
        store.bootstrap(cache)
    failed_ids = {source["technology_id"] for source in store.sources() if source["last_error"]}
    selected = [store.technology(args.technology)] if args.technology else [technology for technology in store.technologies() if technology["id"] in failed_ids]
    selected = [technology for technology in selected if technology]
    if not selected:
        print("No failed sources to retry.")
        return
    for technology in selected:
        print(f"{'Would retry' if args.dry_run else 'Retrying'} {technology['id']}")
        if args.dry_run:
            continue
        collected = collect_technology(technology)
        run_id = store.save_collection(technology["id"], collected, "local-retry", "published")
        print(f"  run {run_id}: {len(collected['source_errors'])} source errors")


if __name__ == "__main__":
    main()
