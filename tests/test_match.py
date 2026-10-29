import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mapago_tools.bots import LegalBot, create_bots
from mapago_tools.match import (
    MatchEngine, digest, make_config, play, replay, save_json, visible_event,
)


def resign(archive):
    archive["sha256"] = digest({key: value for key, value in archive.items() if key != "sha256"})
    return archive


class MatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = play(make_config(mode="kyoku"))

    def test_round_trip_from_file_does_not_call_policies(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "match.internal.json"
            save_json(path, self.archive)
            saved = json.loads(path.read_text(encoding="utf-8"))
            with patch("mapago_tools.match.create_bots", side_effect=AssertionError("Policy called")):
                result, frames = replay(saved, 0)
            self.assertTrue(result["verified"])
            self.assertEqual(result["scores"], self.archive["result"]["scores"])
            self.assertEqual(len(frames), result["steps"] + 1)
            with self.assertRaises(FileExistsError):
                save_json(path, {})

    def test_all_modes_and_presets_finish_and_replay(self):
        for mode in ("kyoku", "east", "hanchan"):
            for rule in ("tenhou", "mjsoul"):
                with self.subTest(mode=mode, rule=rule):
                    archive = play(make_config(seed=1, mode=mode, rule=rule))
                    result, _ = replay(archive)
                    self.assertEqual(result["event_counts"]["end_game"], 1)
                    self.assertEqual(sorted(result["ranks"]), [1, 2, 3, 4])
                    self.assertEqual(result["rounds"], result["event_counts"]["start_kyoku"])
                    if mode != "kyoku":
                        self.assertGreater(result["rounds"], 1)

    def test_determinism_and_mixed_policies(self):
        config = make_config(seed=15, mode="kyoku", dealer=2, names=[
            "random-legal", "first-legal", "random-legal", "first-legal",
        ])
        self.assertEqual(play(config), play(config))
        self.assertNotEqual(play(config)["sha256"], self.archive["sha256"])

    def test_win_riichi_and_each_kan_event_replay(self):
        for kind, seed in (("kakan", 0), ("hora", 2), ("ankan", 18),
                           ("reach", 23), ("daiminkan", 81)):
            with self.subTest(kind=kind, seed=seed):
                archive = play(make_config(seed=seed, mode="kyoku"))
                result, _ = replay(archive, 3)
                self.assertGreater(result["event_counts"].get(kind, 0), 0)

    def test_seat_export_and_event_sequence(self):
        for viewer in range(4):
            result, frames = replay(self.archive, viewer)
            events = [item for frame in frames for item in frame["events"]]
            self.assertEqual([item["seq"] for item in events], list(range(len(events))))
            self.assertEqual(len(events), sum(result["event_counts"].values()))
            for frame in frames:
                self.assertEqual(frame["state"]["player_id"], viewer)
                for seat, hand in enumerate(frame["state"]["hands"]):
                    if seat != viewer:
                        self.assertEqual(hand, [])
            for item in events:
                event = item["event"]
                if event["type"] == "start_kyoku":
                    self.assertTrue(all(tile != "?" for tile in event["tehais"][viewer]))
                    for seat, hand in enumerate(event["tehais"]):
                        if seat != viewer:
                            self.assertEqual(set(hand), {"?"})
                if event["type"] == "tsumo" and event["actor"] != viewer:
                    self.assertEqual(event["pai"], "?")
            serialized = json.dumps(frames)
            for secret in ('"seed"', '"wall"', '"salt"', '"config"'):
                self.assertNotIn(secret, serialized)

    def test_archived_events_hide_every_hand_and_draw(self):
        records = [self.archive["initial"], *self.archive["steps"]]
        for record in records:
            for item in record["events"]:
                event = item["event"]
                if event["type"] == "start_kyoku":
                    self.assertTrue(all(set(hand) == {"?"} for hand in event["tehais"]))
                if event["type"] == "tsumo":
                    self.assertEqual(event["pai"], "?")

    def test_allowlist_drops_unknown_fields_and_rejects_unknown_events(self):
        event = {"type": "hora", "actor": 0, "target": 1, "deltas": [1, -1, 0, 0],
                 "tehai": ["1m"], "seed": 42, "wall": [1], "nested": {"hand": [1]}}
        self.assertEqual(visible_event(event, 0), {
            "type": "hora", "actor": 0, "target": 1, "deltas": [1, -1, 0, 0],
        })
        with self.assertRaises(ValueError):
            visible_event({"type": "future_event"}, 0)

    def test_corrupted_and_truncated_archives_rejected(self):
        mutations = [
            lambda a: a["engine"].update(version="0.0.0"),
            lambda a: a.update(schema="unknown"),
            lambda a: a["steps"].pop(),
            lambda a: a["result"]["scores"].__setitem__(0, 0),
            lambda a: a["steps"][0].update(checkpoint="0" * 64),
            lambda a: a["steps"][0].update(step=2),
            lambda a: a["steps"][0]["actions"][0]["action"].update(tile=999),
            lambda a: a["steps"][0]["actions"].append(a["steps"][0]["actions"][0]),
            lambda a: a["steps"][0].update(actions=[]),
            lambda a: a["initial"]["events"][0].update(seq=999),
            lambda a: a["steps"][0]["events"][0].update(seq=999),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                archive = copy.deepcopy(self.archive)
                mutate(archive)
                # Recompute outer checksum to exercise state/legality validation too.
                resign(archive)
                with self.assertRaises(ValueError):
                    replay(archive)
        archive = copy.deepcopy(self.archive)
        archive["result"]["scores"][0] = 0
        with self.assertRaisesRegex(ValueError, "checksum"):
            replay(archive)

    def test_bot_instances_are_independent_and_receive_only_own_information(self):
        config = make_config(mode="kyoku")
        configs = config["bots"]
        bots = create_bots(configs)
        self.assertEqual(len({id(bot.rng) for bot in bots}), 4)
        received = [[] for _ in range(4)]

        class SpyBot:
            def __init__(self, seat):
                self.seat = seat

            def choose(self, observation, legal):
                seat = self.seat
                self_test.assertEqual(observation["player_id"], seat)
                self_test.assertTrue(legal)
                for other, hand in enumerate(observation["hands"]):
                    if other != seat:
                        self_test.assertEqual(hand, [])
                received[seat].extend(observation["events"])
                return 0

        self_test = self
        archive = play(config, bots=[SpyBot(seat) for seat in range(4)])
        for seat in range(4):
            _, frames = replay(archive, seat)
            expected = [item["event"] for frame in frames for item in frame["events"]]
            self.assertTrue(received[seat])
            self.assertEqual(received[seat], expected[:len(received[seat])])

    def test_illegal_policy_and_limits_rejected(self):
        class InvalidBot:
            def choose(self, observation, legal):
                return len(legal)

        with self.assertRaisesRegex(ValueError, "illegal action index"):
            play(make_config(mode="kyoku"), bots=[InvalidBot() for _ in range(4)])
        bot = LegalBot("first-legal", 0)
        with self.assertRaisesRegex(ValueError, "independent"):
            play(make_config(), bots=[bot] * 4)
        with self.assertRaisesRegex(ValueError, "step limit"):
            play(make_config(), max_steps=1)
        for kwargs in ({"seed": -1}, {"mode": "sanma"}, {"rule": "unknown"},
                       {"dealer": 4}, {"names": []}, {"names": ["unknown"] * 4}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                make_config(**kwargs)
        with self.assertRaises(ValueError):
            replay(self.archive, viewer=4)

    def test_rule_based_policy_records_private_rationale_and_replays(self):
        archive = play(make_config(mode="kyoku", names=["rule-based"] * 4))
        self.assertEqual(archive["config"]["bots"][0]["version"], "rule-based-v1")
        decisions = [action["decision"] for step in archive["steps"]
                     for action in step["actions"] if "decision" in action]
        self.assertTrue(decisions)
        self.assertTrue(all("shanten" in item or item["reason"] in
                            ("legal_win", "conservative_pass") for item in decisions))
        _, frames = replay(archive, viewer=0)
        self.assertTrue(frames)
        self.assertNotIn("decision", str(frames))

    def test_response_batches_really_include_multiple_seats(self):
        # First-legal seed 42 produces a simultaneous claim window.
        archive = play(make_config(mode="kyoku", names=["first-legal"] * 4))
        self.assertTrue(any(len(step["actions"]) > 1 for step in archive["steps"]))
        engine = MatchEngine(make_config(mode="kyoku"))
        with self.assertRaisesRegex(ValueError, "active seat"):
            engine.apply([])

    def test_cli_round_trip_and_bad_archive_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "game.internal.json"
            output = Path(directory) / "seat.json"
            base = [sys.executable, "-m", "mapago_tools.match"]
            run = subprocess.run(base + ["run", "--mode", "kyoku", "--output", str(archive)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            review = subprocess.run(base + ["replay", str(archive), "--viewer", "1", "--output", str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(review.returncode, 0, review.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["viewer"], 1)
            archive.write_text('{"schema":', encoding="utf-8")
            bad = subprocess.run(base + ["replay", str(archive)], capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertNotIn("Traceback", bad.stderr)


if __name__ == "__main__":
    unittest.main()
