from __future__ import annotations
from typing import Callable, Dict, Type
import pygame
from settings import Settings
from systems.sound_manager import SoundManager
from database import db as global_db

class BaseGame:
    name: str = "base"

    def __init__(self, screen: pygame.Surface, cfg: Settings, sounds: SoundManager):
        self.screen = screen
        self.cfg = cfg
        self.sounds = sounds
        self.active = False
        self.score = 0
        self.lives = 3

    def start(self) -> None:
        self.active = True
        self.reset()

    def stop(self) -> None:
        self.active = False

    def reset(self) -> None:
        self.score = 0

    def handle_event(self, event: pygame.event.Event) -> None:
        ...

    def update(self, dt: float) -> None:
        ...

    def draw(self) -> None:
        ...

GAME_REGISTRY: Dict[str, Type[BaseGame]] = {}

def register_game(key: str) -> Callable[[Type[BaseGame]], Type[BaseGame]]:
    def wrapper(cls: Type[BaseGame]) -> Type[BaseGame]:
        GAME_REGISTRY[key] = cls
        cls.name = key
        return cls
    return wrapper

def save_game_score(game_name: str, player_name: str, score: int, level: int = 1) -> bool:
    """Helper to save score from any game. Returns True if successful."""
    if global_db and global_db.pool:
        import asyncio
        try:
            asyncio.run(global_db.save_score(player_name, game_name, score, level))
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
