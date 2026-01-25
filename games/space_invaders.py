from __future__ import annotations
import pygame
import random
from . import BaseGame, register_game
from systems.rules import get_rules
from systems.collision import rect_vs_many
from systems.scoring import ScoreEvent, invaders_score, ScoreBreakdown, calculate_score_breakdown

# Colors
SI_TEXT_COLOR = (255, 255, 255)
SI_PLAYER_COLOR = (120, 220, 255)
SI_PLAYER_BULLET_COLOR = (255, 255, 120)
SI_ENEMY_BULLET_COLOR = (255, 100, 100)
SI_ENEMY_COLOR = (255, 80, 80)
SI_BUNKER_COLOR = (50, 200, 50)
SI_MYSTERY_COLOR = (255, 0, 255)
SI_MYSTERY_DETAIL_COLOR = (255, 150, 255)

# Enemy type colors (7 types)
ENEMY_COLORS = [
    (255, 80, 80),    # Type 0 - Red
    (80, 255, 80),    # Type 1 - Green
    (80, 80, 255),    # Type 2 - Blue
    (255, 255, 80),   # Type 3 - Yellow
    (255, 80, 255),   # Type 4 - Magenta
    (80, 255, 255),   # Type 5 - Cyan
    (255, 165, 80),   # Type 6 - Orange
]

# Pixel art patterns for 7 enemy types (each is a list of rows, 1 = filled, 0 = empty)
# Scale: 4 pixels per cell, patterns are roughly 11x8 cells
ENEMY_PATTERNS = [
    # Type 0 - Classic squid (top row enemy)
    [
        [0,0,0,1,1,0,0,0],
        [0,0,1,1,1,1,0,0],
        [0,1,1,1,1,1,1,0],
        [1,1,0,1,1,0,1,1],
        [1,1,1,1,1,1,1,1],
        [0,0,1,0,0,1,0,0],
        [0,1,0,1,1,0,1,0],
        [1,0,1,0,0,1,0,1],
    ],
    # Type 1 - Crab style
    [
        [0,0,1,0,0,0,1,0,0],
        [0,0,0,1,0,1,0,0,0],
        [0,0,1,1,1,1,1,0,0],
        [0,1,1,0,1,0,1,1,0],
        [1,1,1,1,1,1,1,1,1],
        [1,0,1,1,1,1,1,0,1],
        [1,0,1,0,0,0,1,0,1],
        [0,0,0,1,1,1,0,0,0],
    ],
    # Type 2 - Octopus style
    [
        [0,0,0,0,1,1,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,0],
        [1,1,1,1,1,1,1,1,1,1],
        [1,1,1,0,0,0,0,1,1,1],
        [1,1,1,1,1,1,1,1,1,1],
        [0,0,0,1,1,1,1,0,0,0],
        [0,0,1,1,0,0,1,1,0,0],
        [1,1,0,0,0,0,0,0,1,1],
    ],
    # Type 3 - Skull style
    [
        [0,0,1,1,1,1,1,1,0,0],
        [0,1,1,1,1,1,1,1,1,0],
        [1,1,1,1,1,1,1,1,1,1],
        [1,1,1,0,0,0,0,1,1,1],
        [1,1,1,1,1,1,1,1,1,1],
        [0,0,1,1,0,0,1,1,0,0],
        [0,1,1,0,1,1,0,1,1,0],
        [1,1,0,0,0,0,0,0,1,1],
    ],
    # Type 4 - Bug style
    [
        [0,0,0,1,1,1,1,0,0,0],
        [0,1,1,1,1,1,1,1,1,0],
        [1,1,0,1,1,1,1,0,1,1],
        [1,1,1,1,1,1,1,1,1,1],
        [0,1,1,1,0,0,1,1,1,0],
        [0,0,1,0,0,0,0,1,0,0],
        [0,1,0,0,0,0,0,0,1,0],
        [0,0,1,0,0,0,0,1,0,0],
    ],
    # Type 5 - Robot style
    [
        [0,1,1,1,1,1,1,1,1,0],
        [1,1,1,1,1,1,1,1,1,1],
        [1,1,0,1,1,1,1,0,1,1],
        [1,1,1,1,1,1,1,1,1,1],
        [0,1,1,0,1,1,0,1,1,0],
        [0,0,1,1,1,1,1,1,0,0],
        [0,0,1,0,0,0,0,1,0,0],
        [0,1,1,0,0,0,0,1,1,0],
    ],
    # Type 6 - Diamond style
    [
        [0,0,0,0,1,1,0,0,0,0],
        [0,0,0,1,1,1,1,0,0,0],
        [0,0,1,1,1,1,1,1,0,0],
        [0,1,1,0,1,1,0,1,1,0],
        [1,1,1,1,1,1,1,1,1,1],
        [0,1,0,1,1,1,1,0,1,0],
        [0,0,1,0,0,0,0,1,0,0],
        [0,1,0,0,0,0,0,0,1,0],
    ],
]

@register_game("space_invaders")
class SpaceInvadersGame(BaseGame):
    def __init__(self, screen: pygame.Surface, cfg, sounds, user_id=None):
        super().__init__(screen, cfg, sounds, user_id=user_id)
        self.rules = get_rules("space_invaders").data
        self.player_rect = pygame.Rect(cfg.width // 2 - 25, cfg.height - 80, 50, 20)
        self.bullets: list[pygame.Rect] = []
        self.enemies: list[tuple[pygame.Rect, int]] = []  # (rect, enemy_type)
        self.enemy_bullets: list[pygame.Rect] = []  # Enemy projectiles
        self.bunkers: list[list[pygame.Rect]] = []  # Defense bunkers (list of block lists)
        self.direction = 1
        self.speed = 30
        self.enemy_shoot_timer = 0.0
        self.enemy_shoot_delay = 1.5  # Seconds between enemy shots
        
        # Mystery ship properties
        self.mystery_ship: pygame.Rect | None = None
        self.mystery_ship_timer = 0.0
        self.mystery_ship_delay = 15.0  # Seconds between mystery ship spawns
        self.mystery_ship_speed = 150
        self.mystery_ship_direction = 1
        
        # Font for scoreboard
        self.font = pygame.font.Font(None, 36)
        self.title_font = pygame.font.SysFont("arial", 32)
        self.hud_font = pygame.font.SysFont("arial", 28)
        
        # Game over state
        self.game_over = False
        self.go_button_rects: list[tuple[str, pygame.Rect]] = []
        
        # Time tracking and score breakdown
        self.time_played: float = 0.0
        self.wave: int = 1
        self.score_breakdown: ScoreBreakdown | None = None

    def _create_bunkers(self) -> list[list[pygame.Rect]]:
        """Create 4 defense bunkers made of destructible blocks."""
        bunkers = []
        bunker_width = 60
        bunker_height = 40
        block_size = 10
        spacing = (self.cfg.width - 4 * bunker_width) // 5
        
        for i in range(4):
            bunker_x = spacing + i * (bunker_width + spacing)
            bunker_y = self.cfg.height - 150
            blocks = []
            
            # Create bunker shape (arch-like)
            for row in range(bunker_height // block_size):
                for col in range(bunker_width // block_size):
                    # Skip bottom center blocks to create arch opening
                    if row >= 2 and 2 <= col <= 3:
                        continue
                    block = pygame.Rect(
                        bunker_x + col * block_size,
                        bunker_y + row * block_size,
                        block_size - 1,
                        block_size - 1
                    )
                    blocks.append(block)
            bunkers.append(blocks)
        return bunkers

    def reset(self) -> None:
        super().reset()
        self.lives = 3  # Reset lives on full reset
        self.bullets.clear()
        self.enemy_bullets.clear()
        self._spawn_new_wave()
        self.bunkers = self._create_bunkers()
        self.mystery_ship = None
        self.mystery_ship_timer = 0.0
        self.enemy_shoot_timer = 0.0
        self.direction = 1
        self.speed = 30
        self.game_over = False
        self.go_button_rects.clear()
        self.time_played = 0.0
        self.wave = 1
        self.score_breakdown = None

    def _spawn_new_wave(self) -> None:
        """Spawn a new wave of enemies with 7 rows (one for each type)."""
        self.enemies = []
        num_rows = 7
        num_cols = 8
        for y in range(num_rows):
            enemy_type = y % 7  # Each row gets a different type
            for x in range(num_cols):
                rect = pygame.Rect(100 + x * 55, 60 + y * 36, 40, 28)
                self.enemies.append((rect, enemy_type))
        self.direction = 1

    def _next_wave(self) -> None:
        """Start the next wave - keeps score and lives, spawns new enemies."""
        self.wave += 1
        self.bullets.clear()
        self.enemy_bullets.clear()
        self._spawn_new_wave()
        # Slightly increase difficulty
        self.speed = min(self.speed + 5, 80)
        self.enemy_shoot_delay = max(self.enemy_shoot_delay - 0.1, 0.5)

    def handle_event(self, event: pygame.event.Event) -> None:
        # Handle game over screen
        if self.game_over:
            if not self.go_button_rects:
                self._build_go_buttons()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for key, rect in self.go_button_rects:
                    if rect.collidepoint(mx, my):
                        if key == "restart":
                            self.reset()
                        else:
                            pygame.event.post(pygame.event.Event(pygame.USEREVENT, {"action": "back_to_menu"}))
                        break
            return
        
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            if len(self.bullets) < self.rules["bullet_limit"]:
                bullet = pygame.Rect(self.player_rect.centerx - 4, self.player_rect.y - 12, 8, 16)
                self.bullets.append(bullet)
                self.sounds.play("shoot")

    def _spawn_mystery_ship(self) -> None:
        """Spawn a mystery ship from either side of the screen."""
        if random.random() < 0.5:
            # Spawn from left
            self.mystery_ship = pygame.Rect(-60, 30, 50, 20)
            self.mystery_ship_direction = 1
        else:
            # Spawn from right
            self.mystery_ship = pygame.Rect(self.cfg.width + 10, 30, 50, 20)
            self.mystery_ship_direction = -1

    def _enemy_shoot(self) -> None:
        """Make a random enemy (preferably bottom row) shoot at the player."""
        if not self.enemies:
            return
        
        # Group enemies by column and pick the bottom-most in each column
        columns: dict[int, pygame.Rect] = {}
        for enemy_rect, _ in self.enemies:
            col_key = enemy_rect.centerx // 55
            if col_key not in columns or enemy_rect.y > columns[col_key].y:
                columns[col_key] = enemy_rect
        
        # Pick a random bottom enemy to shoot
        shooter = random.choice(list(columns.values()))
        bullet = pygame.Rect(shooter.centerx - 3, shooter.bottom, 6, 12)
        self.enemy_bullets.append(bullet)

    def update(self, dt: float) -> None:
        if self.game_over:
            return
        
        self.time_played += dt
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.player_rect.x -= 200 * dt
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.player_rect.x += 200 * dt
        
        # Keep player in bounds
        self.player_rect.x = max(0, min(self.cfg.width - self.player_rect.width, self.player_rect.x))
        
        # Update player bullets
        for bullet in list(self.bullets):
            bullet.y -= int(480 * dt)
            if bullet.bottom < 0:
                self.bullets.remove(bullet)

        # Update enemy bullets
        for bullet in list(self.enemy_bullets):
            bullet.y += int(300 * dt)
            if bullet.top > self.cfg.height:
                self.enemy_bullets.remove(bullet)

        # Enemy shooting timer
        self.enemy_shoot_timer += dt
        if self.enemy_shoot_timer >= self.enemy_shoot_delay:
            self.enemy_shoot_timer = 0.0
            self._enemy_shoot()

        # Mystery ship spawn timer
        if self.mystery_ship is None:
            self.mystery_ship_timer += dt
            if self.mystery_ship_timer >= self.mystery_ship_delay:
                self.mystery_ship_timer = 0.0
                self._spawn_mystery_ship()
        else:
            # Update mystery ship position
            self.mystery_ship.x += self.mystery_ship_direction * self.mystery_ship_speed * dt
            # Remove if off screen
            if self.mystery_ship.right < 0 or self.mystery_ship.left > self.cfg.width:
                self.mystery_ship = None

        # Enemy movement
        movement = self.direction * self.speed * dt
        shift_down = False
        
        # Check if any enemy would go out of bounds
        for enemy_rect, _ in self.enemies:
            next_x = enemy_rect.x + movement
            if (self.direction > 0 and next_x + enemy_rect.width >= self.cfg.width - 40) or \
               (self.direction < 0 and next_x <= 40):
                shift_down = True
                break
        
        if shift_down:
            # Reverse direction and move down
            self.direction *= -1
            for enemy_rect, _ in self.enemies:
                enemy_rect.y += 20
        else:
            # Normal horizontal movement
            for enemy_rect, _ in self.enemies:
                enemy_rect.x += movement

        # Player bullet collisions with enemies
        for bullet in list(self.bullets):
            hits = [(enemy_rect, enemy_type) for enemy_rect, enemy_type in self.enemies if bullet.colliderect(enemy_rect)]
            if hits:
                self.score += invaders_score(ScoreEvent(enemies_destroyed=len(hits)))
                self.enemies = [(r, t) for r, t in self.enemies if (r, t) not in hits]
                if bullet in self.bullets:
                    self.bullets.remove(bullet)
                continue
            
            # Check mystery ship hit
            if self.mystery_ship and bullet.colliderect(self.mystery_ship):
                self.score += random.choice([100, 150, 200, 300])  # Random bonus points
                self.mystery_ship = None
                if bullet in self.bullets:
                    self.bullets.remove(bullet)
                self.sounds.play("power_up")  # Use existing sound
                continue
            
            # Check bunker hit by player bullet
            for bunker in self.bunkers:
                for block in list(bunker):
                    if bullet.colliderect(block):
                        bunker.remove(block)
                        if bullet in self.bullets:
                            self.bullets.remove(bullet)
                        break

        # Enemy bullet collisions with player
        for bullet in list(self.enemy_bullets):
            if bullet.colliderect(self.player_rect):
                self.lives -= 1
                self.enemy_bullets.clear()
                if self.lives <= 0:
                    self.game_over = True
                    self._calculate_final_score()
                    self.save_score()  # Save score to database
                    self.go_button_rects.clear()
                    return
                else:
                    self.player_rect.x = self.cfg.width // 2 - 25
                break
            
            # Check bunker hit by enemy bullet
            for bunker in self.bunkers:
                for block in list(bunker):
                    if bullet.colliderect(block):
                        bunker.remove(block)
                        if bullet in self.enemy_bullets:
                            self.enemy_bullets.remove(bullet)
                        break

        # Enemy collision with bunkers (destroy bunker blocks)
        for enemy_rect, _ in self.enemies:
            for bunker in self.bunkers:
                for block in list(bunker):
                    if enemy_rect.colliderect(block):
                        bunker.remove(block)

        # Check if all enemies are defeated - spawn new wave
        if not self.enemies:
            self._next_wave()
            return

        # Enemy reaches player level
        enemy_rects = [r for r, _ in self.enemies]
        if rect_vs_many(self.player_rect, enemy_rects):
            self.lives -= 1
            if self.lives <= 0:
                self.game_over = True
                self._calculate_final_score()
                self.save_score()  # Save score to database
                self.go_button_rects.clear()
                return
            self._respawn_player()
        
        # Check if enemies reached bottom
        for enemy_rect, _ in self.enemies:
            if enemy_rect.bottom >= self.cfg.height - 100:
                self.game_over = True
                self._calculate_final_score()
                self.save_score()  # Save score to database
                return
    
    def _respawn_player(self) -> None:
        """Respawn player after losing a life (without full reset)."""
        self.player_rect.x = self.cfg.width // 2 - 25
        self.enemy_bullets.clear()

    def draw(self) -> None:
        # Draw scoreboard
        score_text = self.font.render(f"SCORE: {self.score}", True, SI_TEXT_COLOR)
        lives_text = self.font.render(f"LIVES: {self.lives}", True, SI_TEXT_COLOR)
        wave_text = self.font.render(f"WAVE: {self.wave}", True, SI_TEXT_COLOR)
        self.screen.blit(score_text, (10, 10))
        self.screen.blit(wave_text, (self.cfg.width // 2 - wave_text.get_width() // 2, 10))
        self.screen.blit(lives_text, (self.cfg.width - 120, 10))
        
        # Draw player
        pygame.draw.rect(self.screen, SI_PLAYER_COLOR, self.player_rect)
        
        # Draw player bullets
        for bullet in self.bullets:
            pygame.draw.rect(self.screen, SI_PLAYER_BULLET_COLOR, bullet)
        
        # Draw enemy bullets
        for bullet in self.enemy_bullets:
            pygame.draw.rect(self.screen, SI_ENEMY_BULLET_COLOR, bullet)
        
        # Draw enemies with pixel art
        for enemy_rect, enemy_type in self.enemies:
            self._draw_enemy(enemy_rect, enemy_type)
        
        # Draw bunkers
        for bunker in self.bunkers:
            for block in bunker:
                pygame.draw.rect(self.screen, SI_BUNKER_COLOR, block)
        
        # Draw mystery ship
        if self.mystery_ship:
            pygame.draw.rect(self.screen, SI_MYSTERY_COLOR, self.mystery_ship)
            # Add a little detail to make it look special
            pygame.draw.rect(self.screen, SI_MYSTERY_DETAIL_COLOR, 
                           pygame.Rect(self.mystery_ship.x + 15, self.mystery_ship.y - 5, 20, 8))
        
        # Draw game over screen
        if self.game_over:
            self._draw_game_over()

    def _draw_enemy(self, rect: pygame.Rect, enemy_type: int) -> None:
        """Draw an enemy as a simple red block (temporary restore)."""
        # Temporary: Draw all enemies as red blocks
        pygame.draw.rect(self.screen, SI_ENEMY_COLOR, rect)
        
        # Original pixel art code (commented out):
        # pattern = ENEMY_PATTERNS[enemy_type]
        # color = ENEMY_COLORS[enemy_type]
        # 
        # # Calculate pixel size based on rect and pattern dimensions
        # pattern_height = len(pattern)
        # pattern_width = len(pattern[0]) if pattern else 0
        # 
        # if pattern_width == 0 or pattern_height == 0:
        #     return
        # 
        # pixel_w = rect.width / pattern_width
        # pixel_h = rect.height / pattern_height
        # 
        # for row_idx, row in enumerate(pattern):
        #     for col_idx, pixel in enumerate(row):
        #         if pixel:
        #             px = rect.x + col_idx * pixel_w
        #             py = rect.y + row_idx * pixel_h
        #             pygame.draw.rect(self.screen, color, 
        #                            pygame.Rect(int(px), int(py), int(pixel_w) + 1, int(pixel_h) + 1))

    def _build_go_buttons(self) -> None:
        self.go_button_rects.clear()
        labels = [("restart", "Restart"), ("back", "Back To Main Menu")]
        spacing, padding_x, padding_y, button_width = 64, 22, 12, 360
        start_y = self.cfg.height // 2 - len(labels) * spacing // 2 + 40
        for i, (key, text) in enumerate(labels):
            surf = self.font.render(text, True, (255, 255, 255))
            w = max(button_width, surf.get_width() + padding_x * 2)
            h = surf.get_height() + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            y = start_y + i * spacing
            self.go_button_rects.append((key, pygame.Rect(x, y, w, h)))

    def _calculate_final_score(self) -> None:
        # Calculate score breakdown with all bonuses
        login_streak, daily_streak = self.get_user_streaks()
        self.score_breakdown = calculate_score_breakdown(
            base_score=self.score,
            difficulty=self.cfg.difficulty,
            levels=self.wave,
            login_streak=login_streak,
            daily_streak=daily_streak,
            time_played=int(self.time_played)
        )
        # Update score to final score for saving
        self.score = self.score_breakdown.final_score

    def _draw_game_over(self) -> None:
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        title = self.title_font.render("Game Over", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 200))
        
        # Score breakdown box
        stats = [f"Wave: {self.wave}"]
        if self.score_breakdown:
            stats.extend(self.score_breakdown.as_display_lines())
        else:
            stats.append(f"Score: {self.score}")
        
        stat_surfs = [self.font.render(s, True, (220, 220, 240)) for s in stats]
        # Highlight final score line
        if self.score_breakdown and len(stat_surfs) > 0:
            stat_surfs[-1] = self.font.render(stats[-1], True, (255, 255, 100))
        
        pad_x, pad_y = 16, 14
        line_spacing = 6
        content_w = max(s.get_width() for s in stat_surfs)
        content_h = sum(s.get_height() for s in stat_surfs) + line_spacing * (len(stat_surfs) - 1)
        box_w = max(320, content_w + pad_x * 2)
        box_h = content_h + pad_y * 2
        box = pygame.Rect(self.cfg.width // 2 - box_w // 2, self.cfg.height // 2 - 140, box_w, box_h)
        pygame.draw.rect(self.screen, (35, 40, 80), box, border_radius=10)
        pygame.draw.rect(self.screen, (140, 150, 190), box, 2, border_radius=10)
        
        y = box.y + pad_y
        for s in stat_surfs:
            self.screen.blit(s, (box.x + pad_x, y))
            y += s.get_height() + line_spacing
        
        # Draw buttons below the box
        gap = 28
        self.go_button_rects.clear()
        labels = [("restart", "Restart"), ("back", "Back To Main Menu")]
        spacing, padding_x, padding_y, button_width = 64, 22, 12, 360
        start_y = box.bottom + gap
        for i, (key, text) in enumerate(labels):
            surf = self.font.render(text, True, (255, 255, 255))
            w = max(button_width, surf.get_width() + padding_x * 2)
            h = surf.get_height() + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            btn_y = start_y + i * spacing
            self.go_button_rects.append((key, pygame.Rect(x, btn_y, w, h)))
        
        mouse = pygame.mouse.get_pos()
        for key, rect in self.go_button_rects:
            hovered = rect.collidepoint(*mouse)
            fill = (70, 80, 120) if hovered else (40, 45, 85)
            border = (255, 255, 255) if hovered else (140, 150, 190)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=8)
            label = "Restart" if key == "restart" else "Back To Main Menu"
            ts = self.font.render(label, True, (255, 255, 255))
            self.screen.blit(ts, (rect.x + (rect.width - ts.get_width()) // 2, rect.y + (rect.height - ts.get_height()) // 2))
