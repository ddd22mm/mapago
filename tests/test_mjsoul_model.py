import json
import tempfile
import unittest
from pathlib import Path

from riichienv import Action, ActionType

from mapago_tools.bots import bot_configs
from mapago_tools.mjsoul_model import (FEATURES, ImitationBot, MIXED_POLICY_VERSION,
                                       MixedImitationBot, POLICY_VERSION, TENHOU_POLICY_VERSION,
                                       candidate_features)


def observation(opponent_hands=None):
    return {
        "player_id": 0,
        "hands": [[0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52],
                   *(opponent_hands or [[], [], []])],
        "discards": [[], [56], [60], [64]],
        "melds": [[], [], [], []],
        "dora_indicators": [72],
        "riichi_declared": [False, True, False, False],
        "scores": [25000] * 4,
    }


class MahjongSoulModelTests(unittest.TestCase):
    def test_features_do_not_depend_on_hidden_hands(self):
        first = observation([[100, 104], [108], [112]])
        second = observation([[120, 124], [128], [132]])
        self.assertEqual(candidate_features(16, first), candidate_features(16, second))

    def test_bot_selects_only_a_supplied_legal_action(self):
        model = {"policy": POLICY_VERSION, "features": list(FEATURES),
                 "weights": [[0.0] * len(FEATURES) for _ in range(34)]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.json"
            path.write_text(json.dumps(model), encoding="utf-8")
            bot = ImitationBot(path)
        actions = [Action(ActionType.DISCARD, 16), Action(ActionType.DISCARD, 20)]
        index = bot.choose(observation(), actions)
        self.assertIn(index, range(len(actions)))

    def test_legal_win_is_taken_over_discard(self):
        model = {"policy": POLICY_VERSION, "features": list(FEATURES),
                 "weights": [[0.0] * len(FEATURES) for _ in range(34)]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.json"
            path.write_text(json.dumps(model), encoding="utf-8")
            bot = ImitationBot(path)
        actions = [Action(ActionType.PASS), Action(ActionType.RON), Action(ActionType.DISCARD, 16)]
        self.assertEqual(bot.choose(observation(), actions), 1)

    def test_tenhou_model_has_distinct_policy_identity(self):
        model = {"policy": TENHOU_POLICY_VERSION, "features": list(FEATURES),
                 "weights": [[0.0] * len(FEATURES) for _ in range(34)]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.json"
            path.write_text(json.dumps(model), encoding="utf-8")
            bot = ImitationBot(path)
        self.assertEqual(bot.name, TENHOU_POLICY_VERSION)

    def test_site_policies_keep_separate_local_checkpoint_paths(self):
        config = bot_configs(["mjsoul-imitation", "tenhou-imitation", "mixed-imitation", "rule-based"], 12)
        self.assertEqual(config[0]["version"], POLICY_VERSION)
        self.assertEqual(config[1]["version"], TENHOU_POLICY_VERSION)
        self.assertEqual(config[2]["version"], MIXED_POLICY_VERSION)
        self.assertIn("model_path", config[0]["settings"])
        self.assertIn("model_path", config[1]["settings"])
        self.assertEqual(config[2]["settings"]["tenhou_weight"], 0.8)

    def test_mixed_bot_uses_the_fixed_80_20_weight_blend(self):
        def model(policy, value):
            return {"policy": policy, "features": list(FEATURES),
                    "weights": [[value] * len(FEATURES) for _ in range(34)]}

        with tempfile.TemporaryDirectory() as directory:
            tenhou_path = Path(directory) / "tenhou.json"
            mjsoul_path = Path(directory) / "mjsoul.json"
            tenhou_path.write_text(json.dumps(model(TENHOU_POLICY_VERSION, 2.0)), encoding="utf-8")
            mjsoul_path.write_text(json.dumps(model(POLICY_VERSION, 4.0)), encoding="utf-8")
            bot = MixedImitationBot(tenhou_path, mjsoul_path)
            self.assertAlmostEqual(bot.weights[0][0], 2.4)
            self.assertEqual(bot.name, MIXED_POLICY_VERSION)
            actions = [Action(ActionType.DISCARD, 16), Action(ActionType.DISCARD, 20)]
            self.assertIn(bot.choose(observation(), actions), range(len(actions)))

    def test_mixed_bot_rejects_a_different_or_unmatched_blend(self):
        with self.assertRaisesRegex(ValueError, "fixed to an 80/20"):
            MixedImitationBot(tenhou_weight=0.5)


if __name__ == "__main__":
    unittest.main()
