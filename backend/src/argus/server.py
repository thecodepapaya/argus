"""ARGUS HTTP service: public API, protected operations API, and static pages."""

from __future__ import annotations

import argparse
import html
import hmac
import json
import os
import re
import threading
import time
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from argus.live import SOURCE_DISCLOSURE, collect_technology, load_live_cache
from argus.enrichment import enrich_profile
from argus.llm import configured as llm_configured
from argus.methodology import public_methodology
from argus.storage.operations import OperationsStore


ROOT = Path(__file__).resolve().parents[3]
STATIC_ROOT = ROOT / "frontend" / "public"
PUBLIC_URL = os.environ.get("ARGUS_PUBLIC_URL", "https://argus.thecodepapaya.dev").rstrip("/")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _log(event: str, **fields: Any) -> None:
    print(json.dumps({"time": _now(), "event": event, **fields}, ensure_ascii=False), flush=True)


def _deduplicate_public_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeat collection results by normalized title for public display."""
    selected: dict[str, dict[str, Any]] = {}
    for item in items:
        key = re.sub(r"[^a-z0-9]+", " ", item.get("title", "").lower()).strip() or item["id"]
        existing = selected.get(key)
        if existing is None or item.get("weight", 0) > existing.get("weight", 0):
            selected[key] = item
    return list(selected.values())


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class ArgusApplication:
    def __init__(self, store: OperationsStore | None = None, cache: dict[str, Any] | None = None, admin_token: str | None = None) -> None:
        cached = cache if cache is not None else load_live_cache()
        if cached is None:
            raise RuntimeError("No public-data cache found. Run `python3 scripts/refresh_data.py` before starting ARGUS.")
        self.store = store or OperationsStore()
        self.store.bootstrap(cached)
        configured_token = admin_token if admin_token is not None else os.environ.get("ARGUS_ADMIN_TOKEN")
        self.admin_token = configured_token or "argus-local"
        self._refresh_lock = threading.Lock()

    def readiness(self) -> dict[str, Any]:
        return {"status": "ok", "service": "argus", "time": _now(), **self.store.health()}

    def refresh(self, technology_id: str | None, actor: str) -> dict[str, Any]:
        if not self._refresh_lock.acquire(blocking=False):
            raise ApiError(HTTPStatus.CONFLICT, "refresh_in_progress", "A data refresh is already running")
        try:
            if technology_id:
                technology = self.store.technology(technology_id)
                if not technology:
                    raise ApiError(HTTPStatus.NOT_FOUND, "technology_not_found", "Technology not found")
                technologies = [technology]
            else:
                plateau_weeks = max(8, int(os.environ.get("ARGUS_PLATEAU_WEEKS", "12")))
                self.store.evaluate_analysis_cadence(actor, plateau_weeks)
                technologies = self.store.technologies_due_for_analysis()
            run_ids = []
            for technology in technologies:
                collected = collect_technology(technology)
                run_ids.append(self.store.save_collection(technology["id"], collected, actor, "published"))
            return {"run_ids": run_ids, "completed_at": _now()}
        finally:
            self._refresh_lock.release()


class ArgusHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], application: ArgusApplication) -> None:
        self.application = application
        super().__init__(address, Handler)


class Handler(SimpleHTTPRequestHandler):
    server_version = "ARGUS/0.5"

    def __init__(self, *args, **kwargs) -> None:
        self.request_id = uuid.uuid4().hex
        self.request_started = time.monotonic()
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    @property
    def application(self) -> ArgusApplication:
        return self.server.application  # type: ignore[attr-defined,no-any-return]

    def finish(self) -> None:
        try:
            super().finish()
        finally:
            # Each request thread owns its SQLite connection. Closing it here keeps
            # connection lifetime bounded and prevents descriptors accumulating.
            self.application.store.close()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        # Python invokes this hook while handling malformed request lines, before
        # `parse_request()` has populated `command` or `path`.
        _log(
            "http_access",
            request_id=self.request_id,
            method=getattr(self, "command", None) or "INVALID",
            path=getattr(self, "path", "<invalid-request>"),
            message=format % args,
            duration_ms=round((time.monotonic() - self.request_started) * 1000, 1),
        )

    def end_headers(self) -> None:
        self.send_header("X-Request-ID", self.request_id)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()

    def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if "/admin" in self.path else "public, max-age=30")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._json({"error": message, "code": code, "request_id": self.request_id}, status)

    def _document(self, body: str, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        """Send a public document without routing it through the JSON API."""
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(encoded)

    def _technology_page(self, technology_id: str) -> None:
        """Render technology-specific metadata around the shared interactive UI shell."""
        if not re.fullmatch(r"[a-z0-9-]{1,80}", technology_id):
            raise ApiError(HTTPStatus.NOT_FOUND, "technology_not_found", "Technology not found")
        technology = self.application.store.technology(technology_id)
        if not technology or technology["status"] != "active":
            raise ApiError(HTTPStatus.NOT_FOUND, "technology_not_found", "Technology not found")
        name = str(technology["display_name"])
        title = f"{name} hype & maturity tracker | ARGUS"
        description = f"ARGUS tracks public evidence for {name}: {technology['definition']}"
        page_url = f"{PUBLIC_URL}/technologies/{technology_id}"
        template = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        for placeholder, value in {
            "__ARGUS_PAGE_TITLE__": title,
            "__ARGUS_PAGE_DESCRIPTION__": description[:300],
            "__ARGUS_PAGE_URL__": page_url,
        }.items():
            template = template.replace(placeholder, html.escape(value, quote=True))
        self._document(template, "text/html; charset=utf-8")

    def _sitemap(self) -> None:
        urls = [f"{PUBLIC_URL}/", f"{PUBLIC_URL}/faq"]
        urls.extend(f"{PUBLIC_URL}/technologies/{item['id']}" for item in self.application.store.technologies())
        entries = "".join(f"  <url><loc>{html.escape(url, quote=True)}</loc></url>\n" for url in urls)
        body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + entries + "</urlset>\n"
        self._document(body, "application/xml; charset=utf-8")

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_content_length", "Invalid Content-Length header") from error
        if length < 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_content_length", "Content-Length cannot be negative")
        if length > 100_000:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_too_large", "Request body is too large")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_json", "Request body must be valid JSON") from error
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_json_type", "Request body must be a JSON object")
        return payload

    def _require_admin(self) -> None:
        token = self.headers.get("X-Argus-Token", "")
        if not hmac.compare_digest(token, self.application.admin_token):
            raise ApiError(HTTPStatus.UNAUTHORIZED, "admin_auth_required", "Admin authentication required")

    def _handle_failure(self, error: Exception) -> None:
        if isinstance(error, ApiError):
            self._error(error.status, error.code, error.message)
            return
        _log("http_error", request_id=self.request_id, method=self.command, path=self.path, error_type=type(error).__name__, error=str(error))
        self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "ARGUS could not complete the request")

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if not path.startswith("/api/"):
                if path == "/sitemap.xml":
                    self._sitemap(); return
                if path.startswith("/technologies/"):
                    self._technology_page(unquote(path.removeprefix("/technologies/"))); return
                if path == "/": self.path = "/home.html"
                elif path == "/admin": self.path = "/admin.html"
                elif path == "/faq": self.path = "/faq.html"
                return super().do_GET()
            self._dispatch_get(path, parse_qs(parsed.query))
        except (BrokenPipeError, ConnectionResetError):
            _log("client_disconnected", request_id=self.request_id, path=self.path)
        except Exception as error:
            self._handle_failure(error)

    def _dispatch_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/health":
            self._json({"status": "ok", "service": "argus", "time": _now()}); return
        if path == "/api/ready":
            self._json(self.application.readiness()); return
        if path == "/api/v1/overview": self._json(self.application.store.overview()); return
        if path == "/api/v1/activity": self._json({"items": self.application.store.runs()[:12]}); return
        if path == "/api/v1/technologies": self._json({"items": self.application.store.technologies()}); return
        if path == "/api/v1/methodology":
            self._json(public_methodology()); return
        if path == "/api/v1/sources/disclosure": self._json({"items": SOURCE_DISCLOSURE}); return
        if path.startswith("/api/v1/technologies/"): self._public_technology(path, query); return
        if path.startswith("/api/v1/admin/"):
            self._require_admin(); self._admin_get(path.removeprefix("/api/v1/admin/"), query); return
        raise ApiError(HTTPStatus.NOT_FOUND, "route_not_found", "Route not found")

    def _admin_get(self, route: str, query: dict[str, list[str]]) -> None:
        store = self.application.store
        if route == "overview": self._json({**store.overview(), "runs": store.runs()[:10], "sources": store.sources()}); return
        if route == "runs": self._json({"items": store.runs(query.get("technology_id", [None])[0])}); return
        if route.startswith("runs/"):
            item = store.run(route.split("/", 1)[1])
            if not item: raise ApiError(HTTPStatus.NOT_FOUND, "run_not_found", "Run not found")
            self._json(item); return
        if route == "evidence": self._json({"items": store.evidence(query.get("technology_id", [None])[0], query.get("review_status", [None])[0])}); return
        if route == "technologies": self._json({"items": store.technologies(include_drafts=True)}); return
        if route == "sources": self._json({"items": store.sources()}); return
        if route == "discovery":
            status = query.get("status", [None])[0]
            try: suggestions = store.suggestions(status)
            except ValueError as error: raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_status", str(error)) from error
            self._json({"items": suggestions, "runs": store.discovery_runs(), "configured": llm_configured()}); return
        if route == "audit":
            try: limit = int(query.get("limit", ["100"])[0])
            except ValueError as error: raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_limit", "Audit limit must be an integer") from error
            self._json({"items": store.audit_events(limit)}); return
        raise ApiError(HTTPStatus.NOT_FOUND, "route_not_found", "Route not found")

    def _public_technology(self, path: str, query: dict[str, list[str]]) -> None:
        parts = path.split("/")
        technology_id = unquote(parts[4]) if len(parts) > 4 else ""
        technology = self.application.store.technology(technology_id)
        if not technology or technology["status"] != "active":
            raise ApiError(HTTPStatus.NOT_FOUND, "technology_not_found", "Technology not found")
        suffix = parts[5:]
        if not suffix: self._json(technology); return
        snapshots = self.application.store.snapshots(technology_id)
        if suffix in (["snapshots"], ["snapshots", "current"]) and not snapshots:
            raise ApiError(HTTPStatus.SERVICE_UNAVAILABLE, "snapshots_unavailable", "No snapshots are available for this technology")
        if suffix == ["snapshots", "current"]: self._json(snapshots[-1]); return
        if suffix == ["snapshots"]: self._json({"items": snapshots}); return
        if len(suffix) == 2 and suffix[0] == "snapshots":
            item = next((snapshot for snapshot in snapshots if snapshot["week"] == unquote(suffix[1])), None)
            if not item: raise ApiError(HTTPStatus.NOT_FOUND, "snapshot_not_found", "Snapshot not found")
            self._json(item); return
        if suffix == ["evidence"]:
            items = self.application.store.evidence(technology_id)
            selected_week = query.get("week", [snapshots[-1]["week"] if snapshots else None])[0]
            if not selected_week or not any(snapshot["week"] == selected_week for snapshot in snapshots):
                raise ApiError(HTTPStatus.NOT_FOUND, "snapshot_not_found", "Evidence week does not match an available snapshot")
            items = [item for item in items if item.get("week") == selected_week]
            items = _deduplicate_public_evidence(items)
            dimension = query.get("dimension", [None])[0]
            allowed = {None, "all", "attention", "expectations", "disappointment", "adoption", "maturity", "momentum"}
            if dimension not in allowed: raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_dimension", "Unknown evidence dimension")
            if dimension and dimension != "all": items = [item for item in items if item["dimension"] == dimension]
            self._json({"items": [item for item in items if item["review_status"] != "excluded"]}); return
        if suffix == ["coverage"]: self._json(self.application.store.coverage(technology_id)); return
        raise ApiError(HTTPStatus.NOT_FOUND, "route_not_found", "Route not found")

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path.rstrip("/")
            if not path.startswith("/api/v1/admin/"):
                raise ApiError(HTTPStatus.NOT_FOUND, "route_not_found", "Route not found")
            self._require_admin()
            payload = self._body()
            self._dispatch_post(path.removeprefix("/api/v1/admin/"), payload)
        except (BrokenPipeError, ConnectionResetError):
            _log("client_disconnected", request_id=self.request_id, path=self.path)
        except Exception as error:
            self._handle_failure(error)

    def _dispatch_post(self, route: str, payload: dict[str, Any]) -> None:
        actor = self.headers.get("X-Argus-Actor", "local-admin")[:100]
        store = self.application.store
        try:
            if route == "refresh": self._json(self.application.refresh(payload.get("technology_id"), actor), HTTPStatus.CREATED); return
            if route == "technologies/enrich": self._json(enrich_profile(payload.get("display_name"), payload.get("definition"))); return
            if route == "technologies": self._json(store.create_technology(payload, actor), HTTPStatus.CREATED); return
            parts = route.split("/")
            if len(parts) == 3 and parts[0] == "technologies":
                technology_id, action = parts[1], parts[2]
                technology = store.technology(technology_id)
                if not technology: raise ApiError(HTTPStatus.NOT_FOUND, "technology_not_found", "Technology not found")
                if action == "validate": self._json(store.set_status(technology_id, "validated", actor)); return
                if action == "backfill":
                    collected = collect_technology(technology)
                    run_id = store.save_collection(technology_id, collected, actor, "completed")
                    self._json({"run_id": run_id, "preview": collected["snapshots"][-1], "errors": collected["source_errors"]}, HTTPStatus.CREATED); return
                if action == "activate": self._json(store.set_status(technology_id, "active", actor)); return
                if action == "pause": self._json(store.set_status(technology_id, "paused", actor)); return
                if action == "cadence": self._json(store.set_analysis_cadence(technology_id, str(payload.get("cadence", "")), actor)); return
            if len(parts) == 3 and parts[0] == "evidence" and parts[2] == "review":
                store.review(parts[1], payload.get("status", "unreviewed"), str(payload.get("note", "")), actor)
                self._json({"ok": True}); return
            if len(parts) == 3 and parts[0] == "suggestions" and parts[2] in {"accept", "dismiss"}:
                suggestion = next((item for item in store.suggestions() if item["id"] == parts[1]), None)
                if not suggestion: raise ApiError(HTTPStatus.NOT_FOUND, "suggestion_not_found", "Technology suggestion not found")
                if parts[2] == "accept":
                    technology = store.create_technology({
                        "id": suggestion["slug"],
                        "display_name": suggestion["display_name"],
                        "kind": suggestion["kind"],
                        "definition": suggestion["definition"],
                        "github_repos": suggestion["github_repos"],
                        "hn_query": suggestion["hn_query"],
                        "news_query": suggestion["news_query"],
                        "relevance_terms": suggestion["relevance_terms"],
                    }, actor)
                    store.review_suggestion(parts[1], "accepted", actor)
                    self._json({"suggestion_status": "accepted", "technology": technology}, HTTPStatus.CREATED); return
                self._json(store.review_suggestion(parts[1], "dismissed", actor)); return
        except ValueError as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "validation_error", str(error)) from error
        raise ApiError(HTTPStatus.NOT_FOUND, "route_not_found", "Route not found")


def create_server(host: str, port: int, application: ArgusApplication | None = None) -> ArgusHTTPServer:
    return ArgusHTTPServer((host, port), application or ArgusApplication())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ARGUS locally")
    parser.add_argument("--host", default=os.environ.get("ARGUS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ARGUS_PORT", "8000")))
    args = parser.parse_args()
    server = create_server(args.host, args.port)
    _log("server_started", host=args.host, port=args.port)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        server.application.store.close()
        _log("server_stopped", host=args.host, port=args.port)


if __name__ == "__main__": main()
