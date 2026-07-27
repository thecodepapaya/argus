import os
import sys
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from argus.discovery import DiscoveryError, _identity_keys, _prompt, _validate_candidate, discover
from argus.enrichment import enrich_profile
from argus.llm import complete_json


VALID_CANDIDATE = {
    "slug": "test-protocol",
    "display_name": "Test Protocol",
    "kind": "protocol",
    "definition": "A distinct protocol used to test discovery validation.",
    "rationale": "Independent sources show a newly forming ecosystem.",
    "emergence_score": 78,
    "news_query": '"Test Protocol" AI',
    "hn_query": '"Test Protocol"',
    "github_repos": ["example/test-protocol"],
    "relevance_terms": ["test protocol"],
    "evidence_urls": ["https://example.com/one", "https://example.org/two"],
}


class DiscoveryTests(unittest.TestCase):
    def test_candidate_requires_grounding_and_runtime_configuration(self):
        self.assertEqual(_validate_candidate(VALID_CANDIDATE)["slug"], "test-protocol")
        invalid = {**VALID_CANDIDATE, "evidence_urls": ["https://example.com/one"]}
        with self.assertRaisesRegex(DiscoveryError, "two valid evidence"):
            _validate_candidate(invalid)

    def test_prompt_includes_established_portfolio_gaps_and_known_aliases(self):
        prompt = _prompt([{
            "id": "model-context-protocol",
            "display_name": "Model Context Protocol (MCP)",
            "definition": "An open AI integration protocol.",
            "status": "active",
            "relevance_terms": ["mcp protocol"],
        }])
        self.assertIn("well-known or moderately established technologies", prompt)
        self.assertIn("not a novelty score", prompt)
        self.assertIn("Model Context Protocol (MCP)", prompt)
        self.assertIn("mcp protocol", prompt)
        self.assertIn("mcp", _identity_keys({"display_name": "Model Context Protocol (MCP)"}))

    def test_known_alias_candidate_is_suppressed_before_persistence(self):
        alias_candidate = {**VALID_CANDIDATE, "slug": "mcp", "display_name": "MCP", "relevance_terms": ["mcp"]}
        metadata = {"model": "test-model", "message": {"annotations": []}}
        with patch("argus.discovery.complete_json", return_value=({"candidates": [alias_candidate]}, metadata)):
            result = discover([{
                "id": "model-context-protocol",
                "display_name": "Model Context Protocol (MCP)",
                "definition": "An open AI integration protocol.",
                "status": "active",
                "relevance_terms": ["mcp protocol"],
            }], api_key="test-key")
        self.assertEqual(result["candidates"], [])

    def test_missing_api_key_fails_before_network_access(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(DiscoveryError, "OPENROUTER_API_KEY"):
                discover([])
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                enrich_profile("Test protocol", "A protocol used to verify optional LLM setup.")

    def test_openrouter_request_uses_bearer_auth_structured_output_and_web_tool(self):
        raw_response = {"model": "test-model", "choices": [{"message": {"content": '{"value":"ok"}', "annotations": []}}]}
        raw = MagicMock()
        raw.read.return_value = json.dumps(raw_response).encode("utf-8")
        context = MagicMock()
        context.__enter__.return_value = raw
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True), patch("argus.llm.urlopen", return_value=context) as request_call:
            result, _ = complete_json(prompt="Test", schema_name="test", schema={"type": "object"}, use_web_search=True)
        self.assertEqual(result, {"value": "ok"})
        request = request_call.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        body = json.loads(request.data)
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(body["tools"], [{"type": "openrouter:web_search"}])
        # GPT-5 endpoints do not universally accept temperature. Keeping it out
        # prevents strict OpenRouter routing from rejecting every endpoint.
        self.assertNotIn("temperature", body)
        self.assertEqual(body["provider"], {"require_parameters": True})


if __name__ == "__main__":
    unittest.main()
