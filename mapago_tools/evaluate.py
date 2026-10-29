"""Paired single-hand comparison; export aggregates, never private match archives."""

import argparse
import json
from importlib.metadata import version
from pathlib import Path
from statistics import mean

from mapago_tools.match import make_config, play, replay


def metrics(archive, seat):
    scores = archive["result"]["scores"]
    score = scores[seat]
    # Midranks avoid assigning different performance to tied scores by seat order.
    rank = 1 + sum(s > score for s in scores) + (sum(s == score for s in scores) - 1) / 2
    wins = deals = 0
    for step in archive["steps"]:
        for item in step["events"]:
            event = item["event"]
            if event["type"] == "hora":
                wins += event["actor"] == seat
                deals += event["target"] == seat and event["actor"] != seat
    return {"rank": rank, "score_delta": score - 25000,
            "wins": wins, "deal_ins": deals, "rounds": archive["result"]["rounds"]}


def aggregate(rows):
    rounds = sum(row["rounds"] for row in rows)
    return {"seat_samples": len(rows), "rounds": rounds,
            "mean_midrank": mean(row["rank"] for row in rows),
            "mean_score_delta": mean(row["score_delta"] for row in rows),
            "win_count": sum(row["wins"] for row in rows),
            "win_rate": sum(row["wins"] for row in rows) / rounds,
            "deal_in_claim_count": sum(row["deal_ins"] for row in rows),
            "deal_in_claims_per_round": sum(row["deal_ins"] for row in rows) / rounds}


def evaluate(seed_count=16):
    reports = {}
    for rule in ("mjsoul",):
        focal, control, opponents = [], [], []
        for seed in range(seed_count):
            baseline = play(make_config(seed=seed, mode="kyoku", rule=rule))
            replay(baseline)
            for seat in range(4):
                names = ["random-legal"] * 4
                names[seat] = "rule-based"
                mixed = play(make_config(seed=seed, mode="kyoku", rule=rule, names=names))
                replay(mixed)
                focal.append(metrics(mixed, seat))
                control.append(metrics(baseline, seat))
                opponents.extend(metrics(mixed, other) for other in range(4) if other != seat)
            print(f"{rule}: seed block {seed + 1}/{seed_count}", flush=True)
        reports[rule] = {
            "mixed_matches": seed_count * 4, "control_matches": seed_count,
            "rule_based": aggregate(focal), "matched_random_control": aggregate(control),
            "random_opponents": aggregate(opponents),
            "paired_mean_rank_improvement": mean(b["rank"] - a["rank"] for a, b in zip(focal, control)),
            "paired_mean_score_improvement": mean(a["score_delta"] - b["score_delta"] for a, b in zip(focal, control)),
        }
    return {"schema": "mapago.policy-evaluation.v1", "engine_version": version("riichienv"),
            "protocol": {"mode": "kyoku", "seed_blocks_per_rule": seed_count,
                         "seeds": "range(seed_blocks_per_rule)", "dealer": 0,
                         "seat_rotation": "one rule-based seat versus three random-legal seats, all four seats",
                         "control": "same seed, dealer, rule, all random-legal; reuse all four seat results",
                         "policy": "rule-based-v1", "baseline": "random-legal-v1",
                         "replay_verified": True},
            "limitations": ["Single-hand benchmark, not east-round or hanchan strength or a rating",
                            "Seat samples within a seed block are correlated",
                            "Random-legal can decline legal wins and is an integration baseline",
                            "Deal-ins count ron claims; multiple ron can count multiple claims",
                            "No policy parameters are fitted or updated"],
            "results": reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-count", type=int, default=16)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seed_count <= 10000:
        parser.error("seed-count must be 1..10000")
    report = evaluate(args.seed_count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
