"""Four-seat matches and verified action replay with seat-filtered exports.

Internal archives contain seeds and actions. They must never be served to a
game client. Only replay(..., viewer=seat)'s frames are suitable for that seat.
"""

import argparse
import copy
import hashlib
import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path

from riichienv import GameType, RiichiEnv

from mapago_tools.bots import bot_configs, create_bots
from mapago_tools.engine_probe import RULE_PRESETS, check_observation

SCHEMA = "mapago.match.v1"
MODES = {
    "kyoku": GameType.YON_IKKYOKU,
    "east": GameType.YON_TONPUSEN,
    "hanchan": GameType.YON_HANCHAN,
}
MAX_STEPS = 20000
EVENT_FIELDS = {
    "start_game": (),
    "start_kyoku": ("bakaze", "dora_marker", "honba", "kyoku", "kyotaku", "oya", "scores", "tehais"),
    "tsumo": ("actor", "pai"),
    "dahai": ("actor", "pai", "tsumogiri"),
    "chi": ("actor", "target", "pai", "consumed"),
    "pon": ("actor", "target", "pai", "consumed"),
    "daiminkan": ("actor", "target", "pai", "consumed"),
    "ankan": ("actor", "consumed"),
    "kakan": ("actor", "pai", "consumed"),
    "reach": ("actor",),
    "reach_accepted": ("actor", "deltas", "scores"),
    "dora": ("dora_marker",),
    "hora": ("actor", "target", "pai", "deltas", "scores", "uradora_markers"),
    "ryukyoku": ("reason", "deltas", "scores", "tenpais"),
    "end_kyoku": (),
    "end_game": ("scores",),
}
STATE_FIELDS = (
    "player_id", "hands", "melds", "discards", "dora_indicators", "scores",
    "riichi_declared", "legal_actions", "honba", "riichi_sticks", "round_wind", "oya",
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def visible_event(event, viewer):
    """Allowlist fields; unknown events fail instead of leaking upstream additions."""
    kind = event["type"]
    if kind not in EVENT_FIELDS:
        raise ValueError(f"Unsupported event type: {kind}")
    result = {"type": kind}
    result.update({key: copy.deepcopy(event[key]) for key in EVENT_FIELDS[kind] if key in event})
    if kind == "start_kyoku":
        result["tehais"] = [
            hand if seat == viewer else ["?"] * len(hand)
            for seat, hand in enumerate(result["tehais"])
        ]
    if kind == "tsumo" and result["actor"] != viewer:
        result["pai"] = "?"
    return result


def make_config(seed=42, mode="east", rule="tenhou", names=None, dealer=0):
    config = {
        "seed": seed, "mode": mode, "rule": rule, "dealer": dealer,
        "bots": bot_configs(["random-legal"] * 4 if names is None else names, seed),
    }
    validate_config(config)
    return config


def validate_config(config):
    if type(config["seed"]) is not int or not 0 <= config["seed"] < 2**64:
        raise ValueError("seed must be an unsigned 64-bit integer")
    if config["mode"] not in MODES or config["rule"] not in RULE_PRESETS:
        raise ValueError("Unknown game mode or rule preset")
    if type(config["dealer"]) is not int or config["dealer"] not in range(4):
        raise ValueError("Invalid dealer")
    bots = config["bots"]
    if len(bots) != 4 or [bot["seat"] for bot in bots] != list(range(4)):
        raise ValueError("Exactly four ordered seat configurations required")


class MatchEngine:
    """Internal adapter. Bots see only one seat's DTO and legal action tuple."""

    def __init__(self, config):
        validate_config(config)
        self.env = RiichiEnv(
            seed=config["seed"], game_mode=MODES[config["mode"]],
            rule=RULE_PRESETS[config["rule"]](),
        )
        self.active = self.env.reset(oya=config["dealer"], honba=0)
        self.event_cursor = 0
        self.bot_cursors = [0] * 4
        self.states = []

    def capture(self, step, viewer=None):
        self.states = []
        for seat in range(4):
            obs = self.active.get(seat)
            if obs is None:
                obs = self.env.get_observations([seat])[seat]
            check_observation(obs)
            data = obs.to_dict()
            data["melds"] = [[{
                "type": int(meld.meld_type), "tiles": list(meld.tiles),
                "opened": meld.opened, "from_who": meld.from_who,
            } for meld in melds] for melds in data["melds"]]
            self.states.append({key: data[key] for key in STATE_FIELDS})
        events = self.env.mjai_log[self.event_cursor:]
        public_events = [
            {"seq": self.event_cursor + i, "event": visible_event(event, None)}
            for i, event in enumerate(events)
        ]
        frame = None
        if viewer is not None:
            frame = {
                "step": step, "state": copy.deepcopy(self.states[viewer]),
                "events": [
                    {"seq": self.event_cursor + i, "event": visible_event(event, viewer)}
                    for i, event in enumerate(events)
                ],
            }
        checkpoint = digest({"states": self.states, "events": events, "done": self.env.done()})
        self.event_cursor += len(events)
        return checkpoint, public_events, frame

    def choose(self, bots):
        if not self.active:
            raise ValueError("Engine stalled without active seats")
        batch = []
        for seat, observation in sorted(self.active.items()):
            legal = tuple(observation.legal_actions())
            if observation.player_id != seat or not legal:
                raise ValueError("Invalid active observation")
            # Accumulate all events since THIS bot last acted. Observation delta
            # cursors are independent and can be consumed by other captures.
            events = self.env.mjai_log[self.bot_cursors[seat]:]
            view = copy.deepcopy(self.states[seat])
            view["events"] = [visible_event(event, seat) for event in events]
            index = bots[seat].choose(view, legal)
            if type(index) is not int or index not in range(len(legal)):
                raise ValueError("Bot selected an illegal action index")
            self.bot_cursors[seat] = len(self.env.mjai_log)
            batch.append({"seat": seat, "action": legal[index].to_dict()})
        return batch

    def apply(self, batch):
        seats = [item["seat"] for item in batch]
        if len(seats) != len(set(seats)) or set(seats) != set(self.active):
            raise ValueError("Action batch must cover each active seat exactly once")
        actions = {}
        for item in batch:
            seat = item["seat"]
            legal = self.active[seat].legal_actions()
            matches = [action for action in legal if action.to_dict() == item["action"]]
            if not matches:
                raise ValueError("Recorded action is not legal in this state")
            actions[seat] = matches[0]
        self.active = self.env.step(actions)

    def result(self, steps, decisions):
        if not self.env.done():
            raise ValueError("Match has not ended")
        counts = Counter(event["type"] for event in self.env.mjai_log)
        if counts["end_game"] != 1 or counts["start_kyoku"] != counts["end_kyoku"]:
            raise ValueError("Incomplete game events")
        return {
            "steps": steps, "decisions": decisions, "rounds": counts["end_kyoku"],
            "scores": self.env.scores(), "ranks": self.env.ranks(),
            "event_counts": dict(sorted(counts.items())),
            "events_sha256": digest(self.env.mjai_log),
        }


def play(config, max_steps=MAX_STEPS, bots=None):
    if type(max_steps) is not int or not 1 <= max_steps <= MAX_STEPS:
        raise ValueError("Invalid step limit")
    engine = MatchEngine(config)
    bots = create_bots(config["bots"]) if bots is None else bots
    if len(bots) != 4 or len({id(bot) for bot in bots}) != 4:
        raise ValueError("Four independent bot instances required")
    initial, events, _ = engine.capture(0)
    archive = {
        "schema": SCHEMA, "visibility": "internal-only",
        "engine": {"name": "riichienv", "version": version("riichienv")},
        "config": copy.deepcopy(config),
        "initial": {"checkpoint": initial, "events": events}, "steps": [],
    }
    decisions = 0
    while not engine.env.done():
        if len(archive["steps"]) >= max_steps:
            raise ValueError("Match exceeded step limit")
        batch = engine.choose(bots)
        engine.apply(batch)
        step = len(archive["steps"]) + 1
        checkpoint, events, _ = engine.capture(step)
        archive["steps"].append({
            "step": step, "actions": batch, "checkpoint": checkpoint, "events": events,
        })
        decisions += len(batch)
    archive["result"] = engine.result(len(archive["steps"]), decisions)
    archive["sha256"] = digest(archive)
    return archive


def replay(archive, viewer=None):
    """Reapply SAVED actions, without invoking bots; validate every state/event."""
    if viewer is not None and (type(viewer) is not int or viewer not in range(4)):
        raise ValueError("viewer must be a seat from 0 to 3")
    if archive["schema"] != SCHEMA or archive["visibility"] != "internal-only":
        raise ValueError("Unsupported archive schema or visibility")
    if archive["engine"] != {"name": "riichienv", "version": version("riichienv")}:
        raise ValueError("Engine version mismatch")
    if digest({key: value for key, value in archive.items() if key != "sha256"}) != archive["sha256"]:
        raise ValueError("Archive checksum mismatch")
    if not 1 <= len(archive["steps"]) <= MAX_STEPS:
        raise ValueError("Invalid recorded step count")
    engine = MatchEngine(archive["config"])
    checkpoint, events, frame = engine.capture(0, viewer)
    if {"checkpoint": checkpoint, "events": events} != archive["initial"]:
        raise ValueError("Initial state/event mismatch")
    frames = [frame] if frame is not None else []
    decisions = 0
    for step, record in enumerate(archive["steps"], 1):
        if record["step"] != step or engine.env.done():
            raise ValueError("Invalid step order or actions after game end")
        engine.apply(record["actions"])
        checkpoint, events, frame = engine.capture(step, viewer)
        if checkpoint != record["checkpoint"] or events != record["events"]:
            raise ValueError(f"State/event mismatch at step {step}")
        decisions += len(record["actions"])
        if frame is not None:
            frames.append(frame)
    result = engine.result(len(archive["steps"]), decisions)
    if result != archive["result"]:
        raise ValueError("Final result mismatch")
    return {"verified": True, **result}, frames


def save_json(path, value):
    """Exclusive creation: don't silently overwrite an existing match record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description="마파고 4봇 자동 대국 및 검증 재생")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--mode", choices=MODES, default="east")
    run.add_argument("--rule", choices=RULE_PRESETS, default="tenhou")
    run.add_argument("--dealer", type=int, choices=range(4), default=0)
    run.add_argument("--bots", default=",".join(["random-legal"] * 4))
    run.add_argument("--max-steps", type=int, default=MAX_STEPS)
    run.add_argument("--output", type=Path, required=True, help="외부 공개 금지: 내부 재현 기록")
    review = commands.add_parser("replay")
    review.add_argument("archive", type=Path)
    review.add_argument("--viewer", type=int, choices=range(4))
    review.add_argument("--output", type=Path, help="선택 좌석의 복기 프레임 JSON")
    args = parser.parse_args()
    try:
        if args.command == "run":
            config = make_config(args.seed, args.mode, args.rule, args.bots.split(","), args.dealer)
            archive = play(config, args.max_steps)
            report, _ = replay(archive)  # Never persist an unverified match.
            save_json(args.output, archive)
        else:
            if args.output is not None and args.viewer is None:
                raise ValueError("--output requires --viewer")
            archive = json.loads(args.archive.read_text(encoding="utf-8"))
            report, frames = replay(archive, args.viewer)
            if args.output:
                save_json(args.output, {
                    "schema": "mapago.seat-replay.v1", "viewer": args.viewer,
                    "engine": archive["engine"],
                    "mode": archive["config"]["mode"], "rule": archive["config"]["rule"],
                    "result": report, "frames": frames,
                })
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
        parser.exit(1, f"Match failed: {exc}\n")


if __name__ == "__main__":
    main()
