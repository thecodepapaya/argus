import json
import os
import socket
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from argus.live import load_live_cache
from argus.server import ArgusApplication, create_server
from argus.storage.operations import OperationsStore


class ServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        store = OperationsStore(Path(cls.directory.name) / "argus.sqlite3")
        cls.application = ArgusApplication(store=store, cache=load_live_cache(), admin_token="test-token")
        cls.server = create_server("127.0.0.1", 0, cls.application)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.application.store.close()
        cls.directory.cleanup()

    @classmethod
    def request(cls, path, method="GET", payload=None, token=None):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Argus-Token"] = token
        request = Request(cls.base_url + path, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, dict(response.headers), json.loads(response.read())
        except HTTPError as error:
            try:
                return error.code, dict(error.headers), json.loads(error.read())
            finally:
                error.close()

    def test_health_and_public_contracts(self):
        status, _, liveness = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertNotIn("database", liveness)
        status, headers, health = self.request("/api/ready")
        self.assertEqual(status, 200)
        self.assertEqual(health["database"], "ok")
        self.assertIn("X-Request-ID", headers)
        status, _, overview = self.request("/api/v1/overview")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(overview["items"]), 3)
        status, _, methodology = self.request("/api/v1/methodology")
        self.assertEqual(status, 200)
        self.assertIn("hype_gap", methodology["glossary"])
        self.assertTrue(all("definition" in item for item in methodology["dimensions"]))
        _, _, current = self.request("/api/v1/technologies/model-context-protocol/snapshots/current")
        status, _, evidence = self.request("/api/v1/technologies/model-context-protocol/evidence")
        self.assertEqual(status, 200)
        self.assertEqual({item["week"] for item in evidence["items"]}, {current["week"]})
        titles = [" ".join("".join(character.lower() if character.isalnum() else " " for character in item["title"]).split()) for item in evidence["items"]]
        self.assertEqual(len(titles), len(set(titles)))

    def test_public_faq_route(self):
        with urlopen(self.base_url + "/faq", timeout=5) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers["Content-Type"])
            self.assertIn("What the five phases mean", body)
            self.assertIn("not affiliated with or endorsed by Gartner", body)

    def test_public_pages_expose_search_metadata_and_sitemap(self):
        with urlopen(self.base_url + "/", timeout=5) as response:
            body = response.read().decode("utf-8")
            self.assertIn('rel="canonical" href="https://argus.thecodepapaya.dev/"', body)
            self.assertIn('application/ld+json', body)
        with urlopen(self.base_url + "/technologies/model-context-protocol", timeout=5) as response:
            body = response.read().decode("utf-8")
            self.assertIn("Model Context Protocol (MCP) hype &amp; maturity tracker | ARGUS", body)
            self.assertIn("<h1>Model Context Protocol (MCP)</h1>", body)
            self.assertIn('rel="canonical" href="https://argus.thecodepapaya.dev/technologies/model-context-protocol"', body)
            self.assertIn('meta property="og:title"', body)
        with urlopen(self.base_url + "/robots.txt", timeout=5) as response:
            self.assertIn("Sitemap: https://argus.thecodepapaya.dev/sitemap.xml", response.read().decode("utf-8"))
        with urlopen(self.base_url + "/sitemap.xml", timeout=5) as response:
            body = response.read().decode("utf-8")
            self.assertIn("application/xml", response.headers["Content-Type"])
            self.assertIn("/technologies/model-context-protocol", body)
            self.assertNotIn("/admin", body)

    def test_favicon_is_served_as_svg(self):
        with urlopen(self.base_url + "/favicon.svg", timeout=5) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("image/svg+xml", response.headers["Content-Type"])
            self.assertIn("<svg", body)

    def test_cloudflare_analytics_loader_is_public_only_and_configuration_driven(self):
        with patch.dict(os.environ, {"ARGUS_CLOUDFLARE_ANALYTICS_TOKEN": "test-site-token"}):
            with urlopen(self.base_url + "/_argus/analytics.js", timeout=5) as response:
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertIn("static.cloudflareinsights.com/beacon.min.js", body)
                self.assertIn("test-site-token", body)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        with urlopen(self.base_url + "/admin", timeout=5) as response:
            self.assertNotIn("/_argus/analytics.js", response.read().decode("utf-8"))

    def test_public_routes_remain_stable_under_concurrency(self):
        paths = [
            "/api/v1/overview",
            "/api/v1/activity",
            "/api/v1/technologies/model-context-protocol/snapshots/current",
            "/api/v1/technologies/model-context-protocol/evidence",
            "/api/v1/technologies/model-context-protocol/coverage",
        ] * 5
        with ThreadPoolExecutor(max_workers=10) as executor:
            statuses = list(executor.map(lambda path: self.request(path)[0], paths))
        self.assertEqual(statuses, [200] * len(paths))

    def test_errors_are_json_and_admin_is_protected(self):
        status, headers, payload = self.request("/api/v1/admin/overview")
        self.assertEqual(status, 401)
        self.assertEqual(payload["code"], "admin_auth_required")
        self.assertEqual(payload["request_id"], headers["X-Request-ID"])
        status, _, payload = self.request("/api/v1/does-not-exist")
        self.assertEqual(status, 404)
        self.assertEqual(payload["code"], "route_not_found")

    def test_malformed_request_is_rejected_without_crashing_the_handler(self):
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=5) as connection:
            connection.sendall(b"GET / HTTP/2.0\r\nHost: localhost\r\n\r\n")
            response = connection.recv(1024)
        self.assertIn(b"505", response)
        self.assertEqual(self.request("/api/health")[0], 200)

    def test_admin_validation_does_not_create_invalid_data(self):
        status, _, payload = self.request(
            "/api/v1/admin/technologies",
            method="POST",
            token="test-token",
            payload={"id": "Invalid Slug"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "validation_error")

    def test_admin_can_unpublish_and_republish_without_losing_data(self):
        technology_id = "model-context-protocol"
        status, _, payload = self.request(
            f"/api/v1/admin/technologies/{technology_id}/pause",
            method="POST", token="test-token", payload={},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "paused")
        self.assertEqual(self.request(f"/api/v1/technologies/{technology_id}/snapshots/current")[0], 404)

        status, _, payload = self.request(
            f"/api/v1/admin/technologies/{technology_id}/activate",
            method="POST", token="test-token", payload={},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "active")
        self.assertEqual(self.request(f"/api/v1/technologies/{technology_id}/snapshots/current")[0], 200)

    def test_admin_can_prepare_an_editable_draft_with_llm_assistance(self):
        prepared = {"profile": {"id": "test-protocol", "display_name": "Test Protocol"}, "provider": "openrouter", "model": "test-model", "review_required": True}
        with patch("argus.server.enrich_profile", return_value=prepared):
            status, _, payload = self.request(
                "/api/v1/admin/technologies/enrich", method="POST", token="test-token",
                payload={"display_name": "Test Protocol", "definition": "A test protocol."},
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload["profile"]["id"], "test-protocol")
        self.assertTrue(payload["review_required"])

    def test_discovery_suggestion_requires_admin_acceptance_and_becomes_a_draft(self):
        self.application.store.save_discovery({
            "provider": "openrouter", "model": "test-model", "completed_at": "2026-07-27T00:00:00+00:00",
            "grounding_sources": [], "search_queries": [],
            "candidates": [{
                "slug": "integration-protocol", "display_name": "Integration Protocol", "kind": "protocol",
                "definition": "An emerging protocol used to exercise the review boundary.",
                "rationale": "Two attributable sources show an emerging ecosystem.", "emergence_score": 82,
                "news_query": "integration protocol", "hn_query": "integration protocol",
                "github_repos": ["example/integration-protocol"], "relevance_terms": ["integration protocol"],
                "evidence_urls": ["https://example.com/one", "https://example.org/two"],
            }],
        }, "tester")
        status, _, discovery = self.request("/api/v1/admin/discovery", token="test-token")
        self.assertEqual(status, 200)
        suggestion = next(item for item in discovery["items"] if item["slug"] == "integration-protocol")
        self.assertIsNone(self.application.store.technology("integration-protocol"))

        status, _, result = self.request(
            f"/api/v1/admin/suggestions/{suggestion['id']}/accept",
            method="POST", token="test-token", payload={},
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["technology"]["status"], "draft")

    def test_admin_technology_lifecycle_enforces_collection_before_activation(self):
        technology_id = "integration-runtime"
        status, _, technology = self.request(
            "/api/v1/admin/technologies",
            method="POST",
            token="test-token",
            payload={
                "id": technology_id,
                "display_name": "Integration runtime",
                "kind": "framework",
                "definition": "A technology created by the server integration test.",
                "github_repos": ["example/runtime"],
                "hn_query": "integration runtime",
                "news_query": "integration runtime",
                "relevance_terms": ["integration runtime"],
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(technology["status"], "draft")

        status, _, technology = self.request(
            f"/api/v1/admin/technologies/{technology_id}/validate",
            method="POST",
            token="test-token",
            payload={},
        )
        self.assertEqual(status, 200)
        self.assertEqual(technology["status"], "validated")

        status, _, payload = self.request(
            f"/api/v1/admin/technologies/{technology_id}/activate",
            method="POST",
            token="test-token",
            payload={},
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "validation_error")
        self.assertIn("snapshot", payload["error"].lower())

        status, _, audit = self.request("/api/v1/admin/audit?limit=10", token="test-token")
        self.assertEqual(status, 200)
        self.assertTrue(any(item["object_id"] == technology_id for item in audit["items"]))


if __name__ == "__main__":
    unittest.main()
