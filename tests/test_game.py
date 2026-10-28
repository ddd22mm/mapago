import copy
import http.client
import json
import threading
import unittest

from mapago_tools.game import GameSession, InvalidAction, StaleAction
from mapago_tools.match import replay
from mapago_tools.server import GameServer


def choose(snapshot):
    return next((action for action in snapshot["actions"] if action["kind"] in (4, 6)),
                next((action for action in snapshot["actions"] if action["kind"] == 0),
                     snapshot["actions"][0]))["id"]


class GameTests(unittest.TestCase):
    def assert_private(self, snapshot):
        for hand in snapshot["state"]["hands"][1:]:
            self.assertEqual(hand, [])
        serialized = json.dumps(snapshot)
        for forbidden in ('"seed"', '"wall"', '"salt"', '"config"', '"bot_cursors"'):
            self.assertNotIn(forbidden, serialized)
        for item in snapshot["events"]:
            event = item["event"]
            if event["type"] == "tsumo" and event["actor"] != 0:
                self.assertEqual(event["pai"], "?")
            if event["type"] == "start_kyoku":
                self.assertTrue(all(set(hand) == {"?"} for hand in event["tehais"][1:]))

    def test_human_and_three_bots_complete_and_replay(self):
        for rule in ("tenhou", "mjsoul"):
            for policy in ("random-legal", "first-legal"):
                with self.subTest(rule=rule, policy=policy):
                    game = GameSession(seed=42, rule=rule, policy=policy)
                    choices = 0
                    while game.snapshot()["status"] != "finished":
                        snapshot = game.snapshot()
                        self.assert_private(snapshot)
                        self.assertTrue(snapshot["actions"])
                        game.act(snapshot["revision"], choose(snapshot))
                        choices += 1
                        self.assertLess(choices, 150)
                    result = game.snapshot()
                    self.assert_private(result)
                    self.assertEqual(result["remaining"], 0)
                    self.assertEqual(result["actions"], [])
                    self.assertEqual(replay(game.archive)[0]["scores"], result["result"]["scores"])
                    self.assertEqual(len(game.seat_replay()["frames"]), game.revision + 1)
                    self.assertEqual(game.archive["config"]["bots"][0]["name"], "human")

    def test_bad_or_stale_actions_do_not_advance_state(self):
        game = GameSession(seed=42)
        before = game.snapshot()
        for revision, action in ((-1, 0), (0, -1), (0, 999), (True, 0), (0, False), (0, {})):
            with self.assertRaises(InvalidAction):
                game.act(revision, action)
            self.assertEqual(game.snapshot(), before)
        game.act(before["revision"], choose(before))
        current = copy.deepcopy(game.snapshot())
        with self.assertRaises(StaleAction):
            game.act(before["revision"], choose(before))
        self.assertEqual(game.snapshot(), current)
        with self.assertRaises(InvalidAction):
            game.seat_replay()

    def test_initial_count_and_action_tiles(self):
        game = GameSession(seed=42)
        snapshot = game.snapshot()
        self.assertEqual(snapshot["remaining"], 69)
        self.assertEqual(len(snapshot["state"]["hands"][0]), 14)
        self.assertTrue(all(action["tile_id"] in snapshot["state"]["hands"][0]
                            for action in snapshot["actions"] if action["kind"] == 0))

    def test_random_human_history_round_trip(self):
        seen = set()
        # Select the original random policy for seat 0 via human inputs to
        # exercise precisely the same special-action seeds as stage 2.
        from mapago_tools.bots import LegalBot
        for seed in (0, 2, 18, 23, 81):
            game = GameSession(seed=seed)
            human = LegalBot("random-legal", seed ^ 1)
            while game.snapshot()["status"] != "finished":
                s = game.snapshot()
                seen.update(action["label"] for action in s["actions"])
                self.assert_private(s)
                index = human.choose({}, s["actions"])
                game.act(s["revision"], s["actions"][index]["id"])
            replay(game.archive)
        # Calls and pass choices must be representable, with full descriptions.
        self.assertTrue({"타패", "패스", "치", "퐁"}.issubset(seen))

    def test_special_human_actions_apply_and_replay(self):
        from mapago_tools.bots import LegalBot
        for label, seed in (("가깡", 1), ("대명깡", 81), ("암깡", 113),
                            ("론", 163), ("구종구패", 412), ("리치", 948)):
            with self.subTest(action=label, seed=seed):
                game = GameSession(seed=seed)
                human = LegalBot("random-legal", seed ^ 1)
                selected = False
                while game.snapshot()["status"] != "finished":
                    snapshot = game.snapshot()
                    options = snapshot["actions"]
                    fallback = options[human.choose({}, options)]
                    target = next((a for a in options if a["label"] == label), None)
                    action = target if target and not selected else fallback
                    selected = selected or target is not None
                    game.act(snapshot["revision"], action["id"])
                self.assertTrue(selected)
                replay(game.archive)


class HttpGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = GameServer(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, cookie=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        supplied = {"Origin": self.server.origin, "Content-Type": "application/json"}
        if cookie:
            supplied["Cookie"] = cookie
        if headers:
            supplied.update(headers)
        payload = None if body is None else json.dumps(body)
        connection.request(method, path, payload, supplied)
        response = connection.getresponse()
        status, response_headers, data = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return status, response_headers, data

    def create(self):
        status, headers, data = self.request("POST", "/api/game", {})
        self.assertEqual(status, 201, data)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        return headers["Set-Cookie"].split(";")[0], json.loads(data)

    def test_full_hand_via_http_and_replay_download(self):
        cookie, state = self.create()
        moves = 0
        while state["status"] != "finished":
            status, _, data = self.request("POST", "/api/action", {
                "revision": state["revision"], "action_id": choose(state),
            }, cookie)
            self.assertEqual(status, 200, data)
            state = json.loads(data)
            moves += 1
            self.assertLess(moves, 150)
            self.assertTrue(all(not hand for hand in state["state"]["hands"][1:]))
        self.assertEqual(state["result"]["rounds"], 1)
        status, _, record = self.request("GET", "/api/replay", cookie=cookie)
        self.assertEqual(status, 200)
        export = json.loads(record)
        self.assertEqual(export["viewer"], 0)
        self.assertEqual(export["result"]["scores"], state["result"]["scores"])
        self.assertNotIn(b'"seed"', record)
        self.assertNotIn(b'"config"', record)

    def test_session_isolation_reload_and_replacement(self):
        first, initial = self.create()
        second, _ = self.create()
        status, _, _ = self.request("POST", "/api/action", {
            "revision": initial["revision"], "action_id": choose(initial),
        }, first)
        self.assertEqual(status, 200)
        _, _, current = self.request("GET", "/api/game", cookie=first)
        _, _, untouched = self.request("GET", "/api/game", cookie=second)
        self.assertGreater(json.loads(current)["revision"], 0)
        self.assertEqual(json.loads(untouched)["revision"], 0)
        _, replacement, _ = self.request("POST", "/api/game", {}, first)
        self.assertNotEqual(first, replacement["Set-Cookie"].split(";")[0])
        self.assertEqual(self.request("GET", "/api/game", cookie=first)[0], 404)
        self.assertEqual(self.request("GET", "/api/game")[0], 404)

    def test_validation_origins_and_static_boundaries(self):
        cookie, state = self.create()
        self.assertEqual(self.request("POST", "/api/game", {}, headers={"Origin": "https://example.com"})[0], 403)
        self.assertEqual(self.request("GET", "/", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/game", {"seed": 42})[0], 400)
        for path in ("/artifacts/stage2-east.internal.json", "/../AGENTS.md", "/api/game?viewer=1"):
            self.assertEqual(self.request("GET", path, cookie=cookie)[0], 404)
        self.assertEqual(self.request("POST", "/api/action", {"revision": -1, "action_id": 0}, cookie)[0], 409)
        self.assertEqual(self.request("POST", "/api/action", {"revision": 0, "action_id": 999}, cookie)[0], 400)
        self.assertEqual(self.request("GET", "/api/replay", cookie=cookie)[0], 400)
        self.assertEqual(self.request("POST", "/api/game", [], cookie)[0], 400)
        for path, mime in (("/", "text/html"), ("/app.js", "text/javascript"), ("/styles.css", "text/css")):
            status, headers, data = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn(mime, headers["Content-Type"])
            self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertTrue(data)


if __name__ == "__main__":
    unittest.main()
