"""Ensure every local stylesheet and script reference is cache-safe.

Cloudflare may retain static files longer than the application response headers.
Each first-party CSS and JavaScript URL therefore carries the first eight
characters of that file's SHA-256 digest. This check makes a content change
without a new URL a CI failure instead of a production styling mismatch.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = ROOT / "frontend" / "public"
REFERENCE = re.compile(r"[\"']/(?P<asset>[\w.-]+\.(?:css|js))\?v=(?P<version>[\w.-]+)[\"']")


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def main() -> int:
    errors: list[str] = []
    for source in sorted(PUBLIC_ROOT.glob("*")):
        if source.suffix not in {".html", ".js"}:
            continue
        for match in REFERENCE.finditer(source.read_text(encoding="utf-8")):
            asset = PUBLIC_ROOT / match.group("asset")
            if not asset.is_file():
                errors.append(f"{source.relative_to(ROOT)} references missing asset {asset.name}")
                continue
            expected = fingerprint(asset)
            actual = match.group("version")
            if actual != expected:
                errors.append(
                    f"{source.relative_to(ROOT)} uses {asset.name}?v={actual}; expected ?v={expected}"
                )
    if errors:
        print("Static asset fingerprint check failed:", *errors, sep="\n- ", file=sys.stderr)
        return 1
    print("Static asset fingerprints are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
