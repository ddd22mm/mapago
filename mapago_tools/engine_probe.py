"""Run one deterministic hand; never export the engine's omniscient log."""

import argparse
import hashlib
import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path

from riichienv import GameRule, GameType, RiichiEnv

POLICY_VERSION = "first-legal-v1"
RULE_PRESETS = {
    "tenhou": GameRule.default_tenhou,
    "mjsoul": GameRule.default_mjsoul,
}


def check_observation(observation):
    """Fail closed if the tested engine observation leaks concealed information."""
    data = observation.to_dict()
    seat = observation.player_id
    if data["player_id"] != seat:
        raise RuntimeError("Observation seat mismatch")
    for player, hand in enumerate(data["hands"]):
        if player != seat and hand:
            raise RuntimeError("Opponent hand exposed")
    for raw_event in data["events"]:
        event = json.loads(raw_event) if isinstance(raw_event, str) else raw_event
        if {"seed", "wall", "salt"} & event.keys():
            raise RuntimeError("Private engine metadata exposed")
        if event["type"] == "start_kyoku":
            for player, hand in enumerate(event["tehais"]):
                if player != seat and any(tile != "?" for tile in hand):
                    raise RuntimeError("Opponent initial hand exposed")
        if event["type"] == "tsumo" and event["actor"] != seat:
            if event.get("pai") != "?":
                raise RuntimeError("Opponent draw exposed")


def run_hand(seed=42, rule="tenhou", max_steps=2000):
    """Probe the engine with a trivial first-legal policy, not a strength baseline.

    Full events and decisions remain in memory only. The returned summary omits
    the seed, hands, wall and action trace; it is not a gameplay API or replay.
    """
    if not 0 <= seed < 2**64:
        raise ValueError("seed must be an unsigned 64-bit integer")
    if rule not in RULE_PRESETS:
        raise ValueError("Unknown rule preset")
    if max_steps < 1:
        raise ValueError("max_steps must be positive")
    env = RiichiEnv(
        game_mode=GameType.YON_IKKYOKU,
        rule=RULE_PRESETS[rule](),
        seed=seed,
    )
    observations = env.reset(oya=0, honba=0)
    decisions = []
    observed_seats = set()
    steps = 0
    while not env.done():
        if steps >= max_steps:
            raise RuntimeError("Hand exceeded step limit")
        if not observations:
            raise RuntimeError("Engine stalled without an active player")
        actions = {}
        for seat, observation in sorted(observations.items()):
            check_observation(observation)
            if observation.player_id != seat:
                raise RuntimeError("Active seat mismatch")
            observed_seats.add(seat)
            legal = observation.legal_actions()
            if not legal:
                raise RuntimeError("Active player has no legal action")
            # Pass the actual engine-provided Action; do not construct a move.
            actions[seat] = legal[0]
        decisions.append({seat: action.to_dict() for seat, action in actions.items()})
        observations = env.step(actions)
        steps += 1

    events = env.mjai_log  # Private: contains all players' initial hands/draws.
    counts = Counter(event["type"] for event in events)
    if counts["start_kyoku"] != 1 or counts["end_kyoku"] != 1:
        raise RuntimeError("Expected exactly one completed hand")
    if counts["hora"] + counts["ryukyoku"] < 1 or counts["end_game"] != 1:
        raise RuntimeError("Missing hand/game result")
    # Hash every event and action, not just the final scores, for repeatability.
    encoded = json.dumps(
        {"events": events, "decisions": decisions},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return {
        "engine": "riichienv",
        "engine_version": version("riichienv"),
        "game_mode": "YON_IKKYOKU",
        "rule_preset": rule,
        "policy_version": POLICY_VERSION,
        "steps": steps,
        "decisions": sum(len(batch) for batch in decisions),
        "observed_seats": sorted(observed_seats),
        "scores": env.scores(),
        "ranks": env.ranks(),
        "event_counts": dict(sorted(counts.items())),
        "trace_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description="마파고 1단계: 엔진 한 국 실행·재현 확인")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rule", choices=RULE_PRESETS, default="tenhou")
    parser.add_argument("--max-steps", type=int, default=2000)
    parser.add_argument("--output", type=Path, help="정보를 제한한 검증 요약 JSON 저장")
    args = parser.parse_args()
    try:
        first = run_hand(args.seed, args.rule, args.max_steps)
        second = run_hand(args.seed, args.rule, args.max_steps)
        if first != second:
            raise RuntimeError("Fixed-seed trace did not reproduce")
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f"Engine probe failed: {exc}\n")
    report = {**first, "reproducible": True}
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
