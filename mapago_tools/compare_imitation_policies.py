"""Compare source-specific imitation bots and an 80/20 blend on identical Mahjong Soul hanchan conditions."""

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from statistics import mean

from mapago_tools.evaluate import aggregate, metrics
from mapago_tools.match import make_config, play, replay
from mapago_tools.mjsoul_model import (
    MODEL_PATH, MIXED_POLICY_VERSION, MixedImitationBot, POLICY_VERSION,
    TENHOU_MODEL_PATH, TENHOU_POLICY_VERSION,
)

POLICIES = {
    "tenhou": ("tenhou-imitation", TENHOU_POLICY_VERSION, TENHOU_MODEL_PATH),
    "mjsoul": ("mjsoul-imitation", POLICY_VERSION, MODEL_PATH),
    "mixed_80_20": ("mixed-imitation", MIXED_POLICY_VERSION, None),
}


def evaluate(seed_count=16, first_seed=20261105, rule="mjsoul"):
    if rule not in ("mjsoul", "tenhou"):
        raise ValueError("rule must be mjsoul or tenhou")
    reports = {}
    for label, (bot_name, policy, path) in POLICIES.items():
        rows, baseline_rows, paired = [], [], []
        for offset in range(seed_count):
            seed = first_seed + offset
            seed_rows, seed_baseline = [], []
            for seat in range(4):
                names = ["rule-based"] * 4
                names[seat] = bot_name
                config = make_config(seed=seed, mode="hanchan", rule=rule, names=names)
                if label == "mixed_80_20":
                    config["bots"][seat]["settings"].update({
                        "tenhou_model_path": str(TENHOU_MODEL_PATH),
                        "mjsoul_model_path": str(MODEL_PATH),
                        "tenhou_weight": 0.8,
                    })
                else:
                    config["bots"][seat]["settings"]["model_path"] = str(path)
                archive = play(config)
                replay(archive)
                focal = metrics(archive, seat)
                opponents = [metrics(archive, other) for other in range(4) if other != seat]
                rows.append(focal)
                baseline_rows.extend(opponents)
                seed_rows.append(focal)
                seed_baseline.extend(opponents)
            paired.append({
                "seed": seed,
                "model_mean_rank": mean(row["rank"] for row in seed_rows),
                "baseline_mean_rank": mean(row["rank"] for row in seed_baseline),
                "model_mean_score_delta": mean(row["score_delta"] for row in seed_rows),
                "baseline_mean_score_delta": mean(row["score_delta"] for row in seed_baseline),
            })
            print(f"{label}: seed block {offset + 1}/{seed_count} complete", flush=True)
        reports[label] = {
            "policy": policy,
            "matches": seed_count * 4,
            "model_sha256": (hashlib.sha256(Path(path).read_bytes()).hexdigest()
                             if path else None),
            "model": aggregate(rows),
            "baseline_opponents": aggregate(baseline_rows),
            "paired_mean_rank_improvement": mean(
                row["baseline_mean_rank"] - row["model_mean_rank"] for row in paired),
            "paired_mean_score_improvement": mean(
                row["model_mean_score_delta"] - row["baseline_mean_score_delta"] for row in paired),
            "paired_seed_blocks": paired,
        }
    model_hashes = {
        "tenhou": hashlib.sha256(TENHOU_MODEL_PATH.read_bytes()).hexdigest(),
        "mjsoul": hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
        "mixed_80_20": MixedImitationBot().model_sha256,
    }
    reports["mixed_80_20"]["model_sha256"] = model_hashes["mixed_80_20"]
    return {
        "schema": "mapago.imitation-mixture-comparison.v1",
        "engine_version": version("riichienv"),
        "protocol": {
            "mode": "hanchan", "rule": rule, "seed_blocks": seed_count,
            "seeds": f"{first_seed}..{first_seed + seed_count - 1}",
            "seat_rotation": "each policy played each seat against three rule-based-v1 bots per seed",
            "paired_conditions": "all policies use the same rule, seeds, seats, and baseline policy",
            "replay_verified": True,
            "mixture": {"weights": {"tenhou": 0.8, "mjsoul": 0.2},
                        "method": "linear blend of source-specific ranker weights",
                        "model_sha256_scope": "canonical JSON of mixture policy id, features, and blended weights"},
            "model_sha256": model_hashes,
            "baseline": "rule-based-v1",
        },
        "policies": reports,
        "data_rights": "Both dataset cards label rights as other. Tenhou upstream grants no CC BY rights over logs; Mahjong Soul rights remain unresolved. All checkpoints remain local.",
        "limitations": [
            "Exploratory finite-sample hanchan benchmark; not a rating",
            "Baseline rows share matches with focal policies and are correlated",
            "Action imitation agreement is not playing strength",
            "The 80/20 blend is a fixed experimental choice, not an optimized ratio",
            "Mahjong Soul training sample had high Jade shard replay rejection; see its replay audit",
            "Source data rights are unresolved; checkpoints are not redistributed",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-count", type=int, default=16)
    parser.add_argument("--first-seed", type=int, default=20261105)
    parser.add_argument("--rule", choices=("mjsoul", "tenhou"), default="mjsoul")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seed_count <= 10000:
        parser.error("seed-count must be 1..10000")
    report = evaluate(args.seed_count, args.first_seed, args.rule)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({name: value["model"] for name, value in report["policies"].items()},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
