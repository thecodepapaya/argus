"""SQLite-backed operational store for ARGUS runs, evidence, and discovery."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from functools import wraps
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
DATABASE_PATH = ROOT / "data" / "argus.sqlite3"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def serialized_write(method):
    """Serialize multi-statement SQLite writes while allowing concurrent reads."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._write_lock:
            try:
                result = method(self, *args, **kwargs)
                self.connection.commit()
                return result
            except Exception:
                self.connection.rollback()
                raise
    return wrapped


class OperationsStore:
    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or Path(os.environ.get("ARGUS_DB_PATH", DATABASE_PATH))
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._migrate()

    @property
    def connection(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self.database_path, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
            connection.execute("PRAGMA journal_mode = WAL")
            self._local.connection = connection
        return connection

    def close(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None

    def _migrate(self) -> None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS technologies (
          id TEXT PRIMARY KEY, display_name TEXT NOT NULL, kind TEXT NOT NULL,
          definition TEXT NOT NULL, status TEXT NOT NULL, profile_json TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS snapshots (
          technology_id TEXT NOT NULL, week TEXT NOT NULL, payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL, PRIMARY KEY (technology_id, week),
          FOREIGN KEY (technology_id) REFERENCES technologies(id)
        );
        CREATE TABLE IF NOT EXISTS evidence (
          id TEXT PRIMARY KEY, technology_id TEXT NOT NULL, payload_json TEXT NOT NULL,
          review_status TEXT NOT NULL DEFAULT 'unreviewed', review_note TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          FOREIGN KEY (technology_id) REFERENCES technologies(id)
        );
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, technology_id TEXT, week TEXT NOT NULL, status TEXT NOT NULL,
          stage TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT,
          details_json TEXT NOT NULL, errors_json TEXT NOT NULL,
          FOREIGN KEY (technology_id) REFERENCES technologies(id)
        );
        CREATE TABLE IF NOT EXISTS sources (
          id TEXT PRIMARY KEY, technology_id TEXT, name TEXT NOT NULL, source_class TEXT NOT NULL,
          status TEXT NOT NULL, config_json TEXT NOT NULL, last_success_at TEXT, last_error TEXT,
          FOREIGN KEY (technology_id) REFERENCES technologies(id)
        );
        CREATE TABLE IF NOT EXISTS audit_events (
          id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, object_type TEXT NOT NULL,
          object_id TEXT NOT NULL, detail_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS discovery_runs (
          id TEXT PRIMARY KEY, status TEXT NOT NULL, provider TEXT NOT NULL,
          model TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT,
          candidate_count INTEGER NOT NULL DEFAULT 0, error TEXT,
          detail_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS technology_suggestions (
          id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
          score INTEGER NOT NULL, payload_json TEXT NOT NULL,
          first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
          discovery_run_id TEXT NOT NULL,
          FOREIGN KEY (discovery_run_id) REFERENCES discovery_runs(id)
        );
        CREATE TABLE IF NOT EXISTS visitor_technology_suggestions (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, rationale TEXT NOT NULL,
          normalized_name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS visitor_technology_suggestions_status_idx
          ON visitor_technology_suggestions(status, created_at DESC);
        """)
        self._ensure_column("technologies", "analysis_cadence", "TEXT NOT NULL DEFAULT 'weekly'")
        self._ensure_column("technologies", "cadence_changed_at", "TEXT")
        self.connection.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in self.connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _insert_audit(self, actor: str, action: str, object_type: str, object_id: str, detail: dict[str, Any]) -> None:
        self.connection.execute("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), actor, action, object_type, object_id, json.dumps(detail), _now()))

    @serialized_write
    def audit(self, actor: str, action: str, object_type: str, object_id: str, detail: dict[str, Any]) -> None:
        self._insert_audit(actor, action, object_type, object_id, detail)

    @serialized_write
    def bootstrap(self, payload: dict[str, Any]) -> None:
        for technology_id, profile in payload["technologies"].items():
            existing = self.technology(technology_id)
            if existing:
                # Built-in technology profiles are source-controlled. Keep their
                # latest query/calibration policy in sync without changing status,
                # reviews, evidence, or manually added technologies.
                self.connection.execute(
                    """UPDATE technologies
                       SET display_name = ?, kind = ?, definition = ?, profile_json = ?, updated_at = ?
                       WHERE id = ?""",
                    (profile["technology"]["display_name"], profile["technology"]["kind"], profile["technology"]["definition"], json.dumps(profile["technology"]), _now(), technology_id),
                )
                database_snapshots = self.snapshots(technology_id)
                fixture_snapshots = profile.get("snapshots", [])
                if fixture_snapshots and (not database_snapshots or database_snapshots[-1].get("model_version") != fixture_snapshots[-1].get("model_version")):
                    self._replace_snapshots(technology_id, fixture_snapshots)
                    self._replace_evidence(technology_id, profile.get("evidence", []))
                continue
            technology = profile["technology"]
            now = _now()
            self.connection.execute(
                """INSERT INTO technologies
                   (id, display_name, kind, definition, status, profile_json, created_at, updated_at, analysis_cadence, cadence_changed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'weekly', ?)""",
                (technology_id, technology["display_name"], technology["kind"], technology["definition"], "active", json.dumps(technology), now, now, now),
            )
            self._replace_snapshots(technology_id, profile["snapshots"])
            self._replace_evidence(technology_id, profile["evidence"])
            self._default_sources(technology_id, profile.get("source_errors", []))
            self._create_run(technology_id, profile["snapshots"][-1]["week"], "published", "published", {"source_counts": profile.get("source_counts", {}), "documents": len(profile["evidence"]), "bootstrap": True}, profile.get("source_errors", []))
        self.connection.commit()

    def _replace_snapshots(self, technology_id: str, snapshots: list[dict[str, Any]]) -> None:
        now = _now()
        for snapshot in snapshots:
            self.connection.execute("INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?, ?)", (technology_id, snapshot["week"], json.dumps(snapshot), now))

    def _replace_evidence(self, technology_id: str, evidence: list[dict[str, Any]]) -> None:
        now = _now()
        for item in evidence:
            self.connection.execute(
                """
                INSERT INTO evidence VALUES (?, ?, ?, 'unreviewed', NULL, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                """,
                (item["id"], technology_id, json.dumps(item), now, now),
            )

    def _default_sources(self, technology_id: str, errors: list[str]) -> None:
        for name, source_class in (("GitHub public API", "source_code_or_registry"), ("Hacker News public search", "community_forum"), ("Google News RSS", "established_technical_press")):
            source_id = f"{technology_id}:{source_class}"
            error = next((value for value in errors if name.split()[0] in value), None)
            self.connection.execute(
                """
                INSERT INTO sources VALUES (?, ?, ?, ?, 'active', '{}', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = 'active',
                    last_success_at = COALESCE(excluded.last_success_at, sources.last_success_at),
                    last_error = excluded.last_error
                """,
                (source_id, technology_id, name, source_class, _now() if not error else None, error),
            )

    def _create_run(self, technology_id: str | None, week: str, status: str, stage: str, details: dict[str, Any], errors: list[str]) -> str:
        run_id = str(uuid.uuid4())
        completed = _now() if status in {"published", "completed", "partial", "failed"} else None
        self.connection.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (run_id, technology_id, week, status, stage, _now(), completed, json.dumps(details), json.dumps(errors)))
        return run_id

    def technologies(self, include_drafts: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM technologies" if include_drafts else "SELECT * FROM technologies WHERE status = 'active'"
        return [self._technology(row) for row in self.connection.execute(query + " ORDER BY display_name")]

    def _technology(self, row: sqlite3.Row) -> dict[str, Any]:
        profile = json.loads(row["profile_json"])
        profile.update({"id": row["id"], "display_name": row["display_name"], "kind": row["kind"], "definition": row["definition"], "status": row["status"], "analysis_cadence": row["analysis_cadence"], "cadence_changed_at": row["cadence_changed_at"], "updated_at": row["updated_at"]})
        return profile

    def technology(self, technology_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM technologies WHERE id = ?", (technology_id,)).fetchone()
        return self._technology(row) if row else None

    def weekly_technologies(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM technologies WHERE status = 'active' AND analysis_cadence = 'weekly' ORDER BY display_name")
        return [self._technology(row) for row in rows]

    def technologies_due_for_analysis(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Return weekly technologies plus quarterly ones whose check is due."""
        current = (now or datetime.now(UTC)).date()
        due = self.weekly_technologies()
        rows = self.connection.execute("SELECT * FROM technologies WHERE status = 'active' AND analysis_cadence = 'quarterly' ORDER BY display_name")
        for row in rows:
            technology = self._technology(row)
            snapshots = self.snapshots(technology["id"])
            if not snapshots:
                due.append(technology)
                continue
            latest = datetime.fromisoformat(snapshots[-1]["week"]).date()
            if current - latest >= timedelta(weeks=12):
                due.append(technology)
        return due

    def snapshots(self, technology_id: str) -> list[dict[str, Any]]:
        return [json.loads(row["payload_json"]) for row in self.connection.execute("SELECT payload_json FROM snapshots WHERE technology_id = ? ORDER BY week", (technology_id,))]

    def evidence(self, technology_id: str | None = None, review_status: str | None = None) -> list[dict[str, Any]]:
        clauses, values = [], []
        if technology_id: clauses.append("technology_id = ?"); values.append(technology_id)
        if review_status: clauses.append("review_status = ?"); values.append(review_status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.connection.execute("SELECT * FROM evidence" + where + " ORDER BY updated_at DESC", values)
        output = []
        for row in rows:
            item = json.loads(row["payload_json"])
            item.update({"technology_id": row["technology_id"], "review_status": row["review_status"], "review_note": row["review_note"]})
            output.append(item)
        return output

    def overview(self) -> dict[str, Any]:
        items = []
        for technology in self.technologies():
            snapshots = self.snapshots(technology["id"])
            if not snapshots: continue
            current = snapshots[-1]
            week_ago = snapshots[-2] if len(snapshots) > 1 else current
            month_ago = snapshots[max(0, len(snapshots) - 5)]
            items.append({"technology": technology, "current": current, "change": {"week": self._movement(current, week_ago), "month": self._movement(current, month_ago)}, "source_errors": [row["last_error"] for row in self.connection.execute("SELECT last_error FROM sources WHERE technology_id = ? AND last_error IS NOT NULL", (technology["id"],))]})
        return {"items": items, "last_updated": max((item["technology"]["updated_at"] for item in items), default=None), "open_reviews": self.connection.execute("SELECT COUNT(*) FROM evidence WHERE review_status = 'unreviewed'").fetchone()[0]}

    @staticmethod
    def _movement(current: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
        """Compare two snapshots for UI-facing weekly/monthly direction."""
        phase_order = ["innovation_trigger", "peak_of_inflated_expectations", "trough_of_disillusionment", "slope_of_enlightenment", "plateau_of_productivity"]
        phase_delta = phase_order.index(current["phase"]) - phase_order.index(prior["phase"])
        return {
            "from_week": prior["week"], "phase_from": prior["phase_label"], "phase_to": current["phase_label"],
            "phase_delta": phase_delta,
            "phase_direction": "advanced" if phase_delta > 0 else "moved back" if phase_delta < 0 else "held its phase",
            "adoption": round(current["features"]["adoption"] - prior["features"]["adoption"], 1),
            "maturity": round(current["features"]["maturity"] - prior["features"]["maturity"], 1),
            "attention": round(current["features"]["attention"] - prior["features"]["attention"], 1),
            "hype_gap": round(current["hype_gap"] - prior["hype_gap"], 1),
        }

    def runs(self, technology_id: str | None = None) -> list[dict[str, Any]]:
        query, values = "SELECT * FROM runs", []
        if technology_id: query += " WHERE technology_id = ?"; values.append(technology_id)
        rows = self.connection.execute(query + " ORDER BY started_at DESC", values)
        return [self._run(row) for row in rows]

    @staticmethod
    def _run(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        details = json.loads(item.pop("details_json"))
        errors = json.loads(item.pop("errors_json"))
        return {**item, "details": details, "errors": errors}

    def run(self, run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._run(row) if row else None

    def sources(self) -> list[dict[str, Any]]:
        output = []
        for row in self.connection.execute("SELECT * FROM sources ORDER BY technology_id, name"):
            item = dict(row)
            config = json.loads(item.pop("config_json"))
            output.append({**item, "config": config})
        return output

    def audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        output = []
        for row in self.connection.execute("SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?", (safe_limit,)):
            item = dict(row)
            detail = json.loads(item.pop("detail_json"))
            output.append({**item, "detail": detail})
        return output

    def coverage(self, technology_id: str) -> dict[str, Any]:
        snapshots = self.snapshots(technology_id)
        if not snapshots:
            raise ValueError("No snapshots are available for this technology")
        errors = [row["last_error"] for row in self.connection.execute("SELECT last_error FROM sources WHERE technology_id = ? AND last_error IS NOT NULL", (technology_id,))]
        current = snapshots[-1]
        return {"week": current["week"], "coverage": current["features"]["coverage"], "status": "partial" if errors else "sufficient", "errors": errors}

    def health(self) -> dict[str, Any]:
        self.connection.execute("SELECT 1").fetchone()
        return {
            "database": "ok",
            "technologies": self.connection.execute("SELECT COUNT(*) FROM technologies WHERE status = 'active'").fetchone()[0],
            "snapshots": self.connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0],
            "source_failures": self.connection.execute("SELECT COUNT(*) FROM sources WHERE last_error IS NOT NULL").fetchone()[0],
            "weekly_technologies": self.connection.execute("SELECT COUNT(*) FROM technologies WHERE status = 'active' AND analysis_cadence = 'weekly'").fetchone()[0],
            "open_suggestions": self.connection.execute("SELECT COUNT(*) FROM technology_suggestions WHERE status = 'new'").fetchone()[0]
                + self.connection.execute("SELECT COUNT(*) FROM visitor_technology_suggestions WHERE status = 'new'").fetchone()[0],
        }

    @serialized_write
    def create_technology(self, profile: dict[str, Any], actor: str) -> dict[str, Any]:
        technology_id = str(profile.get("id", "")).strip()
        if not technology_id or technology_id.startswith("-") or technology_id.endswith("-") or len(technology_id) > 80 or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in technology_id):
            raise ValueError("Technology slug must contain only lowercase letters, numbers, and hyphens")
        if self.technology(technology_id): raise ValueError("A technology with this slug already exists")
        required = ("display_name", "kind", "definition", "github_repos", "hn_query", "news_query", "relevance_terms")
        if any(not profile.get(key) for key in required): raise ValueError("Name, type, definition, source queries, repositories, and relevance terms are required")
        text_limits = {"display_name": 120, "kind": 60, "definition": 1000, "hn_query": 300, "news_query": 300}
        if any(not isinstance(profile[key], str) or not profile[key].strip() or len(profile[key]) > limit for key, limit in text_limits.items()):
            raise ValueError("Technology text fields are invalid or too long")
        if not isinstance(profile["github_repos"], list) or len(profile["github_repos"]) > 20 or not all(isinstance(value, str) and value.count("/") == 1 and value.strip() == value and all(part for part in value.split("/")) for value in profile["github_repos"]):
            raise ValueError("GitHub repositories must be an array of owner/repository values")
        if not isinstance(profile["relevance_terms"], list) or len(profile["relevance_terms"]) > 50 or not all(isinstance(value, str) and value.strip() and len(value) <= 100 for value in profile["relevance_terms"]):
            raise ValueError("Relevance terms must be a non-empty array of strings")
        profile = {**profile, "id": technology_id}
        now = _now()
        self.connection.execute(
            """INSERT INTO technologies
               (id, display_name, kind, definition, status, profile_json, created_at, updated_at, analysis_cadence, cadence_changed_at)
               VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, 'weekly', ?)""",
            (technology_id, profile["display_name"], profile["kind"], profile["definition"], json.dumps(profile), now, now, now),
        )
        self._default_sources(technology_id, [])
        self.connection.commit(); self.audit(actor, "create", "technology", technology_id, {"status": "draft"})
        return self.technology(technology_id)  # type: ignore[return-value]

    @serialized_write
    def set_status(self, technology_id: str, status: str, actor: str) -> dict[str, Any]:
        technology = self.technology(technology_id)
        if not technology: raise ValueError("Technology not found")
        if status not in {"draft", "validated", "active", "paused", "archived"}: raise ValueError("Invalid technology status")
        allowed = {"draft": {"validated", "archived"}, "validated": {"draft", "active", "archived"}, "active": {"paused", "archived"}, "paused": {"active", "archived"}, "archived": {"draft"}}
        if status != technology["status"] and status not in allowed.get(technology["status"], set()):
            raise ValueError(f"Cannot move technology from {technology['status']} to {status}")
        if status == "active" and not self.snapshots(technology_id):
            raise ValueError("Collect at least one snapshot before activating a technology")
        self.connection.execute("UPDATE technologies SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), technology_id)); self.connection.commit()
        self.audit(actor, status, "technology", technology_id, {})
        return self.technology(technology_id)  # type: ignore[return-value]

    @serialized_write
    def save_collection(self, technology_id: str, collected: dict[str, Any], actor: str, status: str = "completed") -> str:
        technology = self.technology(technology_id)
        if not technology: raise ValueError("Technology not found")
        if not collected.get("snapshots"): raise ValueError("Collection did not produce any snapshots")
        profile = collected["technology"]
        self.connection.execute("UPDATE technologies SET profile_json = ?, updated_at = ? WHERE id = ?", (json.dumps(profile), _now(), technology_id))
        self._default_sources(technology_id, collected.get("source_errors", []))
        source_health = collected.get("source_health", {})
        successful_sources = sum(value is True for value in source_health.values())
        has_existing_publication = bool(self.snapshots(technology_id)) and technology["status"] == "active"
        if source_health and successful_sources < 2 and has_existing_publication:
            run_id = self._create_run(technology_id, collected["snapshots"][-1]["week"], "partial", "held", {"source_counts": collected.get("source_counts", {}), "source_health": source_health, "documents": len(collected["evidence"]), "publication_held": True}, collected.get("source_errors", []))
            self._insert_audit(actor, "hold_collection", "run", run_id, {"technology": technology_id, "successful_sources": successful_sources})
            return run_id
        self._replace_snapshots(technology_id, collected["snapshots"]); self._replace_evidence(technology_id, collected["evidence"])
        run_id = self._create_run(technology_id, collected["snapshots"][-1]["week"], "partial" if collected.get("source_errors") else status, "published" if status == "published" else "completed", {"source_counts": collected.get("source_counts", {}), "source_health": source_health, "documents": len(collected["evidence"])}, collected.get("source_errors", []))
        self._insert_audit(actor, "collect", "run", run_id, {"technology": technology_id}); return run_id

    @serialized_write
    def review(self, evidence_id: str, status: str, note: str, actor: str) -> None:
        if status not in {"approved", "excluded", "unreviewed"}: raise ValueError("Invalid review status")
        if not self.connection.execute("SELECT 1 FROM evidence WHERE id = ?", (evidence_id,)).fetchone(): raise ValueError("Evidence not found")
        self.connection.execute("UPDATE evidence SET review_status = ?, review_note = ?, updated_at = ? WHERE id = ?", (status, note[:1000], _now(), evidence_id)); self.connection.commit(); self.audit(actor, status, "evidence", evidence_id, {"note": note[:1000]})

    @serialized_write
    def evaluate_analysis_cadence(self, actor: str, plateau_weeks: int = 12) -> list[str]:
        """Move long-stable plateau technologies from weekly to quarterly analysis."""
        if plateau_weeks < 8:
            raise ValueError("Plateau retirement threshold must be at least eight weeks")
        changed: list[str] = []
        for technology in self.weekly_technologies():
            snapshots = self.snapshots(technology["id"])
            if len(snapshots) < plateau_weeks:
                continue
            recent = snapshots[-plateau_weeks:]
            first_week = datetime.fromisoformat(recent[0]["week"]).date()
            last_week = datetime.fromisoformat(recent[-1]["week"]).date()
            spans_required_period = last_week - first_week >= timedelta(weeks=plateau_weeks - 1)
            if spans_required_period and all(snapshot["phase"] == "plateau_of_productivity" for snapshot in recent):
                now = _now()
                self.connection.execute(
                    "UPDATE technologies SET analysis_cadence = 'quarterly', cadence_changed_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, technology["id"]),
                )
                self.audit(actor, "reduce_analysis_cadence", "technology", technology["id"], {"from": "weekly", "to": "quarterly", "plateau_weeks": plateau_weeks})
                changed.append(technology["id"])
        return changed

    @serialized_write
    def set_analysis_cadence(self, technology_id: str, cadence: str, actor: str) -> dict[str, Any]:
        if cadence not in {"weekly", "quarterly"}:
            raise ValueError("Analysis cadence must be weekly or quarterly")
        technology = self.technology(technology_id)
        if not technology:
            raise ValueError("Technology not found")
        now = _now()
        self.connection.execute("UPDATE technologies SET analysis_cadence = ?, cadence_changed_at = ?, updated_at = ? WHERE id = ?", (cadence, now, now, technology_id))
        self.audit(actor, "set_analysis_cadence", "technology", technology_id, {"from": technology["analysis_cadence"], "to": cadence})
        return self.technology(technology_id)  # type: ignore[return-value]

    @serialized_write
    def save_discovery(self, result: dict[str, Any], actor: str = "weekly-discovery") -> str:
        run_id = str(uuid.uuid4())
        now = _now()
        candidates = result.get("candidates", [])
        self.connection.execute(
            "INSERT INTO discovery_runs VALUES (?, 'completed', ?, ?, ?, ?, ?, NULL, ?)",
            (run_id, result["provider"], result["model"], now, result.get("completed_at", now), len(candidates), json.dumps({"grounding_sources": result.get("grounding_sources", []), "search_queries": result.get("search_queries", [])})),
        )
        for candidate in candidates:
            suggestion_id = str(uuid.uuid4())
            self.connection.execute(
                """INSERT INTO technology_suggestions
                   (id, slug, status, score, payload_json, first_seen_at, last_seen_at, discovery_run_id)
                   VALUES (?, ?, 'new', ?, ?, ?, ?, ?)
                   ON CONFLICT(slug) DO UPDATE SET
                     score = excluded.score,
                     payload_json = excluded.payload_json,
                     last_seen_at = excluded.last_seen_at,
                     discovery_run_id = excluded.discovery_run_id,
                     status = CASE WHEN technology_suggestions.status = 'dismissed' THEN 'dismissed' ELSE 'new' END""",
                (suggestion_id, candidate["slug"], candidate["emergence_score"], json.dumps(candidate), now, now, run_id),
            )
        self.audit(actor, "discover", "discovery_run", run_id, {"candidate_count": len(candidates), "model": result["model"]})
        return run_id

    @serialized_write
    def save_discovery_failure(self, provider: str, model: str, error: str, actor: str = "weekly-discovery") -> str:
        run_id = str(uuid.uuid4())
        now = _now()
        self.connection.execute("INSERT INTO discovery_runs VALUES (?, 'failed', ?, ?, ?, ?, 0, ?, '{}')", (run_id, provider, model, now, now, error[:2000]))
        self.audit(actor, "discovery_failed", "discovery_run", run_id, {"error": error[:500]})
        return run_id

    def discovery_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        output = []
        for row in self.connection.execute("SELECT * FROM discovery_runs ORDER BY started_at DESC LIMIT ?", (safe_limit,)):
            item = dict(row)
            item["detail"] = json.loads(item.pop("detail_json"))
            output.append(item)
        return output

    def suggestions(self, status: str | None = None) -> list[dict[str, Any]]:
        values: list[Any] = []
        query = "SELECT * FROM technology_suggestions"
        if status:
            if status not in {"new", "accepted", "dismissed"}:
                raise ValueError("Invalid suggestion status")
            query += " WHERE status = ?"
            values.append(status)
        output = []
        for row in self.connection.execute(query + " ORDER BY score DESC, last_seen_at DESC", values):
            item = dict(row)
            payload = json.loads(item.pop("payload_json"))
            output.append({**item, **payload})
        return output

    @staticmethod
    def _normalized_suggestion_name(name: str) -> str:
        return " ".join(name.casefold().split())

    @serialized_write
    def create_visitor_suggestion(self, name: object, rationale: object = "") -> tuple[dict[str, Any], bool]:
        if not isinstance(name, str):
            raise ValueError("Technology name is required")
        clean_name = " ".join(name.split())
        if len(clean_name) < 2 or len(clean_name) > 120:
            raise ValueError("Technology name must be between 2 and 120 characters")
        if not isinstance(rationale, str):
            raise ValueError("Suggestion context must be text")
        clean_rationale = " ".join(rationale.split())
        if len(clean_rationale) > 500:
            raise ValueError("Suggestion context must be 500 characters or fewer")
        normalized_name = self._normalized_suggestion_name(clean_name)
        tracked_names = {
            self._normalized_suggestion_name(item["display_name"])
            for item in self.technologies(include_drafts=True)
        }
        if normalized_name in tracked_names:
            raise ValueError("ARGUS already tracks this technology or has it in preparation")
        existing = self.connection.execute(
            "SELECT * FROM visitor_technology_suggestions WHERE normalized_name = ? AND status = 'new' ORDER BY created_at DESC LIMIT 1",
            (normalized_name,),
        ).fetchone()
        if existing:
            return dict(existing), False
        suggestion_id = str(uuid.uuid4())
        now = _now()
        self.connection.execute(
            "INSERT INTO visitor_technology_suggestions VALUES (?, ?, ?, ?, 'new', ?, ?)",
            (suggestion_id, clean_name, clean_rationale, normalized_name, now, now),
        )
        self.audit("public-visitor", "suggest", "visitor_technology_suggestion", suggestion_id, {"name": clean_name})
        row = self.connection.execute("SELECT * FROM visitor_technology_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        return dict(row), True  # type: ignore[arg-type]

    def visitor_suggestions(self, status: str | None = None) -> list[dict[str, Any]]:
        values: list[Any] = []
        query = "SELECT * FROM visitor_technology_suggestions"
        if status:
            if status not in {"new", "reviewed", "dismissed"}:
                raise ValueError("Invalid visitor suggestion status")
            query += " WHERE status = ?"
            values.append(status)
        return [dict(row) for row in self.connection.execute(query + " ORDER BY created_at DESC", values)]

    @serialized_write
    def review_visitor_suggestion(self, suggestion_id: str, status: str, actor: str) -> dict[str, Any]:
        if status not in {"reviewed", "dismissed"}:
            raise ValueError("Visitor suggestion status must be reviewed or dismissed")
        row = self.connection.execute("SELECT * FROM visitor_technology_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        if not row:
            raise ValueError("Visitor suggestion not found")
        self.connection.execute(
            "UPDATE visitor_technology_suggestions SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), suggestion_id),
        )
        self.audit(actor, status, "visitor_technology_suggestion", suggestion_id, {"name": row["name"]})
        updated = self.connection.execute("SELECT * FROM visitor_technology_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        return dict(updated)  # type: ignore[arg-type]

    @serialized_write
    def review_suggestion(self, suggestion_id: str, status: str, actor: str) -> dict[str, Any]:
        if status not in {"accepted", "dismissed"}:
            raise ValueError("Suggestion status must be accepted or dismissed")
        row = self.connection.execute("SELECT * FROM technology_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        if not row:
            raise ValueError("Suggestion not found")
        self.connection.execute("UPDATE technology_suggestions SET status = ? WHERE id = ?", (status, suggestion_id))
        self.audit(actor, status, "technology_suggestion", suggestion_id, {"slug": row["slug"]})
        return next(item for item in self.suggestions() if item["id"] == suggestion_id)
