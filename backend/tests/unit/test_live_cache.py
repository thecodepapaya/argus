import sys
import copy
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from datetime import UTC, datetime, timedelta

from argus.live import TECHNOLOGIES, _get_json, _history, load_live_cache, validate_live_data


class LiveCacheTests(unittest.TestCase):
    def test_committed_showcase_cache_has_all_active_technologies(self):
        payload = load_live_cache()
        self.assertIsNotNone(payload)
        self.assertEqual(set(payload["technologies"]), set(TECHNOLOGIES))
        for profile in payload["technologies"].values():
            self.assertEqual(len(profile["snapshots"]), 52)
            self.assertGreaterEqual(len(profile["evidence"]), 4)
            self.assertTrue(all(item["url"].startswith("http") for item in profile["evidence"]))

    def test_invalid_feature_values_are_rejected(self):
        payload = copy.deepcopy(load_live_cache())
        first = next(iter(payload["technologies"].values()))
        first["snapshots"][-1]["features"]["coverage"] = 140
        with self.assertRaisesRegex(ValueError, "Invalid coverage"):
            validate_live_data(payload)

    def test_github_token_is_scoped_to_github_requests(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{}'
        with patch.dict("os.environ", {"GITHUB_TOKEN": "secret"}, clear=True), patch("argus.live.urlopen", return_value=response) as mocked:
            _get_json("https://api.github.com/repos/example/project")
            github_request = mocked.call_args.args[0]
            self.assertEqual(github_request.get_header("Authorization"), "Bearer secret")
            _get_json("https://hn.algolia.com/api/v1/search")
            hn_request = mocked.call_args.args[0]
            self.assertIsNone(hn_request.get_header("Authorization"))

    def test_history_uses_only_prior_information_for_normalization(self):
        now = datetime(2026, 7, 27, tzinfo=UTC)
        start = now - timedelta(weeks=51)
        activity = [
            {"week": int(start.timestamp()), "total": 10},
            {"week": int(now.timestamp()), "total": 1000},
        ]
        snapshots = _history([activity], [], now)
        self.assertGreater(snapshots[0]["features"]["adoption"], 25)
        self.assertFalse(snapshots[-1]["features"]["momentum_available"])
