"""Run one grounded emerging-technology discovery and persist suggestions."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from argus.discovery import DEFAULT_MODEL, DiscoveryError, discover  # noqa: E402
from argus.live import load_live_cache  # noqa: E402
from argus.storage.operations import OperationsStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover emerging technologies with Gemini and Google Search")
    parser.add_argument("--dry-run", action="store_true", help="Show configuration and weekly scope without calling Gemini")
    parser.add_argument("--plateau-weeks", type=int, default=int(os.environ.get("ARGUS_PLATEAU_WEEKS", "12")), help="Consecutive plateau weeks before quarterly monitoring")
    args = parser.parse_args()

    store = OperationsStore()
    try:
        cache = load_live_cache()
        if cache:
            store.bootstrap(cache)
        moved = store.evaluate_analysis_cadence("weekly-discovery", args.plateau_weeks)
        technologies = store.technologies(include_drafts=True)
        weekly = store.weekly_technologies()
        model = os.environ.get("ARGUS_DISCOVERY_MODEL", DEFAULT_MODEL)
        key_configured = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        print(f"Discovery model: {model}")
        print(f"Gemini API key configured: {'yes' if key_configured else 'no'}")
        print(f"Weekly analysis: {', '.join(item['id'] for item in weekly) or 'none'}")
        if moved:
            print(f"Moved to quarterly monitoring: {', '.join(moved)}")
        if args.dry_run:
            return
        try:
            result = discover(technologies, model=model)
        except DiscoveryError as error:
            run_id = store.save_discovery_failure("google-gemini", model, str(error))
            raise SystemExit(f"Discovery failed (run {run_id}): {error}") from error
        run_id = store.save_discovery(result)
        print(f"Discovery run {run_id}: {len(result['candidates'])} candidate(s)")
        for candidate in result["candidates"]:
            print(f"- {candidate['display_name']} ({candidate['emergence_score']}/100): {candidate['rationale']}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
