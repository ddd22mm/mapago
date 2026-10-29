"""One human seat and three bots, independent of HTTP and the browser UI."""

import copy
import secrets
from importlib.metadata import version

from riichienv import ActionType
from riichienv.convert import tid_to_mjai

from mapago_tools.bots import create_bots
from mapago_tools.match import MAX_STEPS, SCHEMA, MatchEngine, digest, make_config

ACTION_NAMES = {
    int(ActionType.DISCARD): "타패", int(ActionType.CHI): "치",
    int(ActionType.PON): "퐁", int(ActionType.DAIMINKAN): "대명깡",
    int(ActionType.RON): "론", int(ActionType.RIICHI): "리치",
    int(ActionType.TSUMO): "쯔모 화료", int(ActionType.PASS): "패스",
    int(ActionType.ANKAN): "암깡", int(ActionType.KAKAN): "가깡",
    int(ActionType.KYUSHU_KYUHAI): "구종구패",
}


class InvalidAction(ValueError):
    pass


class StaleAction(InvalidAction):
    pass


class HumanInput:
    index = None

    def choose(self, observation, legal):
        if self.index is None:
            raise InvalidAction("사용자 행동을 기다리고 있습니다.")
        index, self.index = self.index, None
        return index


class GameSession:
    def __init__(self, rule="mjsoul", policy="random-legal", seed=None):
        seed = secrets.randbits(64) if seed is None else seed
        config = make_config(seed=seed, mode="kyoku", rule=rule, names=[policy] * 4)
        self.bots = create_bots(config["bots"])
        self.human = HumanInput()
        self.bots[0] = self.human
        config["bots"][0] = {"seat": 0, "name": "human", "version": "1"}
        self.engine = MatchEngine(config)
        self.revision = 0
        self.frames = []
        self.events = []
        self.archive = {
            "schema": SCHEMA, "visibility": "internal-only",
            "engine": {"name": "riichienv", "version": version("riichienv")},
            "config": config, "steps": [],
        }
        self.rule, self.policy = rule, policy
        checkpoint, events = self._capture()
        self.archive["initial"] = {"checkpoint": checkpoint, "events": events}
        self._advance_bots()

    def _capture(self):
        checkpoint, events, frame = self.engine.capture(self.revision, viewer=0)
        self.frames.append(frame)
        self.events.extend(frame["events"])
        return checkpoint, events

    def _step(self):
        if self.revision >= MAX_STEPS:
            raise RuntimeError("대국 진행 한도를 초과했습니다.")
        batch = self.engine.choose(self.bots)
        self.engine.apply(batch)
        self.revision += 1
        checkpoint, events = self._capture()
        self.archive["steps"].append({
            "step": self.revision, "actions": batch,
            "checkpoint": checkpoint, "events": events,
        })

    def _advance_bots(self):
        while not self.engine.env.done() and 0 not in self.engine.active:
            self._step()
        if self.engine.env.done():
            self.archive["result"] = self.engine.result(
                self.revision, sum(len(step["actions"]) for step in self.archive["steps"]),
            )
            self.archive["sha256"] = digest({
                key: value for key, value in self.archive.items() if key != "sha256"
            })

    def act(self, revision, action_id):
        if type(revision) is not int or revision != self.revision:
            raise StaleAction("국면이 바뀌었습니다. 현재 화면에서 다시 선택해 주세요.")
        if self.engine.env.done() or 0 not in self.engine.active:
            raise InvalidAction("지금은 행동할 수 없습니다.")
        legal = self.engine.active[0].legal_actions()
        if type(action_id) is not int or action_id not in range(len(legal)):
            raise InvalidAction("선택할 수 없는 행동입니다.")
        self.human.index = action_id
        self._step()
        self._advance_bots()
        return self.snapshot()

    def snapshot(self):
        done = self.engine.env.done()
        state = copy.deepcopy(self.frames[-1]["state"])
        actions = []
        if not done and 0 in self.engine.active:
            for index, action in enumerate(self.engine.active[0].legal_actions()):
                kind = int(action.action_type)
                has_tile = action.tile is not None and kind not in (
                    int(ActionType.PASS), int(ActionType.KYUSHU_KYUHAI),
                )
                tile = tid_to_mjai(action.tile) if has_tile else None
                consumed = [tid_to_mjai(t) for t in action.consume_tiles]
                actions.append({
                    "id": index, "kind": kind, "label": ACTION_NAMES[kind],
                    "tile_id": action.tile if tile else None, "tile": tile,
                    "consumed": consumed,
                })
        state.pop("legal_actions")  # Only send the action choices above.
        start = next(item["event"] for item in reversed(self.events)
                     if item["event"]["type"] == "start_kyoku")
        last = self.events[-1]["event"]
        return {
            "revision": self.revision, "status": "finished" if done else "waiting",
            "viewer": 0, "rule": self.rule, "bot_policy": self.policy,
            "state": state, "actions": actions,
            "round": {key: start[key] for key in ("bakaze", "kyoku", "honba", "oya")},
            "remaining": max(0, len(self.engine.env.wall) - 14),
            "events": copy.deepcopy(self.events[-80:]),
            "last_event": copy.deepcopy(last),
            "result": copy.deepcopy(self.archive.get("result")),
        }

    def seat_replay(self):
        if not self.engine.env.done():
            raise InvalidAction("한 국이 끝난 뒤 기록을 내려받을 수 있습니다.")
        return {
            "schema": "mapago.seat-replay.v1", "viewer": 0,
            "engine": copy.deepcopy(self.archive["engine"]),
            "mode": "kyoku", "rule": self.rule,
            "result": copy.deepcopy(self.archive["result"]),
            "frames": copy.deepcopy(self.frames),
        }
