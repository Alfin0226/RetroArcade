from __future__ import annotations
import random
import pygame
from . import BaseGame, register_game
from systems.rules import get_rules
from systems.scoring import ScoreEvent, snake_score, ScoreBreakdown, calculate_score_breakdown
from systems.collision import point_in_grid

@register_game("snake")
class SnakeGame(BaseGame):
    def __init__(self, screen: pygame.Surface, cfg, sounds, user_id=None):
        super().__init__(screen, cfg, sounds, user_id=user_id)
        self.rules = get_rules("snake").data
        self.grid_w, self.grid_h = self.rules["grid_size"]
        self.direction = (1, 0)
        self.snake = [(5, 5), (4, 5), (3, 5)]
        self.apple = (10, 8)
        self.timer = 0.0
        self.speed = self.rules.get("fps", self.rules.get("speed", 15))  # Support both keys
        # Background style
        self.cell = 24
        self.offset = pygame.Vector2(80, 80)
        self.bg_light = (176, 221, 120)
        self.bg_dark = (162, 207, 106)
        self.bg_border = (46, 102, 46)
        # Game over UI state (init to avoid AttributeError)
        self.game_over: bool = False
        self.go_button_rects: list[tuple[str, pygame.Rect]] = []
        self.fruits_eaten: int = 0
        # HUD
        self.hud_font = pygame.font.SysFont("arial", 28)
        self.hud_pos = (20, 16)
        self.hud_text_color = (240, 244, 255)

        # Visual style for snake and fruit
        self.head_color = (76, 120, 255)      # snake head color
        self.body_color = self.head_color     # match body color to head
        self.eye_white = (245, 248, 255)
        self.eye_pupil = (30, 70, 160)
        
        # Time tracking and score breakdown
        self.time_played: float = 0.0
        self.score_breakdown: ScoreBreakdown | None = None

    def reset(self) -> None:
        super().reset()
        self.direction = (1, 0)
        self.snake = [(5, 5), (4, 5), (3, 5)]
        self.spawn_apple()
        self.timer = 0.0
        self.game_over = False
        self.go_button_rects.clear()
        self.fruits_eaten = 0
        self.time_played = 0.0
        self.score_breakdown = None

    def spawn_apple(self) -> None:
        free = [(x, y) for x in range(self.grid_w) for y in range(self.grid_h) if (x, y) not in self.snake]
        self.apple = random.choice(free) if free else (0, 0)

    def handle_event(self, event: pygame.event.Event) -> None:
        # While game over, only clicks are processed
        if self.game_over:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for key, rect in self.go_button_rects:
                    if rect.collidepoint(mx, my):
                        if key == "restart":
                            self.reset()
                        elif key == "back":
                            # Tell main to return to menu
                            pygame.event.post(pygame.event.Event(pygame.USEREVENT, {"action": "back_to_menu"}))
                        break
            return

        if event.type != pygame.KEYDOWN:
            return
        
        # Prevent 180° turns into itself
        new_direction = None
        if event.key in (pygame.K_LEFT, pygame.K_a):
            new_direction = (-1, 0)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            new_direction = (1, 0)
        elif event.key in (pygame.K_UP, pygame.K_w):
            new_direction = (0, -1)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            new_direction = (0, 1)
        
        # Only change direction if it's not opposite to current direction
        if new_direction is not None:
            dx, dy = self.direction
            ndx, ndy = new_direction
            # Check if new direction is not 180° opposite
            if not (dx == -ndx and dy == -ndy):
                self.direction = new_direction

    def update(self, dt: float) -> None:
        if self.game_over:
            return
        self.time_played += dt
        self.timer += dt
        if self.timer < 1 / self.speed:
            return
        self.timer = 0.0
        head_x, head_y = self.snake[0]
        dx, dy = self.direction
        new_head = (head_x + dx, head_y + dy)
        # Collision with walls or self → Game Over
        if not point_in_grid(new_head, (self.grid_w, self.grid_h)) or new_head in self.snake:
            self.game_over = True
            self._calculate_final_score()
            self.save_score()  # Save score to database
            return
        self.snake.insert(0, new_head)
        if new_head == self.apple:
            self.fruits_eaten += 1
            self.score += snake_score(ScoreEvent(fruits_eaten=1))
            self.sounds.play("eat")
            self.spawn_apple()
        else:
            self.snake.pop()

    def draw(self) -> None:
        # Background
        self.draw_background()

        # Scoreboard (top-left)
        self.draw_scoreboard()

        # Snake (body + head with eyes)
        self.draw_snake()

        # Apple fruit (cartoon apple)
        ax, ay = self.apple
        self.draw_apple(ax, ay)

        # Game Over overlay
        if self.game_over:
            self.draw_game_over_overlay()

    def draw_background(self) -> None:
        cell = self.cell
        ox, oy = int(self.offset.x), int(self.offset.y)
        w = self.grid_w * cell
        h = self.grid_h * cell

        # Border frame
        border = 8
        border_rect = pygame.Rect(ox - border, oy - border, w + border * 2, h + border * 2)
        pygame.draw.rect(self.screen, self.bg_border, border_rect, border_radius=6)

        # Checkerboard playfield
        play_rect = pygame.Rect(ox, oy, w, h)
        pygame.draw.rect(self.screen, self.bg_light, play_rect)  # base
        for gy in range(self.grid_h):
            for gx in range(self.grid_w):
                if (gx + gy) % 2 == 1:
                    pygame.draw.rect(
                        self.screen,
                        self.bg_dark,
                        pygame.Rect(ox + gx * cell, oy + gy * cell, cell, cell),
                    )

    def build_go_buttons(self) -> None:
        # Ensure container exists
        if not hasattr(self, "go_button_rects") or self.go_button_rects is None:
            self.go_button_rects = []
        else:
            self.go_button_rects.clear()
        labels = [("restart", "Restart"), ("back", "Back To Main Menu")]
        spacing = 64
        padding_x, padding_y = 22, 12
        button_width = 360
        total_h = len(labels) * spacing
        start_y = self.cfg.height // 2 - total_h // 2 + 20
        for i, (key, text) in enumerate(labels):
            surf = pygame.font.SysFont("arial", 28).render(text, True, (255, 255, 255))
            tw, th = surf.get_size()
            w = max(button_width, tw + padding_x * 2)
            h = th + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            y = start_y + i * spacing
            self.go_button_rects.append((key, pygame.Rect(x, y, w, h)))

    def _calculate_final_score(self) -> None:
        # Calculate score breakdown with all bonuses
        # Snake doesn't have levels, so use fruits_eaten as a proxy
        level_proxy = max(1, self.fruits_eaten // 5)
        login_streak, daily_streak = self.get_user_streaks()
        self.score_breakdown = calculate_score_breakdown(
            base_score=self.score,
            difficulty=self.cfg.difficulty,
            levels=level_proxy,
            login_streak=login_streak,
            daily_streak=daily_streak,
            time_played=int(self.time_played)
        )
        # Update score to final score for saving
        self.score = self.score_breakdown.final_score

    def draw_game_over_overlay(self) -> None:
        # Dim background
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        font = pygame.font.SysFont("arial", 36)
        small = pygame.font.SysFont("arial", 28)
        title = font.render("Game Over", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 200))

        # Stats with score breakdown
        stats = [f"Apples Eaten: {self.fruits_eaten}"]
        if self.score_breakdown:
            stats.extend(self.score_breakdown.as_display_lines())
        else:
            stats.append(f"Score: {self.score}")
        
        stat_surfs = [small.render(line, True, (220, 220, 240)) for line in stats]
        # Highlight final score line
        if self.score_breakdown and len(stat_surfs) > 0:
            stat_surfs[-1] = small.render(stats[-1], True, (255, 255, 100))
        
        # Compute data box size
        pad_x, pad_y = 16, 14
        line_spacing = 6
        content_w = max(s.get_width() for s in stat_surfs)
        content_h = sum(s.get_height() for s in stat_surfs) + line_spacing * (len(stat_surfs) - 1)
        box_w = max(320, content_w + pad_x * 2)
        box_h = content_h + pad_y * 2
        box_x = self.cfg.width // 2 - box_w // 2
        box_y = self.cfg.height // 2 - 140
        data_box = pygame.Rect(box_x, box_y, box_w, box_h)
        
        # Draw data box
        pygame.draw.rect(self.screen, (35, 40, 80), data_box, border_radius=10)
        pygame.draw.rect(self.screen, (140, 150, 190), data_box, width=2, border_radius=10)
        
        # Draw stats inside box
        curr_y = data_box.y + pad_y
        for surf in stat_surfs:
            self.screen.blit(surf, (data_box.x + pad_x, curr_y))
            curr_y += surf.get_height() + line_spacing

        # Buttons positioned below the data box
        gap = 28
        # Adjust button position based on box
        self.go_button_rects.clear()
        labels = [("restart", "Restart"), ("back", "Back To Main Menu")]
        spacing = 64
        padding_x, padding_y = 22, 12
        button_width = 360
        start_y = data_box.bottom + gap
        for i, (key, text) in enumerate(labels):
            surf = small.render(text, True, (255, 255, 255))
            tw, th = surf.get_size()
            w = max(button_width, tw + padding_x * 2)
            h = th + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            y = start_y + i * spacing
            self.go_button_rects.append((key, pygame.Rect(x, y, w, h)))
        
        mouse_pos = pygame.mouse.get_pos()
        for key, rect in self.go_button_rects:
            label = "Restart" if key == "restart" else "Back To Main Menu"
            hovered = rect.collidepoint(*mouse_pos)
            fill = (70, 80, 120) if hovered else (40, 45, 85)
            border = (255, 255, 255) if hovered else (140, 150, 190)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
            text_surf = small.render(label, True, (255, 255, 255))
            tx = rect.x + (rect.width - text_surf.get_width()) // 2
            ty = rect.y + (rect.height - text_surf.get_height()) // 2
            self.screen.blit(text_surf, (tx, ty))

    def draw_scoreboard(self) -> None:
        # Small apple icon + count at top-left
        x, y = self.hud_pos
        # Draw apple body
        apple_rect = pygame.Rect(x, y, 26, 26)
        pygame.draw.ellipse(self.screen, (214, 76, 50), apple_rect)
        # Highlight
        pygame.draw.circle(self.screen, (255, 145, 120), (apple_rect.x + 8, apple_rect.y + 8), 4)
        # Leaf
        leaf = pygame.Rect(apple_rect.right - 10, apple_rect.y - 2, 10, 8)
        pygame.draw.ellipse(self.screen, (74, 160, 67), leaf)
        # Stem
        pygame.draw.line(self.screen, (120, 80, 50), (apple_rect.centerx + 3, apple_rect.y + 2), (apple_rect.centerx + 1, apple_rect.y - 4), 2)

        # Value text with light shadow
        value = str(self.fruits_eaten)
        text_surf = self.hud_font.render(value, True, self.hud_text_color)
        shadow = self.hud_font.render(value, True, (0, 0, 0))
        tx = apple_rect.right + 8
        ty = apple_rect.y + (apple_rect.height - text_surf.get_height()) // 2
        self.screen.blit(shadow, (tx + 2, ty + 2))
        self.screen.blit(text_surf, (tx, ty))

    def draw_snake(self) -> None:
        cell = self.cell
        ox, oy = int(self.offset.x), int(self.offset.y)

        if not self.snake:
            return

        # Body segments (skip head at index 0)
        for x, y in self.snake[1:]:
            rect = pygame.Rect(ox + x * cell, oy + y * cell, cell - 1, cell - 1)
            pygame.draw.rect(self.screen, self.body_color, rect, border_radius=6)

        # Head with eyes facing movement direction
        hx, hy = self.snake[0]
        head_rect = pygame.Rect(ox + hx * cell, oy + hy * cell, cell - 1, cell - 1)
        pygame.draw.rect(self.screen, self.head_color, head_rect, border_radius=12)

        dx, dy = self.direction
        er = max(2, int(cell * 0.18))   # eye radius
        pr = max(2, int(cell * 0.09))   # pupil radius

        if dx == 1:  # facing right
            ex = head_rect.right - int(cell * 0.28)
            ey1 = head_rect.y + int(cell * 0.32)
            ey2 = head_rect.y + int(cell * 0.68)
            pygame.draw.circle(self.screen, self.eye_white, (ex, ey1), er)
            pygame.draw.circle(self.screen, self.eye_white, (ex, ey2), er)
            pygame.draw.circle(self.screen, self.eye_pupil, (ex + int(er * 0.3), ey1), pr)
            pygame.draw.circle(self.screen, self.eye_pupil, (ex + int(er * 0.3), ey2), pr)
        elif dx == -1:  # facing left
            ex = head_rect.x + int(cell * 0.28)
            ey1 = head_rect.y + int(cell * 0.32)
            ey2 = head_rect.y + int(cell * 0.68)
            pygame.draw.circle(self.screen, self.eye_white, (ex, ey1), er)
            pygame.draw.circle(self.screen, self.eye_white, (ex, ey2), er)
            pygame.draw.circle(self.screen, self.eye_pupil, (ex - int(er * 0.3), ey1), pr)
            pygame.draw.circle(self.screen, self.eye_pupil, (ex - int(er * 0.3), ey2), pr)
        elif dy == 1:  # facing down
            ey = head_rect.bottom - int(cell * 0.28)
            ex1 = head_rect.x + int(cell * 0.32)
            ex2 = head_rect.x + int(cell * 0.68)
            pygame.draw.circle(self.screen, self.eye_white, (ex1, ey), er)
            pygame.draw.circle(self.screen, self.eye_white, (ex2, ey), er)
            pygame.draw.circle(self.screen, self.eye_pupil, (ex1, ey + int(er * 0.3)), pr)
            pygame.draw.circle(self.screen, self.eye_pupil, (ex2, ey + int(er * 0.3)), pr)
        else:  # dy == -1, facing up
            ey = head_rect.y + int(cell * 0.28)
            ex1 = head_rect.x + int(cell * 0.32)
            ex2 = head_rect.x + int(cell * 0.68)
            pygame.draw.circle(self.screen, self.eye_white, (ex1, ey), er)
            pygame.draw.circle(self.screen, self.eye_white, (ex2, ey), er)
            pygame.draw.circle(self.screen, self.eye_pupil, (ex1, ey - int(er * 0.3)), pr)
            pygame.draw.circle(self.screen, self.eye_pupil, (ex2, ey - int(er * 0.3)), pr)

    def draw_apple(self, gx: int, gy: int) -> None:
        # Draw a cartoon apple within grid cell
        cell = self.cell
        ox, oy = int(self.offset.x), int(self.offset.y)
        px = ox + gx * cell
        py = oy + gy * cell

        # Apple body
        pad = int(cell * 0.12)
        body = pygame.Rect(px + pad, py + pad, cell - pad * 2, cell - pad * 2)
        pygame.draw.ellipse(self.screen, (214, 76, 50), body)

        # Highlight
        pygame.draw.circle(self.screen, (255, 145, 120), (body.x + int(body.width * 0.3), body.y + int(body.height * 0.3)), max(2, int(cell * 0.08)))

        # Leaf
        leaf_w = max(6, int(cell * 0.28))
        leaf_h = max(4, int(cell * 0.20))
        leaf = pygame.Rect(body.right - int(leaf_w * 1.1), body.y - int(leaf_h * 0.3), leaf_w, leaf_h)
        pygame.draw.ellipse(self.screen, (74, 160, 67), leaf)

        # Stem
        pygame.draw.line(self.screen, (120, 80, 50), (body.centerx + int(cell * 0.1), body.y + 2), (body.centerx, body.y - int(cell * 0.18)), max(2, int(cell * 0.07)))
