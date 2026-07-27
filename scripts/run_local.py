"""Convenience launcher for the dependency-free ARGUS service."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from argus.server import main  # noqa: E402


if __name__ == "__main__":
    main()
