from __future__ import annotations
import pygame
from . import BaseGame, register_game
from systems.rules import get_rules
from systems.scoring import ScoreEvent, hybrid_score

@register_game("hybrid")
class HybridGame(BaseGame):
    def __init__(self, screen: pygame.Surface, cfg, sounds, user_id=None):
        super().__init__(screen, cfg, sounds, user_id=user_id)
        self.rules = get_rules("hybrid").data
        self.components = self.rules["components"]
        self.timer = 0.0
        self.actions = ScoreEvent()
        self.game_over: bool = False
        self.go_button_rects: list[tuple[str, pygame.Rect]] = []
        self.hud_font = pygame.font.SysFont("arial", 28)
        self.time_limit = 60.0  # 60 second game
        self.elapsed_time = 0.0

    def reset(self) -> None:
        super().reset()
        self.timer = 0.0
        self.actions = ScoreEvent()
        self.game_over = False
        self.go_button_rects.clear()
        self.elapsed_time = 0.0

    def handle_event(self, event: pygame.event.Event) -> None:
        # Handle Game Over overlay clicks
        if self.game_over:
            if not self.go_button_rects:
                self.build_go_buttons()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for key, rect in self.go_button_rects:
                    if rect.collidepoint(mx, my):
                        if key == "restart":
                            self.reset()
                        elif key == "back":
                            pygame.event.post(pygame.event.Event(pygame.USEREVENT, {"action": "back_to_menu"}))
                        break
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_1:
                self.actions.lines_cleared += 1
            elif event.key == pygame.K_2:
                self.actions.fruits_eaten += 1
            elif event.key == pygame.K_3:
                self.actions.ghosts_eaten += 1
            elif event.key == pygame.K_4:
                self.actions.enemies_destroyed += 1

    def update(self, dt: float) -> None:
        if self.game_over:
            return
        
        self.elapsed_time += dt
        if self.elapsed_time >= self.time_limit:
            self.game_over = True
            self.save_score()
            return
        
        self.timer += dt
        if self.timer >= 1.5:
            self.timer = 0.0
            self.score += hybrid_score(self.actions)
            self.actions = ScoreEvent(level=self.actions.level + 1)

    def build_go_buttons(self) -> None:
        self.go_button_rects.clear()
        labels = [("restart", "Play Again"), ("back", "Back To Menu")]
        spacing = 64
        padding_x, padding_y = 22, 12
        button_width = 260
        total_h = len(labels) * spacing
        start_y = self.cfg.height // 2 - total_h // 2 + 60
        for i, (key, text) in enumerate(labels):
            surf = self.hud_font.render(text, True, (255, 255, 255))
            tw, th = surf.get_size()
            w = max(button_width, tw + padding_x * 2)
            h = th + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            y = start_y + i * spacing
            self.go_button_rects.append((key, pygame.Rect(x, y, w, h)))

    def draw(self) -> None:
        time_left = max(0, self.time_limit - self.elapsed_time)
        info = [
            f"Hybrid Mode - Press 1-4 to score!",
            f"Time Left: {int(time_left)}s",
            f"Score: {self.score}",
            "",
            f"[1] Lines cleared: {self.actions.lines_cleared}",
            f"[2] Fruits eaten: {self.actions.fruits_eaten}",
            f"[3] Ghosts eaten: {self.actions.ghosts_eaten}",
            f"[4] Invaders destroyed: {self.actions.enemies_destroyed}",
        ]
        font = pygame.font.SysFont("consolas", 24)
        for idx, line in enumerate(info):
            color = (255, 200, 100) if idx == 1 else (200, 200, 255)
            text = font.render(line, True, color)
            self.screen.blit(text, (80, 120 + idx * 36))
        
        if self.game_over:
            self.draw_game_over_overlay()

    def draw_game_over_overlay(self) -> None:
        # Dim background
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Time's Up text
        title = self.hud_font.render("TIME'S UP!", True, (255, 200, 100))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 100))
        
        # Score
        score_surf = self.hud_font.render(f"Final Score: {self.score}", True, (255, 255, 255))
        self.screen.blit(score_surf, (self.cfg.width // 2 - score_surf.get_width() // 2, self.cfg.height // 2 - 50))

        # Buttons
        self.build_go_buttons()
        mouse_pos = pygame.mouse.get_pos()
        for key, rect in self.go_button_rects:
            label = "Play Again" if key == "restart" else "Back To Menu"
            hovered = rect.collidepoint(*mouse_pos)
            fill = (70, 80, 120) if hovered else (40, 45, 85)
            border = (255, 255, 255) if hovered else (140, 150, 190)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
            text_surf = self.hud_font.render(label, True, (255, 255, 255))
            tx = rect.x + (rect.width - text_surf.get_width()) // 2
            ty = rect.y + (rect.height - text_surf.get_height()) // 2
            self.screen.blit(text_surf, (tx, ty))
