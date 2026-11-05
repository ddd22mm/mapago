"""Train a CPU-sized legal-action imitation ranker from local Mahjong Soul MJAI shards."""

import argparse
import hashlib
import json
import random
import tarfile
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np
import zstandard
from riichienv import ActionType, MjaiReplay

from mapago_tools.mjsoul_model import (FEATURES, MODEL_PATH, POLICY_VERSION,
                                       TENHOU_MODEL_PATH, TENHOU_POLICY_VERSION, candidate_features)

DEFAULT_DATA = Path(__file__).resolve().parents[1] / ".research" / "majsoul-paipu"


def sample_members(data_dir, years, per_shard, seed, source="mjsoul"):
    """Reservoir-sample game files uniformly from each selected TAR without extracting archives."""
    rng = random.Random(seed)
    samples, archive_stats = [], []
    for year in years:
        ranks = ("jade", "throne") if source == "mjsoul" else ("houou",)
        for rank in ranks:
            path = data_dir / (f"majsoul-{rank}-{year}.tar" if source == "mjsoul"
                               else f"tenhou-houou-{year}.tar")
            if not path.exists():
                raise FileNotFoundError(path)
            reservoir = []
            seen = 0
            with tarfile.open(path, "r:") as archive:
                for member in archive:
                    if not member.isfile() or not member.name.endswith(".mjai.json.zst"):
                        continue
                    seen += 1
                    entry = member
                    if len(reservoir) < per_shard:
                        reservoir.append(entry)
                    else:
                        index = rng.randrange(seen)
                        if index < per_shard:
                            reservoir[index] = entry
            rng.shuffle(reservoir)
            samples.extend((path, member) for member in reservoir)
            archive_stats.append({"shard": path.name, "games_seen": seen,
                                  "games_sampled": len(reservoir), "bytes": path.stat().st_size})
            print(f"indexed {path.name}: {seen:,} games; sampled {len(reservoir)}", flush=True)
    return samples, archive_stats


def _examples_from_mjai(path, weights, training, rng, learning_rate, rule="mjsoul"):
    replay = MjaiReplay.from_jsonl(str(path), rule=rule)
    stats = Counter()
    for kyoku in replay.take_kyokus():
        for _, observation, expert in kyoku.steps(skip_single_action=False):
            if int(expert.action_type) != int(ActionType.DISCARD):
                continue
            legal = observation.legal_actions()
            discard_actions = [(i, action) for i, action in enumerate(legal)
                               if int(action.action_type) == int(ActionType.DISCARD)]
            if len(discard_actions) < 2:
                continue
            candidates, tiles, target = [], [], None
            state = observation.to_dict()
            for index, action in discard_actions:
                observed_action = action.to_dict()
                expert_fields = expert.to_dict()
                if (observed_action["type"], observed_action.get("tile"),
                    observed_action.get("consume_tiles", [])) == (
                    expert_fields["type"], expert_fields.get("tile"),
                    expert_fields.get("consume_tiles", [])):
                    target = len(candidates)
                candidates.append(candidate_features(action.tile, state))
                tiles.append(action.tile // 4)
            if target is None:
                raise ValueError("Expert discard missing from engine legal action list")
            x = np.asarray(candidates, dtype=np.float64)
            tile_kinds = np.asarray(tiles, dtype=np.int64)
            scores = np.einsum("ij,ij->i", weights[tile_kinds], x)
            predicted = int(np.argmax(scores))
            stats["decisions"] += 1
            stats["correct"] += predicted == target
            if training:
                logits = scores - scores.max()
                probs = np.exp(logits)
                probs /= probs.sum()
                probs[target] -= 1.0
                gradient = np.zeros_like(weights)
                np.add.at(gradient, tile_kinds, probs[:, None] * x)
                weights -= learning_rate * (gradient + 1e-4 * weights)
                stats["updates"] += 1
    return stats


def process_samples(samples, weights, data_dir, *, training, rng, learning_rate=0.03, rule="mjsoul"):
    stats = Counter()
    per_shard = {}
    decompress = zstandard.ZstdDecompressor()
    current_archive = None
    archive = None
    try:
        for path, member in samples:
            if path != current_archive:
                if archive is not None:
                    archive.close()
                archive = tarfile.open(path, "r:")
                current_archive = path
            try:
                with archive.extractfile(member) as compressed:
                    with decompress.stream_reader(compressed) as reader:
                        with tempfile.NamedTemporaryFile("wb", suffix=".mjson", delete=True) as raw:
                            while chunk := reader.read(1024 * 1024):
                                raw.write(chunk)
                            raw.flush()
                            game_weights = weights.copy() if training else weights
                            game_stats = _examples_from_mjai(raw.name, game_weights, training, rng, learning_rate, rule)
                if training:
                    weights[:] = game_weights
            except Exception:
                # Skip the whole match on any replay/deserialization mismatch; never learn from a partial game.
                stats["rejected_games"] += 1
                stats["games_seen"] += 1
                shard_stats = per_shard.setdefault(path.name, Counter())
                shard_stats["games_seen"] += 1
                shard_stats["games_rejected"] += 1
                if stats["games_seen"] % 100 == 0:
                    print(f"processing: {stats['games_seen']}/{len(samples)} games, "
                          f"accepted={stats['games']}, rejected={stats['rejected_games']}", flush=True)
                continue
            stats.update(game_stats)
            stats["games"] += 1
            stats["games_seen"] += 1
            shard_stats = per_shard.setdefault(path.name, Counter())
            shard_stats["games_seen"] += 1
            shard_stats["games_replayed"] += 1
            if stats["games_seen"] % 100 == 0:
                print(f"{'training' if training else 'evaluating'}: {stats['games_seen']}/{len(samples)} games, "
                      f"{stats['decisions']:,} decisions", flush=True)
    finally:
        if archive is not None:
            archive.close()
    stats["per_shard_replay"] = [
        {"shard": name, "games_seen": int(row["games_seen"]),
         "games_replayed": int(row["games_replayed"]),
         "games_rejected": int(row["games_rejected"]),
         "replay_failure_rate": row["games_rejected"] / row["games_seen"]}
        for name, row in sorted(per_shard.items())
    ]
    return stats


def _summary(stats):
    total = int(stats["decisions"])
    return {"games_seen": int(stats["games_seen"]), "games_replayed": int(stats["games"]),
            "games_rejected": int(stats["rejected_games"]), "discard_decisions": total,
            "expert_action_top1_accuracy": (int(stats["correct"]) / total if total else None),
            "per_shard_replay": stats.get("per_shard_replay", [])}


def train(data_dir=DEFAULT_DATA, per_shard=120, epochs=4, seed=20261105,
          model_path=None, report_path=None, source="mjsoul"):
    if source not in ("mjsoul", "tenhou"):
        raise ValueError("source must be mjsoul or tenhou")
    rule = source
    policy = POLICY_VERSION if source == "mjsoul" else TENHOU_POLICY_VERSION
    model_path = model_path or (MODEL_PATH if source == "mjsoul" else TENHOU_MODEL_PATH)
    start = time.time()
    train_samples, train_archives = sample_members(data_dir, range(2019, 2025), per_shard, seed, source)
    validation_samples, validation_archives = sample_members(data_dir, (2025,), per_shard, seed + 1, source)
    test_samples, test_archives = sample_members(data_dir, (2026,), per_shard, seed + 2, source)
    weights = np.zeros((34, len(FEATURES)), dtype=np.float64)
    rng = np.random.default_rng(seed)
    epoch_reports = []
    for epoch in range(epochs):
        order = list(train_samples)
        random.Random(seed + epoch).shuffle(order)
        stats = process_samples(order, weights, data_dir, training=True, rng=rng, rule=rule,
                                learning_rate=0.03 / (1.0 + epoch * 0.25))
        epoch_reports.append(_summary(stats))
        validation = process_samples(validation_samples, weights, data_dir, training=False, rng=rng, rule=rule)
        epoch_reports[-1]["validation"] = _summary(validation)
        print(f"epoch {epoch + 1}/{epochs}: {_summary(stats)} validation={_summary(validation)}", flush=True)
    test_stats = process_samples(test_samples, weights, data_dir, training=False, rng=rng, rule=rule)
    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model = {"policy": policy, "features": list(FEATURES),
             "training": {"source": "Mahjong Soul Jade/Throne MJAI" if source == "mjsoul" else "Tenhou Houou MJAI",
                          "years": "2019-2024",
                          "epochs": epochs, "seed": seed}, "weights": weights.tolist()}
    with model_path.open("x", encoding="utf-8") as stream:
        json.dump(model, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
    report = {
        "schema": f"mapago.{source}-training.v1", "policy": policy,
        "dataset": {"source": "nikketryhard/tenhou-houou-mjai",
                    "source_url": "https://huggingface.co/datasets/nikketryhard/tenhou-houou-mjai",
                    "license_label": "other",
                    "source_data_rights": ("not granted by the dataset card; Mahjong Soul upstream rights remain unresolved"
                                            if source == "mjsoul" else
                                            "dataset card labels other; upstream repository explicitly grants no CC BY rights over Tenhou logs; original rights remain with Tenhou/C-EGG and upstream terms must be confirmed"),
                    "train_archives": train_archives, "validation_archives": validation_archives,
                    "test_archives": test_archives},
        "protocol": {"rule": rule, "train_years": "2019-2024",
                     "validation_years": [2025], "test_years": [2026],
                     "sampling": ("uniform reservoir sample per Jade/Throne yearly TAR" if source == "mjsoul"
                                  else "uniform reservoir sample per yearly Tenhou Houou TAR"),
                     "max_games_per_shard": per_shard,
                     "input": "RiichiEnv MjaiReplay acting-seat observation; no opponent hands or future draws",
                     "target": "human discard among legal discard actions",
                     "training": "linear tile-conditioned softmax ranker, online cross-entropy SGD",
                     "epochs": epochs, "seed": seed},
        "training_epochs": epoch_reports, "heldout_2026": _summary(test_stats),
        "model_path": str(model_path), "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "duration_seconds": round(time.time() - start, 2),
        "limitations": ["Action agreement measures imitation, not optimal play or playing strength",
                        "Only discard choices are learned; legal wins remain automatic and calls remain conservative passes",
                        ("Source dataset license is other and upstream rights remain unresolved; model/data are not cleared for redistribution"
                         if source == "mjsoul" else
                         "Dataset card says other and upstream repository grants no CC BY rights over Tenhou logs; independently confirm terms with the rights holder before redistribution")]
    }
    if report_path:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--source", choices=("mjsoul", "tenhou"), default="mjsoul")
    parser.add_argument("--per-shard", type=int, default=120)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261105)
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    if args.per_shard < 1 or args.epochs < 1:
        parser.error("per-shard and epochs must be positive")
    data_dir = args.data_dir
    if args.source == "tenhou" and data_dir == DEFAULT_DATA:
        data_dir = DEFAULT_DATA.parent / "tenhou-paipu"
    report = train(data_dir, args.per_shard, args.epochs, args.seed, args.model, args.report, args.source)
    print(json.dumps({"model": report["model_path"], "heldout_2026": report["heldout_2026"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
