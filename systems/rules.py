from dataclasses import dataclass, field
from typing import Dict, Any, Literal

# Type alias for difficulty levels
DifficultyLevel = Literal["easy", "intermediate", "hard"]

@dataclass
class GameRuleSet:
    """Container for game-specific rules and settings."""
    name: str
    difficulty: DifficultyLevel = "intermediate"
    level: int = 1
    data: Dict[str, Any] = field(default_factory=dict)


class RulesManager:
    """
    Manages difficulty scaling and game rules for all games.
    
    Difficulty Levels:
    - easy: Slower, more forgiving, 1.0x score multiplier
    - intermediate: Balanced, 1.5x score multiplier
    - hard: Fast, challenging, 2.0x score multiplier
    """
    
    # Score multipliers by difficulty
    SCORE_MULTIPLIERS: Dict[DifficultyLevel, float] = {
        "easy": 1.0,
        "intermediate": 1.5,
        "hard": 2.0,
    }
    
    # Base rules for each game (at intermediate difficulty, level 1)
    BASE_RULES: Dict[str, Dict[str, Any]] = {
        "tetris": {
            "grid_size": (10, 20),
            "gravity_delay": 0.8,  # seconds between drops
            "fast_drop_multiplier": 20,
            "lock_delay": 0.5,  # seconds before piece locks
            "lines_per_level": 10,
        },
        "snake": {
            "grid_size": (30, 20),
            "fps": 15,  # game speed (frames per second for movement)
            "growth": 1,  # segments added per food
            "initial_length": 3,
        },
        "pac_man": {
            "lives": 3,
            "player_speed": 200,  # pixels per second
            "ghost_speed_ratio": 0.9,  # percentage of player speed
            "frightened_time": 8.0,  # seconds ghosts stay frightened
            "scatter_time": 7.0,  # seconds ghosts scatter
            "chase_time": 20.0,  # seconds ghosts chase
        },
        "space_invaders": {
            "lives": 3,
            "bullet_limit": 3,  # max player bullets on screen
            "enemy_speed": 30,  # base horizontal speed
            "alien_drop_speed": 20,  # pixels dropped when changing direction
            "enemy_shoot_delay": 1.5,  # seconds between enemy shots
            "mystery_ship_delay": 15.0,  # seconds between mystery ships
        },
        "hybrid": {
            "components": ["snake", "pac_man"],
            "mix_factor": 0.5,
        },
    }
    
    # Difficulty modifiers (multiplied/added to base values)
    DIFFICULTY_MODIFIERS: Dict[str, Dict[DifficultyLevel, Dict[str, Any]]] = {
        "tetris": {
            "easy": {"gravity_delay": 1.2, "lock_delay": 0.8},
            "intermediate": {"gravity_delay": 0.8, "lock_delay": 0.5},
            "hard": {"gravity_delay": 0.5, "lock_delay": 0.3},
        },
        "snake": {
            "easy": {"fps": 10},
            "intermediate": {"fps": 15},
            "hard": {"fps": 25},
        },
        "pac_man": {
            "easy": {"ghost_speed_ratio": 0.75, "frightened_time": 10.0},
            "intermediate": {"ghost_speed_ratio": 0.9, "frightened_time": 8.0},
            "hard": {"ghost_speed_ratio": 1.05, "frightened_time": 5.0},
        },
        "space_invaders": {
            "easy": {"bullet_limit": 5, "enemy_speed": 20, "enemy_shoot_delay": 2.0},
            "intermediate": {"bullet_limit": 3, "enemy_speed": 30, "enemy_shoot_delay": 1.5},
            "hard": {"bullet_limit": 2, "enemy_speed": 45, "enemy_shoot_delay": 0.8},
        },
    }
    
    def __init__(self):
        self._current_difficulty: DifficultyLevel = "intermediate"
    
    @property
    def current_difficulty(self) -> DifficultyLevel:
        """Get the current global difficulty setting."""
        return self._current_difficulty
    
    @current_difficulty.setter
    def current_difficulty(self, value: DifficultyLevel) -> None:
        """Set the global difficulty setting."""
        if value in ("easy", "intermediate", "hard"):
            self._current_difficulty = value
    
    def get_score_multiplier(self, difficulty: DifficultyLevel | None = None) -> float:
        """Get the score multiplier for the given or current difficulty."""
        diff = difficulty or self._current_difficulty
        return self.SCORE_MULTIPLIERS.get(diff, 1.0)
    
    def get_rules(
        self,
        game_name: str,
        difficulty: DifficultyLevel | None = None,
        level: int = 1
    ) -> GameRuleSet:
        """
        Get game rules adjusted for difficulty and level.
        
        Args:
            game_name: Name of the game (tetris, snake, pac_man, space_invaders, hybrid)
            difficulty: Difficulty level (uses current if None)
            level: Current game level (affects scaling)
        
        Returns:
            GameRuleSet with computed game settings
        """
        diff = difficulty or self._current_difficulty
        
        # Start with base rules
        base = self.BASE_RULES.get(game_name, {}).copy()
        
        # Apply difficulty modifiers
        if game_name in self.DIFFICULTY_MODIFIERS:
            modifiers = self.DIFFICULTY_MODIFIERS[game_name].get(diff, {})
            base.update(modifiers)
        
        # Apply level scaling
        base = self._apply_level_scaling(game_name, base, level)
        
        # Add score multiplier
        base["score_multiplier"] = self.get_score_multiplier(diff)
        
        return GameRuleSet(
            name=game_name,
            difficulty=diff,
            level=level,
            data=base
        )
    
    def _apply_level_scaling(
        self,
        game_name: str,
        rules: Dict[str, Any],
        level: int
    ) -> Dict[str, Any]:
        """Apply level-based difficulty scaling."""
        if level <= 1:
            return rules
        
        # Level scaling factor (increases difficulty per level)
        level_factor = level - 1
        
        if game_name == "tetris":
            # Gravity gets faster each level (min 0.1 seconds)
            gravity = rules.get("gravity_delay", 0.8)
            rules["gravity_delay"] = max(0.1, gravity - (level_factor * 0.05))
        
        elif game_name == "snake":
            # Speed increases slightly each level
            fps = rules.get("fps", 15)
            rules["fps"] = min(30, fps + level_factor)
        
        elif game_name == "pac_man":
            # Ghosts get faster, frightened time shorter
            ghost_ratio = rules.get("ghost_speed_ratio", 0.9)
            rules["ghost_speed_ratio"] = min(1.2, ghost_ratio + (level_factor * 0.05))
            frightened = rules.get("frightened_time", 8.0)
            rules["frightened_time"] = max(3.0, frightened - (level_factor * 0.5))
        
        elif game_name == "space_invaders":
            # Enemies get faster, shoot more often
            speed = rules.get("enemy_speed", 30)
            rules["enemy_speed"] = min(80, speed + (level_factor * 5))
            shoot_delay = rules.get("enemy_shoot_delay", 1.5)
            rules["enemy_shoot_delay"] = max(0.3, shoot_delay - (level_factor * 0.1))
        
        return rules


# Global rules manager instance
_rules_manager = RulesManager()


def get_rules_manager() -> RulesManager:
    """Get the global RulesManager instance."""
    return _rules_manager


def get_rules(
    game: str,
    difficulty: DifficultyLevel | None = None,
    level: int = 1
) -> GameRuleSet:
    """
    Convenience function to get game rules.
    
    Args:
        game: Name of the game
        difficulty: Difficulty level (uses global setting if None)
        level: Current game level
    
    Returns:
        GameRuleSet with computed game settings
    """
    return _rules_manager.get_rules(game, difficulty, level)


def set_difficulty(difficulty: DifficultyLevel) -> None:
    """Set the global difficulty level."""
    _rules_manager.current_difficulty = difficulty


def get_difficulty() -> DifficultyLevel:
    """Get the current global difficulty level."""
    return _rules_manager.current_difficulty


# Legacy compatibility: DEFAULT_RULES dict for simple access
DEFAULT_RULES = {
    game: _rules_manager.get_rules(game)
    for game in _rules_manager.BASE_RULES
}
