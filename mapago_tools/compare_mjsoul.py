"""Compare the learned Mahjong Soul policy with rule-based-v1 in seat-rotated hanchan."""

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from statistics import mean

from mapago_tools.evaluate import aggregate, metrics
from mapago_tools.match import make_config, play, replay
from mapago_tools.mjsoul_model import (MODEL_PATH, TENHOU_MODEL_PATH, POLICY_VERSION, TENHOU_POLICY_VERSION)


def evaluate(seed_count=16, first_seed=20261105, rule="mjsoul", model_path=None):
    policy = POLICY_VERSION if rule == "mjsoul" else TENHOU_POLICY_VERSION
    bot_name = "mjsoul-imitation" if rule == "mjsoul" else "tenhou-imitation"
    model_path = Path(model_path or (MODEL_PATH if rule == "mjsoul" else TENHOU_MODEL_PATH))
    model_rows, baseline_rows, paired = [], [], []
    match_count = 0
    for offset in range(seed_count):
        seed = first_seed + offset
        seed_model, seed_baseline = [], []
        for seat in range(4):
            names = ["rule-based"] * 4
            names[seat] = bot_name
            config = make_config(seed=seed, mode="hanchan", rule=rule, names=names)
            config["bots"][seat]["settings"]["model_path"] = str(model_path)
            archive = play(config)
            replay(archive)
            match_count += 1
            seed_model.append(metrics(archive, seat))
            seed_baseline.extend(metrics(archive, other) for other in range(4) if other != seat)
        model_rows.extend(seed_model)
        baseline_rows.extend(seed_baseline)
        paired.append({"seed": seed,
                       "model_mean_rank": mean(row["rank"] for row in seed_model),
                       "baseline_mean_rank": mean(row["rank"] for row in seed_baseline),
                       "model_mean_score_delta": mean(row["score_delta"] for row in seed_model),
                       "baseline_mean_score_delta": mean(row["score_delta"] for row in seed_baseline)})
        print(f"seed block {offset + 1}/{seed_count} complete ({match_count} matches)", flush=True)
    return {
        "schema": f"mapago.{rule}-comparison.v1", "engine_version": version("riichienv"),
        "protocol": {"mode": "hanchan", "rule": rule, "seed_blocks": seed_count,
                     "seeds": f"{first_seed}..{first_seed + seed_count - 1}",
                     "seat_rotation": "one learned policy against three rule-based-v1 bots, each seat per seed",
                     "replay_verified": True, "model": policy,
                     "baseline": "rule-based-v1"},
        "matches": match_count,
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "data_rights": ("Dataset card license is other; source rights remain unresolved; checkpoint not redistributed"
                        if rule == "mjsoul" else
                        "Dataset card license is other; upstream grants no CC BY rights over Tenhou logs; rights holder terms unresolved; checkpoint stays local"),
        "model": aggregate(model_rows), "baseline_opponents": aggregate(baseline_rows),
        "paired_mean_rank_improvement": mean(row["baseline_mean_rank"] - row["model_mean_rank"]
                                              for row in paired),
        "paired_mean_score_improvement": mean(row["model_mean_score_delta"] - row["baseline_mean_score_delta"]
                                               for row in paired),
        "limitations": ["Exploratory finite-sample hanchan benchmark; not a rating",
                        "Baseline rows are opponents from the same mixed matches, so outcomes are correlated",
                        ("Model imitates Jade/Throne discard choices; action agreement and playing strength differ"
                         if rule == "mjsoul" else
                         "Model imitates Tenhou Houou discard choices; action agreement and playing strength differ"),
                        "No policy tuning on benchmark seeds"]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-count", type=int, default=16)
    parser.add_argument("--rule", choices=("mjsoul", "tenhou"), default="mjsoul")
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--first-seed", type=int, default=20261105)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seed_count <= 10000:
        parser.error("seed-count must be 1..10000")
    report = evaluate(args.seed_count, args.first_seed, args.rule, args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"model": report["model"], "baseline": report["baseline_opponents"],
                      "paired_mean_rank_improvement": report["paired_mean_rank_improvement"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
