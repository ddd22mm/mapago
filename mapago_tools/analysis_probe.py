"""Small closed-hand shanten cross-check; requires the research dependency group."""

import json

from mahjong.shanten import Shanten
from riichienv import calculate_shanten, parse_hand

CASES = (
    ("123m123p123s111z22z", -1),
    ("123m123p123s111z2z", 0),
    ("11223344556677m", -1),
    ("19m19p19s1234567z", 0),
)


def main():
    results = []
    for hand, expected in CASES:
        tiles, _ = parse_hand(hand)
        counts = [0] * 34
        for tile in tiles:
            counts[tile // 4] += 1
        engine = calculate_shanten(tiles)
        helper = Shanten().calculate_shanten(counts)
        if engine != expected or helper != expected:
            raise RuntimeError(f"Shanten mismatch for {hand}: {engine}, {helper}")
        results.append({"hand": hand, "expected": expected, "engine": engine, "helper": helper})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
