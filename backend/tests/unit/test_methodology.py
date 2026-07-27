import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from argus.inference.engine import PHASES
from argus.live import FEATURE_NAMES
from argus.methodology import public_methodology


class MethodologyTests(unittest.TestCase):
    def test_public_methodology_matches_runtime_features_and_phases(self):
        methodology = public_methodology()
        self.assertEqual({item["id"] for item in methodology["dimensions"]}, FEATURE_NAMES)
        self.assertEqual([(item["id"], item["label"]) for item in methodology["phases"]], list(PHASES))
        self.assertIn("hype_gap", methodology["glossary"])
        self.assertIn("confidence", methodology["glossary"])


if __name__ == "__main__":
    unittest.main()
