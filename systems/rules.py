from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class GameRuleSet:
    name: str
    data: Dict[str, Any] = field(default_factory=dict)

DEFAULT_RULES = {
    "tetris": GameRuleSet(
        name="tetris",
        data={"grid_size": (10, 20), "gravity_delay": 0.8, "fast_drop_multiplier": 20},
    ),
    "snake": GameRuleSet(
        name="snake",
        data={"grid_size": (30, 20), "speed": 8, "growth": 1},
    ),
    "pacman": GameRuleSet(
        name="pacman",
        data={"lives": 3, "power_duration": 6.0},
    ),
    "space_invaders": GameRuleSet(
        name="space_invaders",
        data={"lives": 3, "bullet_limit": 3},
    ),
    "hybrid": GameRuleSet(
        name="hybrid",
        data={"components": ["snake", "pacman"], "mix_factor": 0.5},
    ),
}

def get_rules(game: str) -> GameRuleSet:
    return DEFAULT_RULES.get(game, GameRuleSet(name=game))
