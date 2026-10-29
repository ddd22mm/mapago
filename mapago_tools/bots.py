"""Small legal-action policies for engine integration, not measured AI strength."""

import random

from mapago_tools.strategy import POLICY_VERSION, RuleBasedBot


class LegalBot:
    def __init__(self, name, seed):
        if name not in ("first-legal", "random-legal"):
            raise ValueError("Unknown bot policy")
        self.name = name
        self.rng = random.Random(seed)

    def choose(self, observation, legal_actions):
        """Return an index into the supplied legal actions; never receive an env."""
        if not legal_actions:
            raise ValueError("No legal action available")
        return 0 if self.name == "first-legal" else self.rng.randrange(len(legal_actions))


def bot_configs(names, seed):
    if len(names) != 4:
        raise ValueError("Exactly four bot policies required")
    configs = []
    for seat, name in enumerate(names):
        if name not in ("first-legal", "random-legal", "rule-based"):
            raise ValueError("Unknown bot policy")
        configs.append({"seat": seat, "name": name,
                        "version": POLICY_VERSION if name == "rule-based" else "1",
                        "seed": seed ^ (seat + 1),
                        **({"settings": {"ranking": ["shanten", "visible_ukeire", "riichi_tenpai", "riichi_safety", "dora", "tile_id"]}}
                           if name == "rule-based" else {})})
    return configs


def create_bots(configs):
    return [RuleBasedBot(config["name"], config["seed"]) if config["name"] == "rule-based"
            else LegalBot(config["name"], config["seed"]) for config in configs]
