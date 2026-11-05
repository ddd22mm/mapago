"""Lightweight, legal-action-constrained Mahjong Soul imitation policy."""

import json
from pathlib import Path

from riichienv import ActionType, calculate_shanten

from mapago_tools.strategy import RED_TILES, tile_type

POLICY_VERSION = "mjsoul-imitation-v1"
TENHOU_POLICY_VERSION = "tenhou-imitation-v1"
FEATURES = (
    "bias", "own_copies", "left_2", "left_1", "right_1", "right_2",
    "visible_copies", "dora", "red_five", "safe_tier",
)
MODEL_PATH = Path(__file__).resolve().parents[1] / ".research" / "models" / f"{POLICY_VERSION}.json"
TENHOU_MODEL_PATH = Path(__file__).resolve().parents[1] / ".research" / "models" / f"{TENHOU_POLICY_VERSION}.json"


def _neighbors(kind):
    if kind >= 27:
        return [None] * 4
    suit_start = kind // 9 * 9
    rank = kind % 9
    return [suit_start + rank + offset if 0 <= rank + offset < 9 else None
            for offset in (-2, -1, 1, 2)]


def _dora_kind(indicator):
    kind = tile_type(indicator)
    if kind < 27:
        return kind - kind % 9 + (kind % 9 + 1) % 9
    if kind < 31:
        return 27 + (kind - 27 + 1) % 4
    return 31 + (kind - 31 + 1) % 3


def _safe_tier(tile, seat, observation):
    kind = tile_type(tile)
    threats = [p for p, active in enumerate(observation["riichi_declared"])
               if active and p != seat]
    if not threats:
        return 0.0
    rivers = observation["discards"]
    if any(any(tile_type(t) == kind for t in rivers[p]) for p in threats):
        return 1.0
    if kind < 27:
        rank = kind % 9 + 1
        suji = (rank - 3, rank + 3)
        if any(1 <= r <= 9 and any(tile_type(t) % 9 + 1 == r
                                   for t in rivers[p] if tile_type(t) < 27
                                   and tile_type(t) // 9 == kind // 9)
               for p in threats for r in suji):
            return 0.5
    return 0.0


def _visible_copies(observation):
    seat = observation["player_id"]
    known = set(observation["hands"][seat])
    known.update(observation.get("dora_indicators", []))
    for river in observation["discards"]:
        known.update(river)
    for melds in observation["melds"]:
        for meld in melds:
            tiles = meld["tiles"] if isinstance(meld, dict) else meld.tiles
            known.update(tiles)
    counts = [0] * 34
    for tile in known:
        counts[tile_type(tile)] += 1
    return [max(0, 4 - count) for count in counts]


def candidate_features(tile, observation):
    """Build only from the acting player's hand and currently public information."""
    seat = observation["player_id"]
    hand = observation["hands"][seat]
    kind = tile_type(tile)
    counts = [0] * 34
    for held in hand:
        counts[tile_type(held)] += 1
    neighbors = _neighbors(kind)
    visible = _visible_copies(observation)
    dora = {_dora_kind(ind) for ind in observation.get("dora_indicators", [])}
    return [
        1.0,
        counts[kind] / 4.0,
        (counts[neighbors[0]] / 4.0) if neighbors[0] is not None else 0.0,
        (counts[neighbors[1]] / 4.0) if neighbors[1] is not None else 0.0,
        (counts[neighbors[2]] / 4.0) if neighbors[2] is not None else 0.0,
        (counts[neighbors[3]] / 4.0) if neighbors[3] is not None else 0.0,
        visible[kind] / 4.0,
        float(kind in dora),
        float(tile in RED_TILES),
        _safe_tier(tile, seat, observation),
    ]


def _discard_actions(legal_actions):
    return [(index, action) for index, action in enumerate(legal_actions)
            if int(action.action_type) == int(ActionType.DISCARD)]


class ImitationBot:
    def __init__(self, model_path=MODEL_PATH):
        with Path(model_path).open(encoding="utf-8") as stream:
            model = json.load(stream)
        if model.get("policy") not in (POLICY_VERSION, TENHOU_POLICY_VERSION) or tuple(model.get("features", ())) != FEATURES:
            raise ValueError("Unsupported imitation model")
        self.policy = model["policy"]
        self.weights = model["weights"]
        if len(self.weights) != 34 or any(len(row) != len(FEATURES) for row in self.weights):
            raise ValueError("Invalid imitation model weight shape")
        self.name = self.policy
        self.last_decision = None

    def choose(self, observation, legal_actions):
        if not legal_actions:
            raise ValueError("No legal action available")
        kinds = [int(a.action_type) for a in legal_actions]
        for win in (int(ActionType.TSUMO), int(ActionType.RON)):
            if win in kinds:
                self.last_decision = {"policy": self.policy, "reason": "legal_win"}
                return kinds.index(win)
        discards = _discard_actions(legal_actions)
        if not discards:
            passes = [i for i, kind in enumerate(kinds) if kind == int(ActionType.PASS)]
            selected = passes[0] if passes else 0
            self.last_decision = {"policy": self.policy, "reason": "conservative_pass"}
            return selected
        ranked = []
        for index, action in discards:
            features = candidate_features(action.tile, observation)
            score = sum(weight * feature for weight, feature in
                        zip(self.weights[tile_type(action.tile)], features, strict=True))
            ranked.append((score, index, action))
        _, selected, action = max(ranked, key=lambda row: (row[0], -row[2].tile))
        hand = observation["hands"][observation["player_id"]]
        rest = list(hand)
        if action.tile in rest:
            rest.remove(action.tile)
        else:
            match = next((i for i, held in enumerate(rest)
                          if tile_type(held) == tile_type(action.tile)), None)
            if match is None:
                raise ValueError("Legal discard is not represented in the private hand")
            rest.pop(match)
        if calculate_shanten(rest) == 0 and int(ActionType.RIICHI) in kinds:
            selected = kinds.index(int(ActionType.RIICHI))
            reason = "declare_riichi_tenpai"
        else:
            reason = "learned_discard_ranking"
        self.last_decision = {"policy": self.policy, "reason": reason}
        return selected


def evaluate_decision(observation, legal_actions, expert_action, weights):
    discards = _discard_actions(legal_actions)
    expert_type = int(expert_action.action_type)
    if expert_type != int(ActionType.DISCARD) or len(discards) < 2:
        return None
    target = None
    features, tile_kinds = [], []
    for index, action in discards:
        if action.to_dict() == expert_action.to_dict():
            target = len(features)
        features.append(candidate_features(action.tile, observation))
        tile_kinds.append(tile_type(action.tile))
    if target is None:
        raise ValueError("Expert discard is absent from the engine legal-action list")
    scores = [sum(weight * feature for weight, feature in
                  zip(weights[kind], row, strict=True)) for kind, row in zip(tile_kinds, features, strict=True)]
    return features, tile_kinds, target, max(range(len(scores)), key=lambda index: scores[index])
