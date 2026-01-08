from __future__ import annotations
from typing import Callable, Dict, Type, Optional
import asyncio
import pygame
from settings import Settings
from systems.sound_manager import SoundManager
import database  # Import module to access db dynamically


class BaseGame:
    name: str = "base"

    def __init__(self, screen: pygame.Surface, cfg: Settings, sounds: SoundManager, user_id: Optional[int] = None):
        self.screen = screen
        self.cfg = cfg
        self.sounds = sounds
        self.active = False
        self.score = 0
        self.lives = 3
        self.user_id = user_id  # User ID for score tracking
        self._score_saved = False  # Prevent double-saving

    def start(self) -> None:
        self.active = True
        self.reset()

    def stop(self) -> None:
        self.active = False

    def reset(self) -> None:
        self.score = 0
        self._score_saved = False

    def handle_event(self, event: pygame.event.Event) -> None:
        ...

    def update(self, dt: float) -> None:
        ...

    def draw(self) -> None:
        ...
    
    def save_score(self) -> bool:
        """Save the current score for this user. Call when game ends."""
        if self._score_saved or not self.user_id:
            return False
        result = save_game_score_for_user(self.user_id, self.name, self.score)
        if result:
            self._score_saved = True
        return result


GAME_REGISTRY: Dict[str, Type[BaseGame]] = {}


def register_game(key: str) -> Callable[[Type[BaseGame]], Type[BaseGame]]:
    def wrapper(cls: Type[BaseGame]) -> Type[BaseGame]:
        GAME_REGISTRY[key] = cls
        cls.name = key
        return cls
    return wrapper


def save_game_score_for_user(user_id: int, game_name: str, score: int) -> bool:
    """
    Save score for a user to the database.
    Updates the high score if the new score is higher.
    Returns True if successful.
    """
    # Access db through module to get the current reference (not the one at import time)
    db = database.db
    if not db or not db.is_connected:
        print("Database not connected - score not saved")
        return False
    
    try:
        # Map game names to database column names
        game_map = {
            "snake": "snake",
            "tetris": "tetris",
            "pac_man": "pacman",
            "space_invaders": "space_invaders",
            "hybrid": "hybrid",
        }
        db_game_name = game_map.get(game_name, game_name)
        
        result = asyncio.run(db.update_game_score(user_id, db_game_name, score))
        if result:
            print(f"🏆 New high score saved! {game_name}: {score}")
        else:
            print(f"Score {score} for {game_name} (not a new high score)")
        return True
    except Exception as e:
        print(f"Failed to save score: {e}")
        return False

# Auto-import game modules to populate the registry on package import.
from . import snake  # noqa: F401
from . import tetris  # noqa: F401
from . import pac_man  # noqa: F401
from . import space_invaders  # noqa: F401
from . import hybrid  # noqa: F401
