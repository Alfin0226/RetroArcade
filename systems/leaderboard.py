from __future__ import annotations
import asyncio
from typing import List, Dict
import pygame

class LeaderboardManager:
    """Manages fetching and displaying game leaderboards."""
    
    def __init__(self, db):
        self.db = db
        self.cache: Dict[str, List[dict]] = {}
        self.cache_timeout = 60.0  # 60 seconds
        self.last_fetch: Dict[str, float] = {}
    
    def get_leaderboard(self, game: str, limit: int = 10, force_refresh: bool = False) -> List[dict]:
        """Get leaderboard for a game (uses cache if recent)."""
        import time
        current_time = time.time()
        
        # Check cache
        if not force_refresh and game in self.cache:
            if current_time - self.last_fetch.get(game, 0) < self.cache_timeout:
                return self.cache[game]
        
        # Fetch from database
        try:
            leaderboard = asyncio.run(self.db.get_leaderboard(game, limit))
            self.cache[game] = leaderboard
            self.last_fetch[game] = current_time
            return leaderboard
        except Exception as e:
            print(f"❌ Failed to fetch leaderboard: {e}")
            return self.cache.get(game, [])
    
    def save_score_sync(self, player_name: str, game: str, score: int, level: int = 1) -> bool:
        """Save score synchronously (call from game over screen)."""
        try:
            asyncio.run(self.db.save_score(player_name, game, score, level))
            # Invalidate cache for this game
            if game in self.cache:
                del self.cache[game]
            return True
        except Exception as e:
            print(f"❌ Failed to save score: {e}")
            return False
    
    def draw_leaderboard(self, screen: pygame.Surface, game: str, x: int, y: int, font: pygame.font.Font):
        """Draw leaderboard on screen."""
        leaderboard = self.get_leaderboard(game, limit=10)
        
        # Title
        title = font.render(f"{game.upper()} - TOP 10", True, (255, 255, 255))
        screen.blit(title, (x, y))
        y += 40
        
        # Headers
        header_font = pygame.font.SysFont("arial", 18)
        header = header_font.render("RANK  PLAYER           SCORE    LEVEL", True, (200, 200, 200))
        screen.blit(header, (x, y))
        y += 30
        
        # Scores
        entry_font = pygame.font.SysFont("arial", 20)
        for i, entry in enumerate(leaderboard, 1):
            color = (255, 215, 0) if i == 1 else (192, 192, 192) if i == 2 else (205, 127, 50) if i == 3 else (255, 255, 255)
            
            rank = f"{i:2d}."
            player = entry['player_name'][:15].ljust(15)
            score_val = f"{entry['score']:7d}"
            level_val = f"{entry['level']:3d}"
            
            line = f"{rank}  {player}  {score_val}  {level_val}"
            text = entry_font.render(line, True, color)
            screen.blit(text, (x, y))
            y += 28
        
        if not leaderboard:
            text = entry_font.render("No scores yet!", True, (150, 150, 150))
            screen.blit(text, (x, y))
