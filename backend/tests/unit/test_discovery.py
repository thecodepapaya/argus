import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from argus.discovery import DiscoveryError, _validate_candidate, discover


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

    def test_missing_api_key_fails_before_network_access(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(DiscoveryError, "GEMINI_API_KEY"):
                discover([])


if __name__ == "__main__":
    unittest.main()
