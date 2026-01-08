from __future__ import annotations
import pygame
from . import BaseGame, register_game
from systems.rules import get_rules
from systems.collision import rect_vs_many
from systems.scoring import ScoreEvent, invaders_score

@register_game("space_invaders")
class SpaceInvadersGame(BaseGame):
    def __init__(self, screen: pygame.Surface, cfg, sounds, user_id=None):
        super().__init__(screen, cfg, sounds, user_id=user_id)
        self.rules = get_rules("space_invaders").data
        self.player_rect = pygame.Rect(cfg.width // 2 - 25, cfg.height - 80, 50, 20)
        self.bullets: list[pygame.Rect] = []
        self.enemies: list[pygame.Rect] = []
        self.direction = 1
        self.speed = 30
        self.game_over: bool = False
        self.go_button_rects: list[tuple[str, pygame.Rect]] = []
        self.hud_font = pygame.font.SysFont("arial", 28)

    def reset(self) -> None:
        super().reset()
        self.bullets.clear()
        self.enemies = [
            pygame.Rect(100 + x * 60, 80 + y * 40, 40, 24)
            for y in range(4) for x in range(8)
        ]
        self.game_over = False
        self.go_button_rects.clear()
        self.lives = 3
        self.speed = 30
        self.player_rect.x = self.cfg.width // 2 - 25

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
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            if len(self.bullets) < self.rules["bullet_limit"]:
                bullet = pygame.Rect(self.player_rect.centerx - 4, self.player_rect.y - 12, 8, 16)
                self.bullets.append(bullet)
                self.sounds.play("shoot")

    def update(self, dt: float) -> None:
        if self.game_over:
            return
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            self.player_rect.x -= 200 * dt
        if keys[pygame.K_RIGHT]:
            self.player_rect.x += 200 * dt
        
        # Keep player in bounds
        self.player_rect.x = max(40, min(self.cfg.width - 90, self.player_rect.x))
        
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

        # Check for player collision with enemies
        if rect_vs_many(self.player_rect, self.enemies):
            self.lives -= 1
            if self.lives <= 0:
                self.game_over = True
                self.save_score()  # Save score to database
            else:
                # Reset position but keep score
                self.player_rect.x = self.cfg.width // 2 - 25
                self.bullets.clear()
        
        # Check if enemies reached bottom
        for enemy in self.enemies:
            if enemy.bottom >= self.cfg.height - 100:
                self.game_over = True
                self.save_score()
                return
        
        # Win condition: all enemies destroyed - spawn next wave
        if not self.enemies:
            self.enemies = [
                pygame.Rect(100 + x * 60, 80 + y * 40, 40, 24)
                for y in range(4) for x in range(8)
            ]
            self.speed += 10

    def build_go_buttons(self) -> None:
        self.go_button_rects.clear()
        labels = [("restart", "Restart"), ("back", "Back To Menu")]
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
        # Draw HUD
        score_text = self.hud_font.render(f"Score: {self.score}", True, (255, 255, 255))
        lives_text = self.hud_font.render(f"Lives: {self.lives}", True, (255, 255, 255))
        self.screen.blit(score_text, (20, 16))
        self.screen.blit(lives_text, (self.cfg.width - 120, 16))
        
        pygame.draw.rect(self.screen, (120, 220, 255), self.player_rect)
        for bullet in self.bullets:
            pygame.draw.rect(self.screen, (255, 255, 120), bullet)
        for enemy in self.enemies:
            pygame.draw.rect(self.screen, (255, 80, 80), enemy)
        
        if self.game_over:
            self.draw_game_over_overlay()

    def draw_game_over_overlay(self) -> None:
        # Dim background
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Game Over text
        title = self.hud_font.render("GAME OVER", True, (255, 80, 80))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 100))
        
        # Score
        score_surf = self.hud_font.render(f"Final Score: {self.score}", True, (255, 255, 255))
        self.screen.blit(score_surf, (self.cfg.width // 2 - score_surf.get_width() // 2, self.cfg.height // 2 - 50))

        # Buttons
        self.build_go_buttons()
        mouse_pos = pygame.mouse.get_pos()
        for key, rect in self.go_button_rects:
            label = "Restart" if key == "restart" else "Back To Menu"
            hovered = rect.collidepoint(*mouse_pos)
            fill = (70, 80, 120) if hovered else (40, 45, 85)
            border = (255, 255, 255) if hovered else (140, 150, 190)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
            text_surf = self.hud_font.render(label, True, (255, 255, 255))
            tx = rect.x + (rect.width - text_surf.get_width()) // 2
            ty = rect.y + (rect.height - text_surf.get_height()) // 2
            self.screen.blit(text_surf, (tx, ty))
