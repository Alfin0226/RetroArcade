from __future__ import annotations
import pygame
from . import BaseGame, register_game
from systems.rules import get_rules
from systems.collision import rect_vs_many
from systems.scoring import ScoreEvent, invaders_score

@register_game("space_invaders")
class SpaceInvadersGame(BaseGame):
    def __init__(self, screen: pygame.Surface, cfg, sounds):
        super().__init__(screen, cfg, sounds)
        self.rules = get_rules("space_invaders").data
        self.player_rect = pygame.Rect(cfg.width // 2 - 25, cfg.height - 80, 50, 20)
        self.bullets: list[pygame.Rect] = []
        self.enemies: list[pygame.Rect] = []
        self.direction = 1
        self.speed = 30

    def reset(self) -> None:
        super().reset()
        self.bullets.clear()
        self.enemies = [
            pygame.Rect(100 + x * 60, 80 + y * 40, 40, 24)
            for y in range(4) for x in range(8)
        ]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            if len(self.bullets) < self.rules["bullet_limit"]:
                bullet = pygame.Rect(self.player_rect.centerx - 4, self.player_rect.y - 12, 8, 16)
                self.bullets.append(bullet)
                self.sounds.play("shoot")

    def update(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            self.player_rect.x -= 200 * dt
        if keys[pygame.K_RIGHT]:
            self.player_rect.x += 200 * dt
        for bullet in list(self.bullets):
            bullet.y -= int(480 * dt)
            if bullet.bottom < 0:
                self.bullets.remove(bullet)

        movement = self.direction * self.speed * dt
        shift_down = False
        for enemy in self.enemies:
            enemy.x += movement
            if enemy.right >= self.cfg.width - 40 or enemy.left <= 40:
                shift_down = True
        if shift_down:
            self.direction *= -1
            for enemy in self.enemies:
                enemy.y += 20

        for bullet in list(self.bullets):
            hits = [enemy for enemy in self.enemies if bullet.colliderect(enemy)]
            if hits:
                self.score += invaders_score(ScoreEvent(enemies_destroyed=len(hits)))
                self.enemies = [enemy for enemy in self.enemies if enemy not in hits]
                self.bullets.remove(bullet)

        if rect_vs_many(self.player_rect, self.enemies):
            self.lives -= 1
            self.reset()

    def draw(self) -> None:
        pygame.draw.rect(self.screen, (120, 220, 255), self.player_rect)
        for bullet in self.bullets:
            pygame.draw.rect(self.screen, (255, 255, 120), bullet)
        for enemy in self.enemies:
            pygame.draw.rect(self.screen, (255, 80, 80), enemy)
