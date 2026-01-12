from __future__ import annotations
from typing import List, Dict, Optional
import pygame
from settings import Settings
import database
from async_helper import run_async


GAME_TABS = ["total", "snake", "tetris", "pacman", "space_invaders", "hybrid"]
TAB_DISPLAY_NAMES = {
    "total": "Overall",
    "snake": "Snake",
    "tetris": "Tetris",
    "pacman": "Pac-Man",
    "space_invaders": "Space Invaders",
    "hybrid": "Hybrid",
}


def fetch_leaderboard(game: str, limit: int = 10) -> List[Dict]:
    """Fetch leaderboard from database."""
    db = database.db
    if not db or not db.is_connected:
        return []
    
    try:
        if game == "total":
            return run_async(db.get_global_leaderboard(limit))
        else:
            return run_async(db.get_game_leaderboard(game, limit))
    except Exception as e:
        print(f"Error fetching leaderboard: {e}")
        return []


class LeaderboardView:
    def __init__(self, screen: pygame.Surface, cfg: Settings, font: pygame.font.Font):
        self.screen = screen
        self.cfg = cfg
        self.font = font
        self.title_font = pygame.font.SysFont("arial", 36, bold=True)
        self.tab_font = pygame.font.SysFont("arial", 22)
        self.active_tab = "total"
        self.tab_rects: List[tuple[str, pygame.Rect]] = []
        self.back_rect: Optional[pygame.Rect] = None
        self.scores: List[Dict] = []
        self.last_fetch_tab = ""
        
    def refresh_scores(self) -> None:
        """Refresh scores from database."""
        if self.active_tab != self.last_fetch_tab:
            self.scores = fetch_leaderboard(self.active_tab, limit=10)
            self.last_fetch_tab = self.active_tab
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle events. Returns 'back' if back button clicked."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            # Check tab clicks
            for tab_key, rect in self.tab_rects:
                if rect.collidepoint(mx, my):
                    self.active_tab = tab_key
                    self.last_fetch_tab = ""  # Force refresh
                    return None
            # Check back button
            if self.back_rect and self.back_rect.collidepoint(mx, my):
                return "back"
        return None

    def draw(self) -> None:
        self.screen.fill((12, 12, 28))
        self.refresh_scores()
        
        # Title
        title = self.title_font.render("🏆 Leaderboard", True, (255, 215, 0))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, 30))
        
        # Draw tabs
        self._draw_tabs()
        
        # Draw scores table
        self._draw_scores()
        
        # Draw back button
        self._draw_back_button()
    
    def _draw_tabs(self) -> None:
        """Draw game selection tabs."""
        self.tab_rects.clear()
        tab_y = 90
        tab_height = 36
        tab_spacing = 8
        total_width = 0
        tab_widths = []
        
        # Calculate tab widths
        for tab in GAME_TABS:
            name = TAB_DISPLAY_NAMES[tab]
            surf = self.tab_font.render(name, True, (255, 255, 255))
            w = surf.get_width() + 24
            tab_widths.append(w)
            total_width += w + tab_spacing
        total_width -= tab_spacing
        
        # Draw tabs centered
        start_x = self.cfg.width // 2 - total_width // 2
        x = start_x
        mouse_pos = pygame.mouse.get_pos()
        
        for i, tab in enumerate(GAME_TABS):
            name = TAB_DISPLAY_NAMES[tab]
            w = tab_widths[i]
            rect = pygame.Rect(x, tab_y, w, tab_height)
            self.tab_rects.append((tab, rect))
            
            is_active = tab == self.active_tab
            is_hovered = rect.collidepoint(*mouse_pos)
            
            if is_active:
                fill = (80, 100, 180)
                border = (255, 215, 0)
            elif is_hovered:
                fill = (50, 60, 100)
                border = (150, 160, 200)
            else:
                fill = (30, 35, 60)
                border = (80, 90, 120)
            
            pygame.draw.rect(self.screen, fill, rect, border_radius=6)
            pygame.draw.rect(self.screen, border, rect, width=2, border_radius=6)
            
            text_surf = self.tab_font.render(name, True, (255, 255, 255))
            tx = rect.x + (rect.width - text_surf.get_width()) // 2
            ty = rect.y + (rect.height - text_surf.get_height()) // 2
            self.screen.blit(text_surf, (tx, ty))
            
            x += w + tab_spacing
    
    def _draw_scores(self) -> None:
        """Draw the scores table."""
        table_y = 150
        row_height = 44
        table_width = 500
        table_x = self.cfg.width // 2 - table_width // 2
        
        # Table header
        header_rect = pygame.Rect(table_x, table_y, table_width, row_height)
        pygame.draw.rect(self.screen, (40, 50, 80), header_rect, border_radius=6)
        
        rank_text = self.font.render("Rank", True, (200, 200, 220))
        name_text = self.font.render("Player", True, (200, 200, 220))
        score_text = self.font.render("Score", True, (200, 200, 220))
        
        self.screen.blit(rank_text, (table_x + 20, table_y + 10))
        self.screen.blit(name_text, (table_x + 100, table_y + 10))
        self.screen.blit(score_text, (table_x + table_width - 120, table_y + 10))
        
        # Score rows
        if not self.scores:
            no_data = self.font.render("No scores yet!", True, (150, 150, 170))
            self.screen.blit(no_data, (self.cfg.width // 2 - no_data.get_width() // 2, table_y + row_height + 40))
            return
        
        for idx, entry in enumerate(self.scores):
            row_y = table_y + row_height + idx * row_height
            row_rect = pygame.Rect(table_x, row_y, table_width, row_height - 4)
            
            # Alternate row colors
            if idx % 2 == 0:
                fill = (25, 30, 50)
            else:
                fill = (30, 35, 55)
            
            # Highlight top 3
            if idx == 0:
                fill = (60, 50, 20)  # Gold tint
            elif idx == 1:
                fill = (40, 45, 55)  # Silver tint
            elif idx == 2:
                fill = (45, 35, 30)  # Bronze tint
            
            pygame.draw.rect(self.screen, fill, row_rect, border_radius=4)
            
            # Rank with medal for top 3
            rank = idx + 1
            if rank == 1:
                rank_str = "🥇"
            elif rank == 2:
                rank_str = "🥈"
            elif rank == 3:
                rank_str = "🥉"
            else:
                rank_str = f"{rank}."
            
            rank_surf = self.font.render(rank_str, True, (255, 255, 255))
            self.screen.blit(rank_surf, (table_x + 20, row_y + 8))
            
            # Player name
            username = entry.get("username", "Unknown")
            name_surf = self.font.render(username[:15], True, (255, 255, 255))
            self.screen.blit(name_surf, (table_x + 100, row_y + 8))
            
            # Score
            if self.active_tab == "total":
                score = entry.get("total_score", 0)
            else:
                score = entry.get("score", 0)
            score_surf = self.font.render(f"{score:,}", True, (100, 255, 150))
            self.screen.blit(score_surf, (table_x + table_width - 120, row_y + 8))
    
    def _draw_back_button(self) -> None:
        """Draw back to menu button."""
        btn_width = 160
        btn_height = 44
        btn_x = self.cfg.width // 2 - btn_width // 2
        btn_y = self.cfg.height - 70
        
        self.back_rect = pygame.Rect(btn_x, btn_y, btn_width, btn_height)
        mouse_pos = pygame.mouse.get_pos()
        hovered = self.back_rect.collidepoint(*mouse_pos)
        
        fill = (70, 80, 120) if hovered else (40, 45, 85)
        border = (255, 255, 255) if hovered else (140, 150, 190)
        
        pygame.draw.rect(self.screen, fill, self.back_rect, border_radius=8)
        pygame.draw.rect(self.screen, border, self.back_rect, width=2, border_radius=8)
        
        text = self.font.render("Back", True, (255, 255, 255))
        tx = self.back_rect.x + (self.back_rect.width - text.get_width()) // 2
        ty = self.back_rect.y + (self.back_rect.height - text.get_height()) // 2
        self.screen.blit(text, (tx, ty))
