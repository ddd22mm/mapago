import copy
import unittest
from types import SimpleNamespace

from riichienv import GameRule, RiichiEnv

from mapago_tools.engine_probe import check_observation, run_hand


class EngineProbeTests(unittest.TestCase):
    def test_fixed_seed_reproduces_entire_hand(self):
        first = run_hand(42)
        self.assertEqual(first, run_hand(42))
        self.assertEqual(first["scores"], [24000, 24000, 24000, 28000])
        self.assertEqual(first["observed_seats"], [0, 1, 2, 3])
        self.assertEqual(first["event_counts"]["end_game"], 1)
        self.assertEqual(first["engine_version"], "0.4.11")

    def test_multiple_seeds_and_rule_presets_complete(self):
        for preset in ("tenhou", "mjsoul"):
            for seed in (0, 1, 20261028):
                with self.subTest(preset=preset, seed=seed):
                    result = run_hand(seed, preset)
                    self.assertEqual(result, run_hand(seed, preset))
                    self.assertEqual(len(result["scores"]), 4)
                    self.assertEqual(sorted(result["ranks"]), [1, 2, 3, 4])

    def test_different_seeds_change_trace(self):
        self.assertNotEqual(run_hand(1)["trace_sha256"], run_hand(2)["trace_sha256"])

    def test_summary_does_not_export_private_state(self):
        result = run_hand()
        for key in ("seed", "hands", "wall", "salt", "events", "action_trace"):
            self.assertNotIn(key, result)

    def test_observation_masks_all_other_seats(self):
        env = RiichiEnv(seed=42, rule=GameRule.default_tenhou())
        env.reset()
        for observation in env.get_observations([0, 1, 2, 3]).values():
            check_observation(observation)

    def test_privacy_guard_rejects_leaks(self):
        env = RiichiEnv(seed=42)
        original = env.reset()[0].to_dict()
        mutations = [
            lambda data: data["hands"][1].append(0),
            lambda data: data["events"].append(
                {"type": "tsumo", "actor": 1, "pai": "1m"}
            ),
            lambda data: data["events"].append({"type": "start_game", "seed": 42}),
            lambda data: data["events"].append({
                "type": "start_kyoku", "tehais": [[], ["1m"], [], []],
            }),
        ]
        for mutate in mutations:
            data = copy.deepcopy(original)
            mutate(data)
            observation = SimpleNamespace(player_id=0, to_dict=lambda: data)
            with self.assertRaises(RuntimeError):
                check_observation(observation)

    def test_step_limit_and_invalid_config_fail(self):
        with self.assertRaisesRegex(RuntimeError, "step limit"):
            run_hand(max_steps=1)
        for config in ({"seed": -1}, {"seed": 2**64}, {"rule": "unknown"}, {"max_steps": 0}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                run_hand(**config)

    def test_explicit_rule_presets_differ(self):
        tenhou, mjsoul = GameRule.default_tenhou(), GameRule.default_mjsoul()
        self.assertTrue(tenhou.sanchaho_is_draw)
        self.assertFalse(mjsoul.sanchaho_is_draw)
        self.assertFalse(tenhou.allows_ron_on_ankan_for_kokushi_musou)
        self.assertTrue(mjsoul.allows_ron_on_ankan_for_kokushi_musou)


if __name__ == "__main__":
    unittest.main()
