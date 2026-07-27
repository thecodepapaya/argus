"""Refresh ARGUS's committed public-metadata showcase snapshot."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from argus.live import collect_live_data, write_live_cache  # noqa: E402


if __name__ == "__main__":
    data = collect_live_data()
    write_live_cache(data)
    for tech_id, profile in data["technologies"].items():
        print(f"{tech_id}: {profile['source_counts']} · {len(profile['source_errors'])} source errors")
