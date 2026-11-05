import json
import tempfile
import unittest
from pathlib import Path

from riichienv import Action, ActionType

from mapago_tools.bots import bot_configs
from mapago_tools.mjsoul_model import (FEATURES, ImitationBot, POLICY_VERSION,
                                       TENHOU_POLICY_VERSION, candidate_features)


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
        config = bot_configs(["mjsoul-imitation", "tenhou-imitation", "rule-based", "rule-based"], 12)
        self.assertEqual(config[0]["version"], POLICY_VERSION)
        self.assertEqual(config[1]["version"], TENHOU_POLICY_VERSION)
        self.assertIn("model_path", config[0]["settings"])
        self.assertIn("model_path", config[1]["settings"])


if __name__ == "__main__":
    unittest.main()
