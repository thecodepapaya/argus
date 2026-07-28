import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from argus.inference.engine import infer


class InferenceTests(unittest.TestCase):
    def test_peak_when_expectations_outpace_adoption(self):
        estimate = infer({"attention": 88, "expectations": 92, "disappointment": 18, "adoption": 28, "maturity": 25, "momentum": 34, "coverage": 90})
        self.assertEqual(estimate["phase"], "peak_of_inflated_expectations")
        self.assertGreater(estimate["hype_gap"], 0)

    def test_slope_when_adoption_and_maturity_are_growing(self):
        estimate = infer({"attention": 52, "expectations": 55, "disappointment": 22, "adoption": 72, "maturity": 77, "momentum": 18, "coverage": 92})
        self.assertIn(estimate["phase"], {"slope_of_enlightenment", "plateau_of_productivity"})
        self.assertIn(estimate["confidence_band"], {"moderate", "high"})

    def test_unsettled_momentum_does_not_influence_phase_scores(self):
        features = {"attention": 50, "expectations": 50, "disappointment": 20, "adoption": 50, "maturity": 50, "momentum": 95, "coverage": 80, "momentum_available": False}
        positive = infer(features)
        features["momentum"] = -95
        negative = infer(features)
        self.assertEqual(positive["probabilities"], negative["probabilities"])


if __name__ == "__main__":
    unittest.main()
