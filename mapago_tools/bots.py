"""Small legal-action policies for engine integration, not measured AI strength."""

import random

from mapago_tools.strategy import POLICY_VERSION, RuleBasedBot
from mapago_tools.mjsoul_model import (MODEL_PATH, TENHOU_MODEL_PATH,
                                       POLICY_VERSION as MJSOUL_POLICY_VERSION,
                                       TENHOU_POLICY_VERSION, MIXED_POLICY_VERSION,
                                       ImitationBot, MixedImitationBot)


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
        if name not in ("first-legal", "random-legal", "rule-based", "mjsoul-imitation", "tenhou-imitation", "mixed-imitation"):
            raise ValueError("Unknown bot policy")
        version = (POLICY_VERSION if name == "rule-based" else
                   MJSOUL_POLICY_VERSION if name == "mjsoul-imitation" else
                   TENHOU_POLICY_VERSION if name == "tenhou-imitation" else
                   MIXED_POLICY_VERSION if name == "mixed-imitation" else "1")
        configs.append({"seat": seat, "name": name,
                        "version": version,
                        "seed": seed ^ (seat + 1),
                        **({"settings": {"ranking": ["shanten", "visible_ukeire", "riichi_tenpai", "riichi_safety", "dora", "tile_id"]}}
                           if name == "rule-based" else {}),
                        **({"settings": {"model_path": str(MODEL_PATH)}}
                           if name == "mjsoul-imitation" else
                           {"settings": {"model_path": str(TENHOU_MODEL_PATH)}} if name == "tenhou-imitation" else
                           {"settings": {"tenhou_model_path": str(TENHOU_MODEL_PATH),
                                         "mjsoul_model_path": str(MODEL_PATH), "tenhou_weight": 0.8}}
                           if name == "mixed-imitation" else {})})
    return configs


def create_bots(configs):
    bots = []
    for config in configs:
        if config["name"] == "rule-based":
            bot = RuleBasedBot(config["name"], config["seed"])
        elif config["name"] == "mixed-imitation":
            settings = config["settings"]
            bot = MixedImitationBot(settings["tenhou_model_path"], settings["mjsoul_model_path"],
                                    settings["tenhou_weight"])
        elif config["name"] in ("mjsoul-imitation", "tenhou-imitation"):
            bot = ImitationBot(config["settings"]["model_path"])
        else:
            bot = LegalBot(config["name"], config["seed"])
        bots.append(bot)
    return bots
