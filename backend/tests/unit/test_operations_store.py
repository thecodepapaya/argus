import sys
import tempfile
from pathlib import Path
import unittest
import json
from datetime import UTC, datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from argus.live import load_live_cache
from argus.storage.operations import OperationsStore


class OperationsStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = OperationsStore(Path(self.directory.name) / "argus.sqlite3")
        self.store.bootstrap(load_live_cache())

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_bootstrap_exposes_public_overview_and_run_history(self):
        overview = self.store.overview()
        self.assertGreaterEqual(len(overview["items"]), 2)
        self.assertGreaterEqual(len(self.store.runs()), 2)
        movement = overview["items"][0]["change"]
        self.assertIn(movement["week"]["phase_direction"], {"advanced", "moved back", "held its phase"})
        self.assertIn("maturity", movement["month"])

    def test_technology_can_be_created_without_code_changes(self):
        technology = self.store.create_technology({
            "id": "test-runtime", "display_name": "Test runtime", "kind": "framework",
            "definition": "A test technology profile.", "github_repos": ["owner/repo"],
            "hn_query": "test runtime", "news_query": "test runtime", "relevance_terms": ["test runtime"],
        }, "tester")
        self.assertEqual(technology["status"], "draft")
        self.assertEqual(self.store.set_status("test-runtime", "validated", "tester")["status"], "validated")

    def test_long_productivity_plateau_reduces_weekly_cadence(self):
        rows = self.store.connection.execute(
            "SELECT technology_id, week, payload_json FROM snapshots WHERE technology_id = ? ORDER BY week DESC LIMIT 12",
            ("model-context-protocol",),
        ).fetchall()
        self.assertEqual(len(rows), 12)
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload["phase"] = "plateau_of_productivity"
            payload["phase_label"] = "Plateau of Productivity"
            self.store.connection.execute(
                "UPDATE snapshots SET payload_json = ? WHERE technology_id = ? AND week = ?",
                (json.dumps(payload), row["technology_id"], row["week"]),
            )
        self.store.connection.commit()
        changed = self.store.evaluate_analysis_cadence("tester", plateau_weeks=12)
        self.assertEqual(changed, ["model-context-protocol"])
        self.assertEqual(self.store.technology("model-context-protocol")["analysis_cadence"], "quarterly")
        self.assertNotIn("model-context-protocol", {item["id"] for item in self.store.weekly_technologies()})
        latest_week = datetime.fromisoformat(rows[0]["week"]).replace(tzinfo=UTC)
        due = self.store.technologies_due_for_analysis(latest_week + timedelta(weeks=12))
        self.assertIn("model-context-protocol", {item["id"] for item in due})

    def test_discovery_suggestions_are_persisted_and_reviewable(self):
        result = {
            "provider": "openrouter",
            "model": "test-model",
            "completed_at": "2026-07-27T00:00:00+00:00",
            "grounding_sources": [{"title": "Source", "url": "https://example.com"}],
            "search_queries": ["emerging AI protocols"],
            "candidates": [{
                "slug": "test-protocol", "display_name": "Test Protocol", "kind": "protocol",
                "definition": "A test discovery candidate.", "rationale": "Two independent signals.",
                "emergence_score": 75, "news_query": "test protocol", "hn_query": "test protocol",
                "github_repos": ["example/test-protocol"], "relevance_terms": ["test protocol"],
                "evidence_urls": ["https://example.com/one", "https://example.org/two"],
            }],
        }
        run_id = self.store.save_discovery(result, "tester")
        self.assertEqual(self.store.discovery_runs()[0]["id"], run_id)
        suggestion = self.store.suggestions("new")[0]
        self.assertEqual(suggestion["slug"], "test-protocol")
        reviewed = self.store.review_suggestion(suggestion["id"], "dismissed", "tester")
        self.assertEqual(reviewed["status"], "dismissed")

    def test_visitor_suggestions_are_deduplicated_and_reviewable(self):
        suggestion, created = self.store.create_visitor_suggestion("Agent-to-Agent Protocol", "A growing interoperability standard.")
        self.assertTrue(created)
        self.assertEqual(suggestion["status"], "new")
        duplicate, created = self.store.create_visitor_suggestion("  agent-to-agent   protocol  ")
        self.assertFalse(created)
        self.assertEqual(duplicate["id"], suggestion["id"])
        reviewed = self.store.review_visitor_suggestion(suggestion["id"], "reviewed", "tester")
        self.assertEqual(reviewed["status"], "reviewed")
        with self.assertRaisesRegex(ValueError, "already tracks"):
            self.store.create_visitor_suggestion("Model Context Protocol (MCP)")
