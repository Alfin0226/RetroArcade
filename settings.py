from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv
import pygame

BASE_DIR = Path(__file__).resolve().parent
ASSET_DIR = BASE_DIR / "assets"
IMAGE_DIR = ASSET_DIR / "images"
SOUND_DIR = ASSET_DIR / "sounds"
DATA_DIR = BASE_DIR / "data"

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")

@dataclass
class DatabaseConfig:
    """Database connection configuration for Neon (or any Postgres)."""
    host: str = os.getenv("DB_HOST", "")
    port: int = int(os.getenv("DB_PORT", "5432"))
    database: str = os.getenv("DB_NAME", "")
    user: str = os.getenv("DB_USER", "")
    password: str = os.getenv("DB_PASSWORD", "")
    # For Neon, you can also use a full connection string
    connection_string: str = os.getenv("DATABASE_URL", "")
    
    @property
    def is_configured(self) -> bool:
        """Check if database is configured (either via connection string or individual params)."""
        return bool(self.connection_string or (self.host and self.database and self.user))

@dataclass
class Settings:
    width: int = 960
    height: int = 720
    fullscreen: bool = False
    fps: int = 60
    title: str = "Retro Arcade Game"
    bg_color: tuple[int, int, int] = (16, 16, 32)
    # Allow held keys to auto-repeat KEYDOWN events (ms)
    key_repeat_delay: int = 120  # was 180
    key_repeat_interval: int = 30  # was 40

    # Database configuration
    db: DatabaseConfig = None
    
    def __post_init__(self):
        if self.db is None:
            self.db = DatabaseConfig()

    @property
    def screen_size(self) -> tuple[int, int]:
        return (self.width, self.height)

def ensure_directories() -> None:
    for directory in (ASSET_DIR, IMAGE_DIR, SOUND_DIR, DATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)

def init_pygame_window(cfg: Settings) -> pygame.Surface:
    pygame.display.set_caption(cfg.title)
    flags = pygame.FULLSCREEN if cfg.fullscreen else 0
    size = (0, 0) if cfg.fullscreen else cfg.screen_size
    screen = pygame.display.set_mode(size, flags)
    if cfg.fullscreen:
        cfg.width, cfg.height = screen.get_size()
    # Enable key repeat so holding keys (e.g., W/A/S/D) keeps moving
    pygame.key.set_repeat(cfg.key_repeat_delay, cfg.key_repeat_interval)
    return screen
