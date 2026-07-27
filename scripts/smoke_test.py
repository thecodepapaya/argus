"""Run a dependency-free smoke test against a running ARGUS service."""

from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch(base_url: str, path: str) -> tuple[dict, str | None]:
    request = Request(base_url.rstrip("/") + path, headers={"Accept": "application/json", "User-Agent": "ARGUS-smoke-test/1.0"})
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read()), response.headers.get("X-Request-ID")


def fetch_page(base_url: str, path: str) -> tuple[str, str | None]:
    request = Request(base_url.rstrip("/") + path, headers={"Accept": "text/html", "User-Agent": "ARGUS-smoke-test/1.0"})
    with urlopen(request, timeout=8) as response:
        return response.read().decode("utf-8"), response.headers.get("X-Request-ID")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test a running ARGUS service")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    checks = (
        ("readiness", "/api/ready", lambda body: body.get("status") == "ok" and body.get("database") == "ok"),
        ("overview", "/api/v1/overview", lambda body: bool(body.get("items"))),
        ("technologies", "/api/v1/technologies", lambda body: bool(body.get("items"))),
        ("activity", "/api/v1/activity", lambda body: isinstance(body.get("items"), list)),
        ("methodology", "/api/v1/methodology", lambda body: bool(body.get("glossary", {}).get("hype_gap"))),
    )
    failed = False
    for name, path, predicate in checks:
        try:
            body, request_id = fetch(args.base_url, path)
            ok = predicate(body)
            print(f"{'PASS' if ok else 'FAIL'} {name} request_id={request_id or 'missing'}")
            failed = failed or not ok
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            print(f"FAIL {name}: {error}")
            failed = True
    try:
        faq, request_id = fetch_page(args.base_url, "/faq")
        ok = "What the five phases mean" in faq
        print(f"{'PASS' if ok else 'FAIL'} faq request_id={request_id or 'missing'}")
        failed = failed or not ok
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError) as error:
        print(f"FAIL faq: {error}")
        failed = True
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
