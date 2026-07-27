"""Long-running weekly scheduler for grounded technology discovery."""

from __future__ import annotations

import json
import os
import signal
import threading
from datetime import UTC, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from argus.discovery import DEFAULT_MODEL, DiscoveryError, discover  # noqa: E402
from argus.live import load_live_cache  # noqa: E402
from argus.storage.operations import OperationsStore  # noqa: E402


def log(event: str, **fields) -> None:
    print(json.dumps({"time": datetime.now(UTC).isoformat(), "service": "argus-discovery", "event": event, **fields}), flush=True)


def main() -> None:
    interval = max(3600, int(os.environ.get("ARGUS_DISCOVERY_INTERVAL_SECONDS", "604800")))
    plateau_weeks = max(8, int(os.environ.get("ARGUS_PLATEAU_WEEKS", "12")))
    model = os.environ.get("ARGUS_DISCOVERY_MODEL", DEFAULT_MODEL)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    log("scheduler_started", interval_seconds=interval, model=model, plateau_weeks=plateau_weeks)

    while not stop.is_set():
        wait_seconds = interval
        store = OperationsStore()
        try:
            cache = load_live_cache()
            if cache:
                store.bootstrap(cache)
            moved = store.evaluate_analysis_cadence("weekly-discovery", plateau_weeks)
            if moved:
                log("cadence_reduced", technologies=moved)
            prior_runs = store.discovery_runs(1)
            discovery_due = not prior_runs
            if prior_runs:
                last_started = datetime.fromisoformat(prior_runs[0]["started_at"])
                elapsed = (datetime.now(UTC) - last_started).total_seconds()
                remaining = interval - elapsed
                discovery_due = remaining <= 0
                wait_seconds = max(3600, remaining)
            if discovery_due:
                try:
                    result = discover(store.technologies(include_drafts=True), model=model)
                    run_id = store.save_discovery(result)
                    log("discovery_completed", run_id=run_id, candidate_count=len(result["candidates"]))
                    wait_seconds = interval
                except DiscoveryError as error:
                    run_id = store.save_discovery_failure("openrouter", model, str(error))
                    log("discovery_failed", run_id=run_id, error=str(error))
                    wait_seconds = interval
            else:
                log("discovery_deferred", seconds_until_due=round(wait_seconds))
        except Exception as error:  # the scheduler must survive a single bad cycle
            log("scheduler_cycle_failed", error_type=type(error).__name__, error=str(error))
        finally:
            store.close()
        stop.wait(wait_seconds)
    log("scheduler_stopped")


if __name__ == "__main__":
    main()
