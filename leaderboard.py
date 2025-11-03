from __future__ import annotations
import sqlite3
from typing import List, Tuple
import pygame
from settings import DATA_DIR, Settings
from systems.scoring import format_score

DB_PATH = DATA_DIR / "users.db"

def save_score(username: str, game: str, score: int) -> None:
    if not username:
        return
    from user import save_progress
    save_progress(username, game, score)

def fetch_top_scores(game: str, limit: int = 10) -> List[Tuple[str, int]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT username, score FROM progress WHERE game = ? ORDER BY score DESC LIMIT ?",
            (game, limit),
        ).fetchall()
    return rows

class LeaderboardView:
    def __init__(self, screen: pygame.Surface, cfg: Settings, font: pygame.font.Font):
        self.screen = screen
        self.cfg = cfg
        self.font = font
        self.active_game = "snake"

    def draw(self) -> None:
        self.screen.fill((12, 12, 28))
        title = self.font.render(f"Leaderboard - {self.active_game.title()}", True, (255, 255, 255))
        self.screen.blit(title, (40, 40))
        for idx, (username, score) in enumerate(fetch_top_scores(self.active_game), start=1):
            line = self.font.render(f"{idx:02d}. {username} - {format_score(score)}", True, (200, 200, 220))
            self.screen.blit(line, (40, 80 + idx * 32))
