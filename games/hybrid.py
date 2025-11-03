from __future__ import annotations
import pygame
from . import BaseGame, register_game
from systems.rules import get_rules
from systems.scoring import ScoreEvent, hybrid_score

@register_game("hybrid")
class HybridGame(BaseGame):
    def __init__(self, screen: pygame.Surface, cfg, sounds):
        super().__init__(screen, cfg, sounds)
        self.rules = get_rules("hybrid").data
        self.components = self.rules["components"]
        self.timer = 0.0
        self.actions = ScoreEvent()

    def reset(self) -> None:
        super().reset()
        self.timer = 0.0
        self.actions = ScoreEvent()

    def handle_event(self, event: pygame.event.Event) -> None:
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
        self.timer += dt
        if self.timer >= 1.5:
            self.timer = 0.0
            self.score += hybrid_score(self.actions)
            self.actions = ScoreEvent(level=self.actions.level + 1)

    def draw(self) -> None:
        info = [
            f"Hybrid components: {', '.join(self.components)}",
            f"Score: {self.score}",
            f"Lines: {self.actions.lines_cleared}",
            f"Fruits: {self.actions.fruits_eaten}",
            f"Ghosts: {self.actions.ghosts_eaten}",
            f"Invaders: {self.actions.enemies_destroyed}",
        ]
        font = pygame.font.SysFont("consolas", 24)
        for idx, line in enumerate(info):
            text = font.render(line, True, (200, 200, 255))
            self.screen.blit(text, (80, 120 + idx * 36))
