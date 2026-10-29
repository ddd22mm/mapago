"""Deterministic, public-information discard policy. Heuristics are not probabilities."""

from riichienv import ActionType, calculate_shanten

POLICY_VERSION = "rule-based-v1"
RED_TILES = {16, 52, 88}


def tile_type(tile_id):
    return tile_id // 4


def _dora_type(indicator):
    kind = tile_type(indicator)
    if kind < 27:
        base = kind - kind % 9
        return base + (kind % 9 + 1) % 9
    if kind < 31:
        return 27 + (kind - 27 + 1) % 4
    return 31 + (kind - 31 + 1) % 3


def visible_counts(observation):
    # Sets avoid counting a called discard twice; only exact public physical IDs count.
    known = set(observation["hands"][observation["player_id"]])
    known.update(observation.get("dora_indicators", []))
    for river in observation["discards"]:
        known.update(river)
    for melds in observation["melds"]:
        for meld in melds:
            known.update(meld["tiles"])
    counts = [0] * 34
    for tile in known:
        counts[tile_type(tile)] += 1
    return [max(0, 4 - n) for n in counts]


def _risk(tile, seat, observation):
    threats = [p for p, active in enumerate(observation["riichi_declared"])
               if active and p != seat]
    if not threats:
        return 0
    kind = tile_type(tile)
    rivers = observation["discards"]
    if any(any(tile_type(t) == kind for t in rivers[p]) for p in threats):
        return 0  # genbutsu
    if kind < 27:
        rank = kind % 9 + 1
        suji = {rank - 3, rank + 3}
        if any(1 <= r <= 9 and any(tile_type(t) % 9 + 1 == r
                                   for t in rivers[p] if tile_type(t) < 27
                                   and tile_type(t) // 9 == kind // 9)
               for p in threats for r in suji):
            return 1
    return 2


def _evaluate_discard(tile, hand, observation, visible):
    rest = list(hand)
    if tile in rest:
        rest.remove(tile)
    else:
        # Some legal-action adapters identify the tile by its 34-kind id.
        match = next((i for i, held in enumerate(rest) if tile_type(held) == tile_type(tile)), None)
        if match is None:
            raise ValueError("Legal discard is not represented in the private hand")
        rest.pop(match)
    shanten = calculate_shanten(rest)
    ukeire = [kind for kind, remaining in enumerate(visible)
              if remaining and calculate_shanten(rest + [kind * 4]) < shanten]
    dora = {_dora_type(ind) for ind in observation.get("dora_indicators", [])}
    value = sum(tile_type(t) in dora or t in RED_TILES for t in rest)
    return (shanten, -sum(visible[k] for k in ukeire), -len(ukeire),
            _risk(tile, observation["player_id"], observation), -value, tile), {
                "shanten": shanten, "ukeire_kinds": len(ukeire),
                "ukeire_visible_copies": sum(visible[k] for k in ukeire),
                "risk_tier": _risk(tile, observation["player_id"], observation),
            }


class RuleBasedBot:
    """Wins when legal; otherwise chooses the lexicographically best legal discard."""

    def __init__(self, name="rule-based", seed=0):
        self.name, self.seed = name, seed
        self.last_decision = None

    def choose(self, observation, legal_actions):
        if not legal_actions:
            raise ValueError("No legal action available")
        kinds = [int(a.action_type) for a in legal_actions]
        for win in (int(ActionType.TSUMO), int(ActionType.RON)):
            if win in kinds:
                self.last_decision = {"policy": POLICY_VERSION, "reason": "legal_win"}
                return kinds.index(win)
        discards = [i for i, kind in enumerate(kinds) if kind == int(ActionType.DISCARD)]
        if not discards:
            # Calls and aborts remain declined unless the engine exposes a legal win.
            passes = [i for i, kind in enumerate(kinds) if kind == int(ActionType.PASS)]
            selected = passes[0] if passes else 0
            self.last_decision = {"policy": POLICY_VERSION, "reason": "conservative_pass"}
            return selected
        hand = observation["hands"][observation["player_id"]]
        visible = visible_counts(observation)
        ranked = []
        for i in discards:
            action = legal_actions[i]
            rank, detail = _evaluate_discard(action.tile, hand, observation, visible)
            ranked.append((rank, i, detail, kinds[i]))
        _, selected, detail, kind = min(ranked)
        if detail["shanten"] == 0 and int(ActionType.RIICHI) in kinds:
            selected = kinds.index(int(ActionType.RIICHI))
            self.last_decision = {
                "policy": POLICY_VERSION, "reason": "declare_riichi_tenpai",
                **detail,
            }
            return selected
        self.last_decision = {
            "policy": POLICY_VERSION,
            "reason": "shanten_ukeire_safety",
            **detail,
        }
        return selected
