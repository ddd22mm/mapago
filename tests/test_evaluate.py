"""Check benchmark accounting independently of the policy ranking."""

import unittest

from mapago_tools.evaluate import aggregate, metrics


class EvaluationTests(unittest.TestCase):
    def test_tied_scores_and_multiple_ron_claims(self):
        archive = {"result": {"scores": [25000, 25000, 30000, 20000], "rounds": 1},
                   "steps": [{"events": [
                       {"event": {"type": "hora", "actor": 1, "target": 0}},
                       {"event": {"type": "hora", "actor": 2, "target": 0}},
                   ]}]}
        zero = metrics(archive, 0)
        self.assertEqual(zero["rank"], 2.5)
        self.assertEqual(zero["deal_ins"], 2)
        one = metrics(archive, 1)
        self.assertEqual(one["wins"], 1)
        summary = aggregate([zero, one])
        self.assertEqual(summary["seat_samples"], 2)
        self.assertEqual(summary["win_rate"], 0.5)
        self.assertEqual(summary["deal_in_claims_per_round"], 1)


if __name__ == "__main__":
    unittest.main()
