"""
Hybrid Mode 4: Tetris + Space Invaders
"""

from __future__ import annotations
import random
import math
import pygame
from . import BaseGame, register_game
from systems.rules import get_rules
from systems.scoring import ScoreEvent, tetris_score, ScoreBreakdown, calculate_score_breakdown

# Import pre-defined constants from original game
from .tetris import TETROMINOES

# Hybrid-specific: Space Invader themed colors for each tetromino
INVADER_COLORS = {
    "I": (80, 255, 255),   # Cyan - like the cyan invader
    "O": (255, 255, 80),   # Yellow
    "L": (255, 165, 80),   # Orange
    "J": (80, 80, 255),    # Blue
    "T": (255, 80, 255),   # Magenta
    "S": (80, 255, 80),    # Green
    "Z": (255, 80, 80),    # Red
}

# Space Invader pixel patterns for each tetromino type
# Each block in the tetromino will display this pattern
INVADER_BLOCK_PATTERNS = {
    "I": [  # Squid-like
        [0,0,1,1,1,1,0,0],
        [0,1,1,1,1,1,1,0],
        [1,1,0,1,1,0,1,1],
        [1,1,1,1,1,1,1,1],
        [0,1,0,1,1,0,1,0],
        [1,0,1,0,0,1,0,1],
    ],
    "O": [  # Round alien
        [0,1,1,1,1,1,1,0],
        [1,1,1,1,1,1,1,1],
        [1,1,0,1,1,0,1,1],
        [1,1,1,1,1,1,1,1],
        [0,1,1,0,0,1,1,0],
        [0,0,1,1,1,1,0,0],
    ],
    "L": [  # Crab-like
        [0,0,1,0,0,1,0,0],
        [0,1,1,1,1,1,1,0],
        [1,1,0,1,1,0,1,1],
        [1,1,1,1,1,1,1,1],
        [0,1,0,0,0,0,1,0],
        [1,0,0,0,0,0,0,1],
    ],
    "J": [  # Octopus-like
        [0,0,0,1,1,0,0,0],
        [0,1,1,1,1,1,1,0],
        [1,1,1,1,1,1,1,1],
        [1,1,0,0,0,0,1,1],
        [0,1,1,0,0,1,1,0],
        [1,1,0,0,0,0,1,1],
    ],
    "T": [  # Classic invader
        [0,1,0,0,0,0,1,0],
        [0,0,1,1,1,1,0,0],
        [0,1,1,0,0,1,1,0],
        [1,1,1,1,1,1,1,1],
        [1,0,1,1,1,1,0,1],
        [1,0,1,0,0,1,0,1],
    ],
    "S": [  # Bug-like
        [0,0,1,1,1,1,0,0],
        [0,1,1,1,1,1,1,0],
        [1,1,0,1,1,0,1,1],
        [1,1,1,1,1,1,1,1],
        [0,0,1,0,0,1,0,0],
        [0,1,0,1,1,0,1,0],
    ],
    "Z": [  # Skull-like
        [0,1,1,1,1,1,1,0],
        [1,1,0,1,1,0,1,1],
        [1,1,1,1,1,1,1,1],
        [0,1,1,1,1,1,1,0],
        [0,0,1,0,0,1,0,0],
        [0,1,0,0,0,0,1,0],
    ],
}

# Stars for background
class Star:
    def __init__(self, x: float, y: float, size: int, brightness: int, speed: float):
        self.x = x
        self.y = y
        self.size = size
        self.brightness = brightness
        self.speed = speed
        self.twinkle_offset = random.random() * math.pi * 2


@register_game("hybrid_space_tetris")
class HybridSpaceTetrisGame(BaseGame):
    
    def __init__(self, screen: pygame.Surface, cfg, sounds, user_id=None):
        super().__init__(screen, cfg, sounds, user_id=user_id)
        self.name = "hybrid_space_tetris"
        self.rules = get_rules("tetris").data
        self.grid_width, self.grid_height = self.rules["grid_size"]
        self.grid = [[None for _ in range(self.grid_width)] for _ in range(self.grid_height)]
        self.current_piece: list[tuple[int, int]] = []
        self.current_shape_key: str | None = None
        self.next_shape_key: str = random.choice(list(TETROMINOES.keys()))
        self.piece_pos = [self.grid_width // 2, 0]
        self.drop_timer = 0.0
        self.gravity = self.rules["gravity_delay"]
        self.soft_drop = False
        
        # HUD/layout
        self.cell = 24
        self.offset_x = 80
        self.offset_y = 40
        self.hud_font = pygame.font.SysFont("courier", 24, bold=True)  # Arcade-style font
        self.title_font = pygame.font.SysFont("courier", 36, bold=True)
        
        # Progress (unchanged mechanics)
        self.level = 1
        self.total_lines = 0
        self.invaders_eliminated = 0  # Themed counter
        
        # Game over UI
        self.game_over: bool = False
        self.go_button_rects: list[tuple[str, pygame.Rect]] = []
        
        # Space bar hold protection
        self.space_pressed: bool = False
        
        # Line clear animation state
        self.clearing_rows: list[int] = []
        self.clearing: bool = False
        self.clear_anim_timer: float = 0.0
        self.clear_anim_duration: float = 0.45  # Slightly longer for effect
        
        # Explosion particles for line clear
        self.particles: list[dict] = []
        
        # Time tracking for bonus calculation
        self.time_played: float = 0.0
        self.score_breakdown: ScoreBreakdown | None = None
        
        # Space background
        self.stars: list[Star] = []
        self._generate_stars()
        
        # Animation timer for invader sprites
        self.anim_timer: float = 0.0
        
        # Pause state
        self.paused: bool = False
        self.pause_button_rects: list[tuple[str, pygame.Rect]] = []

    def _generate_stars(self) -> None:
        """Generate starfield for space background."""
        self.stars.clear()
        # Create layers of stars (parallax effect)
        for _ in range(60):  # Background stars (dim, slow)
            self.stars.append(Star(
                x=random.randint(0, self.cfg.width),
                y=random.randint(0, self.cfg.height),
                size=1,
                brightness=random.randint(40, 80),
                speed=random.uniform(2, 5)
            ))
        for _ in range(30):  # Mid-layer stars
            self.stars.append(Star(
                x=random.randint(0, self.cfg.width),
                y=random.randint(0, self.cfg.height),
                size=random.choice([1, 2]),
                brightness=random.randint(80, 140),
                speed=random.uniform(8, 15)
            ))
        for _ in range(15):  # Foreground stars (bright, fast)
            self.stars.append(Star(
                x=random.randint(0, self.cfg.width),
                y=random.randint(0, self.cfg.height),
                size=2,
                brightness=random.randint(150, 220),
                speed=random.uniform(20, 35)
            ))

    def reset(self) -> None:
        super().reset()
        self.grid = [[None for _ in range(self.grid_width)] for _ in range(self.grid_height)]
        self.level = 1
        self.total_lines = 0
        self.invaders_eliminated = 0
        self.drop_timer = 0.0
        self.soft_drop = False
        self.current_shape_key = None
        self.next_shape_key = random.choice(list(TETROMINOES.keys()))
        self.game_over = False
        self.go_button_rects.clear()
        self.space_pressed = False
        self.clearing_rows = []
        self.clearing = False
        self.clear_anim_timer = 0.0
        self.particles.clear()
        self.time_played = 0.0
        self.score_breakdown = None
        self.anim_timer = 0.0
        self.paused = False
        self._generate_stars()
        self.spawn_piece()

    def spawn_piece(self) -> None:
        """Spawn next tetromino (unchanged logic)."""
        self.current_shape_key = self.next_shape_key
        self.next_shape_key = random.choice(list(TETROMINOES.keys()))
        self.current_piece = list(TETROMINOES[self.current_shape_key])
        self.piece_pos = [self.grid_width // 2 - 2, 0]
        if not self.can_move(0, 0, self.current_piece, self.piece_pos):
            self.game_over = True
            self._calculate_final_score()
            self.save_score()

    def can_move(self, dx: int, dy: int, piece: list[tuple[int, int]] | None = None, pos: list[int] | None = None) -> bool:
        """Check if piece can move (unchanged logic)."""
        piece = piece or self.current_piece
        px, py = (pos or self.piece_pos)
        for x, y in piece:
            nx = px + x + dx
            ny = py + y + dy
            if nx < 0 or nx >= self.grid_width or ny < 0 or ny >= self.grid_height:
                return False
            if self.grid[ny][nx] is not None:
                return False
        return True

    def try_rotate(self) -> None:
        """Rotate piece with wall kicks (unchanged logic)."""
        if self.clearing:
            return
        rotated = [(-y, x) for (x, y) in self.current_piece]
        for kick_x in (0, -1, 1, -2, 2):
            if self.can_move(kick_x, 0, rotated):
                self.current_piece = rotated
                self.piece_pos[0] += kick_x
                return

    def lock_piece(self) -> None:
        """Lock piece into grid (unchanged logic)."""
        px, py = self.piece_pos
        shape_key = self.current_shape_key
        for x, y in self.current_piece:
            gx, gy = px + x, py + y
            if 0 <= gx < self.grid_width and 0 <= gy < self.grid_height:
                self.grid[gy][gx] = shape_key  # Store shape key for rendering

        full_rows = [y for y, row in enumerate(self.grid) if all(cell is not None for cell in row)]
        if full_rows:
            self.clearing_rows = full_rows
            self.clearing = True
            self.clear_anim_timer = 0.0
            self.current_piece = []
            self._spawn_explosion_particles(full_rows)
            self.sounds.play("line_clear")
            return
        self.spawn_piece()

    def _spawn_explosion_particles(self, rows: list[int]) -> None:
        """Spawn explosion particles when lines are cleared."""
        self.particles.clear()
        ox, oy = self.offset_x, self.offset_y
        cell = self.cell
        
        for row_y in rows:
            for x in range(self.grid_width):
                shape_key = self.grid[row_y][x]
                if shape_key:
                    color = INVADER_COLORS.get(shape_key, (255, 255, 255))
                    cx = ox + x * cell + cell // 2
                    cy = oy + row_y * cell + cell // 2
                    # Create multiple particles per block
                    for _ in range(4):
                        angle = random.uniform(0, math.pi * 2)
                        speed = random.uniform(50, 150)
                        self.particles.append({
                            'x': cx,
                            'y': cy,
                            'vx': math.cos(angle) * speed,
                            'vy': math.sin(angle) * speed,
                            'color': color,
                            'life': 1.0,
                            'size': random.randint(2, 5),
                        })

    def perform_line_clear(self) -> None:
        """Clear lines and update score (unchanged logic)."""
        cleared = len(self.clearing_rows)
        if cleared:
            new_rows = [row for y, row in enumerate(self.grid) if y not in self.clearing_rows]
            for _ in range(cleared):
                new_rows.insert(0, [None for _ in range(self.grid_width)])
            self.grid = new_rows
            
            self.total_lines += cleared
            self.invaders_eliminated += cleared * self.grid_width  # Themed count
            self.level = 1 + self.total_lines // 10
            self.score += tetris_score(ScoreEvent(lines_cleared=cleared, level=self.level))

        self.clearing_rows = []
        self.clearing = False
        self.clear_anim_timer = 0.0
        self.spawn_piece()

    def handle_event(self, event: pygame.event.Event) -> None:
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
        
        # Pause handling
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.paused = not self.paused
            return
        
        if self.paused:
            if not self.pause_button_rects:
                self._build_pause_buttons()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for key, rect in self.pause_button_rects:
                    if rect.collidepoint(mx, my):
                        if key == "resume":
                            self.paused = False
                        elif key == "restart":
                            self.reset()
                        elif key == "back":
                            pygame.event.post(pygame.event.Event(pygame.USEREVENT, {"action": "back_to_menu"}))
                        break
            return
        
        if self.clearing:
            return
        
        # Standard Tetris controls (unchanged)
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_LEFT, pygame.K_a):
                if self.can_move(-1, 0):
                    self.piece_pos[0] -= 1
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                if self.can_move(1, 0):
                    self.piece_pos[0] += 1
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.soft_drop = True
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.try_rotate()
            elif event.key == pygame.K_SPACE:
                if not self.space_pressed:
                    self.space_pressed = True
                    self.hard_drop()
        elif event.type == pygame.KEYUP:
            if event.key in (pygame.K_DOWN, pygame.K_s):
                self.soft_drop = False
            elif event.key == pygame.K_SPACE:
                self.space_pressed = False

    def update(self, dt: float) -> None:
        if self.game_over or self.paused:
            return
        
        self.time_played += dt
        self.anim_timer += dt
        
        # Update stars (slow drift)
        for star in self.stars:
            star.y += star.speed * dt
            if star.y > self.cfg.height:
                star.y = 0
                star.x = random.randint(0, self.cfg.width)
        
        # Update particles
        for p in self.particles[:]:
            p['x'] += p['vx'] * dt
            p['y'] += p['vy'] * dt
            p['vy'] += 200 * dt  # Gravity on particles
            p['life'] -= dt * 2.5
            if p['life'] <= 0:
                self.particles.remove(p)
        
        # Line clear animation
        if self.clearing:
            self.clear_anim_timer += dt
            if self.clear_anim_timer >= self.clear_anim_duration:
                self.perform_line_clear()
            return
        
        # Standard gravity (unchanged)
        drop_interval = self.gravity / (self.rules["fast_drop_multiplier"] if self.soft_drop else 1)
        self.drop_timer += dt
        if self.drop_timer >= drop_interval:
            self.drop_timer = 0.0
            if self.can_move(0, 1):
                self.piece_pos[1] += 1
            else:
                self.lock_piece()

    def draw(self) -> None:
        # Draw space background first
        self._draw_space_background()
        
        # Draw the Tetris board
        self._draw_board()
        
        # Draw particles
        self._draw_particles()
        
        # Draw current piece
        if self.current_piece and self.current_shape_key:
            self._draw_invader_piece(self.current_piece, self.piece_pos, self.current_shape_key)
        
        # Draw HUD
        self._draw_hud()
        
        # Overlays
        if self.paused:
            self._draw_pause_menu()
        elif self.game_over:
            self.draw_game_over_overlay()

    def _draw_space_background(self) -> None:
        """Draw starfield background."""
        # Deep space black with slight blue tint
        self.screen.fill((5, 5, 20))
        
        # Draw stars with twinkle effect
        time_ms = pygame.time.get_ticks()
        for star in self.stars:
            # Twinkle effect
            twinkle = math.sin(time_ms * 0.003 + star.twinkle_offset) * 0.3 + 0.7
            brightness = int(star.brightness * twinkle)
            color = (brightness, brightness, min(255, brightness + 20))  # Slight blue tint
            
            if star.size == 1:
                self.screen.set_at((int(star.x), int(star.y)), color)
            else:
                pygame.draw.circle(self.screen, color, (int(star.x), int(star.y)), star.size)

    def _draw_board(self) -> None:
        """Draw the Tetris grid with space theme."""
        cell = self.cell
        ox, oy = self.offset_x, self.offset_y
        
        # Draw grid background (dark space with subtle grid lines)
        board_rect = pygame.Rect(ox - 2, oy - 2, 
                                 self.grid_width * cell + 4, 
                                 self.grid_height * cell + 4)
        pygame.draw.rect(self.screen, (10, 10, 30), board_rect)
        pygame.draw.rect(self.screen, (60, 60, 100), board_rect, 2)
        
        # Draw grid cells
        for y, row in enumerate(self.grid):
            for x, shape_key in enumerate(row):
                cell_rect = pygame.Rect(ox + x * cell, oy + y * cell, cell - 1, cell - 1)
                
                if shape_key is None:
                    # Empty cell - subtle grid pattern
                    pygame.draw.rect(self.screen, (15, 15, 35), cell_rect)
                    # Grid lines
                    pygame.draw.rect(self.screen, (25, 25, 50), cell_rect, 1)
                else:
                    # Locked block - draw as invader sprite
                    self._draw_invader_block(cell_rect, shape_key)
        
        # Line clear flash effect
        if self.clearing and self.clearing_rows:
            p = max(0.0, min(1.0, self.clear_anim_timer / self.clear_anim_duration))
            # Multiple flash pulses
            flash_intensity = abs(math.sin(p * math.pi * 4)) * (1.0 - p)
            alpha = int(255 * flash_intensity)
            
            for y in self.clearing_rows:
                row_rect = pygame.Rect(ox, oy + y * cell, self.grid_width * cell, cell - 1)
                s = pygame.Surface((row_rect.width, row_rect.height), pygame.SRCALPHA)
                s.fill((255, 255, 255, alpha))
                self.screen.blit(s, row_rect.topleft)

    def _draw_invader_block(self, rect: pygame.Rect, shape_key: str) -> None:
        """Draw a single block as a Space Invader sprite."""
        color = INVADER_COLORS.get(shape_key, (200, 200, 200))
        pattern = INVADER_BLOCK_PATTERNS.get(shape_key, INVADER_BLOCK_PATTERNS["I"])
        
        # Background glow
        glow_color = tuple(max(0, c - 100) for c in color)
        pygame.draw.rect(self.screen, glow_color, rect)
        
        # Draw pixel pattern
        pattern_h = len(pattern)
        pattern_w = len(pattern[0]) if pattern else 0
        
        if pattern_w == 0 or pattern_h == 0:
            return
        
        pixel_w = max(1, rect.width // pattern_w)
        pixel_h = max(1, rect.height // pattern_h)
        
        start_x = rect.x + (rect.width - pattern_w * pixel_w) // 2
        start_y = rect.y + (rect.height - pattern_h * pixel_h) // 2
        
        # Animation frame
        anim_frame = int(self.anim_timer * 3) % 2
        
        for py, row in enumerate(pattern):
            for px, pixel in enumerate(row):
                if pixel == 1:
                    # Animate bottom rows
                    offset_x = 0
                    if py >= pattern_h - 1 and anim_frame == 1:
                        offset_x = 1 if px < pattern_w // 2 else -1
                    
                    pygame.draw.rect(
                        self.screen, color,
                        pygame.Rect(
                            start_x + px * pixel_w + offset_x,
                            start_y + py * pixel_h,
                            pixel_w,
                            pixel_h
                        )
                    )

    def _draw_invader_piece(self, piece: list[tuple[int, int]], pos: list[int], shape_key: str) -> None:
        """Draw the current falling piece as invader sprites."""
        ox, oy = self.offset_x, self.offset_y
        cell = self.cell
        
        for x, y in piece:
            px = ox + (pos[0] + x) * cell
            py = oy + (pos[1] + y) * cell
            rect = pygame.Rect(px, py, cell - 1, cell - 1)
            self._draw_invader_block(rect, shape_key)

    def _draw_particles(self) -> None:
        """Draw explosion particles."""
        for p in self.particles:
            alpha = int(255 * p['life'])
            size = int(p['size'] * p['life'])
            if size > 0:
                color = (*p['color'][:3], alpha)
                s = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                pygame.draw.circle(s, color, (size, size), size)
                self.screen.blit(s, (int(p['x']) - size, int(p['y']) - size))

    def _draw_hud(self) -> None:
        """Draw HUD with arcade/space theme."""
        cell = self.cell
        ox, oy = self.offset_x, self.offset_y
        board_w = self.grid_width * cell
        panel_x = ox + board_w + 24
        panel_y = oy
        
        # Title label
        mode_label = self.hud_font.render("SPACE TETRIS", True, (255, 100, 100))
        self.screen.blit(mode_label, (self.cfg.width // 2 - mode_label.get_width() // 2, 8))
        
        # Next piece box
        next_label = self.hud_font.render("NEXT", True, (100, 255, 100))
        self.screen.blit(next_label, (panel_x, panel_y))
        
        box = pygame.Rect(panel_x, panel_y + 28, 120, 100)
        pygame.draw.rect(self.screen, (15, 20, 40), box, border_radius=8)
        pygame.draw.rect(self.screen, (80, 255, 80), box, width=2, border_radius=8)
        
        # Draw next piece
        if self.next_shape_key:
            pts = TETROMINOES[self.next_shape_key]
            minx = min(x for x, _ in pts)
            miny = min(y for _, y in pts)
            norm = [(x - minx, y - miny) for x, y in pts]
            
            preview_cell = 20
            base_x = box.x + (box.width - 4 * preview_cell) // 2
            base_y = box.y + (box.height - 4 * preview_cell) // 2
            
            for x, y in norm:
                rect = pygame.Rect(base_x + x * preview_cell, base_y + y * preview_cell, 
                                   preview_cell - 1, preview_cell - 1)
                self._draw_invader_block(rect, self.next_shape_key)
        
        # Stats with arcade styling
        score_y = box.bottom + 20
        
        # Score
        score_surf = self.hud_font.render(f"SCORE", True, (255, 255, 100))
        score_val = self.hud_font.render(f"{self.score:,}", True, (255, 255, 255))
        self.screen.blit(score_surf, (panel_x, score_y))
        self.screen.blit(score_val, (panel_x, score_y + 22))
        
        # Level (themed as "WAVE")
        wave_y = score_y + 60
        wave_surf = self.hud_font.render(f"WAVE", True, (100, 200, 255))
        wave_val = self.hud_font.render(f"{self.level}", True, (255, 255, 255))
        self.screen.blit(wave_surf, (panel_x, wave_y))
        self.screen.blit(wave_val, (panel_x, wave_y + 22))
        
        # Lines (themed as "ELIMINATED")
        elim_y = wave_y + 60
        elim_surf = self.hud_font.render(f"CLEARED", True, (255, 100, 200))
        elim_val = self.hud_font.render(f"{self.total_lines} LINES", True, (255, 255, 255))
        self.screen.blit(elim_surf, (panel_x, elim_y))
        self.screen.blit(elim_val, (panel_x, elim_y + 22))

    def _build_pause_buttons(self) -> None:
        self.pause_button_rects.clear()
        labels = [("resume", "RESUME"), ("restart", "RESTART"), ("back", "MAIN MENU")]
        spacing, padding_x, padding_y, button_width = 64, 22, 12, 360
        start_y = self.cfg.height // 2 - len(labels) * spacing // 2
        for i, (key, text) in enumerate(labels):
            surf = self.hud_font.render(text, True, (255, 255, 255))
            w = max(button_width, surf.get_width() + padding_x * 2)
            h = surf.get_height() + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            y = start_y + i * spacing
            self.pause_button_rects.append((key, pygame.Rect(x, y, w, h)))

    def _draw_pause_menu(self) -> None:
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        title = self.title_font.render("PAUSED", True, (100, 255, 100))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 140))
        
        self._build_pause_buttons()
        mouse = pygame.mouse.get_pos()
        for key, rect in self.pause_button_rects:
            hovered = rect.collidepoint(*mouse)
            fill = (30, 60, 30) if hovered else (20, 40, 20)
            border = (100, 255, 100) if hovered else (60, 150, 60)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=8)
            label = {"resume": "RESUME", "restart": "RESTART", "back": "MAIN MENU"}[key]
            ts = self.hud_font.render(label, True, (100, 255, 100))
            self.screen.blit(ts, (rect.x + (rect.width - ts.get_width()) // 2, 
                                  rect.y + (rect.height - ts.get_height()) // 2))

    def _calculate_final_score(self) -> None:
        login_streak, daily_streak = self.get_user_streaks()
        self.score_breakdown = calculate_score_breakdown(
            base_score=self.score,
            difficulty=self.cfg.difficulty,
            levels=self.level,
            login_streak=login_streak,
            daily_streak=daily_streak,
            time_played=int(self.time_played)
        )
        self.score = self.score_breakdown.final_score

    def build_go_buttons(self, start_y: int | None = None) -> None:
        self.go_button_rects.clear()
        labels = [("restart", "PLAY AGAIN"), ("back", "MAIN MENU")]
        spacing = 64
        padding_x, padding_y = 22, 12
        button_width = 360
        if start_y is None:
            total_h = len(labels) * spacing
            start_y = self.cfg.height // 2 - total_h // 2 + 20
        for i, (key, text) in enumerate(labels):
            surf = self.hud_font.render(text, True, (255, 255, 255))
            tw, th = surf.get_size()
            w = max(button_width, tw + padding_x * 2)
            h = th + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            y = start_y + i * spacing
            self.go_button_rects.append((key, pygame.Rect(x, y, w, h)))

    def draw_game_over_overlay(self) -> None:
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))
        
        # Game over title with arcade style
        title = self.title_font.render("GAME OVER", True, (255, 80, 80))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 200))
        
        # Stats
        stats = [f"WAVE: {self.level}", f"LINES CLEARED: {self.total_lines}"]
        if self.score_breakdown:
            stats.extend(self.score_breakdown.as_display_lines())
        else:
            stats.append(f"SCORE: {self.score}")
        
        stat_surfs = [self.hud_font.render(line, True, (200, 200, 220)) for line in stats]
        if self.score_breakdown and len(stat_surfs) > 0:
            stat_surfs[-1] = self.hud_font.render(stats[-1], True, (255, 255, 100))
        
        pad_x, pad_y = 16, 14
        line_spacing = 6
        content_w = max(s.get_width() for s in stat_surfs)
        content_h = sum(s.get_height() for s in stat_surfs) + line_spacing * (len(stat_surfs) - 1)
        box_w = max(320, content_w + pad_x * 2)
        box_h = content_h + pad_y * 2
        box_x = self.cfg.width // 2 - box_w // 2
        box_y = self.cfg.height // 2 - 140
        data_box = pygame.Rect(box_x, box_y, box_w, box_h)
        
        pygame.draw.rect(self.screen, (20, 15, 40), data_box, border_radius=10)
        pygame.draw.rect(self.screen, (255, 80, 80), data_box, width=2, border_radius=10)
        
        curr_y = data_box.y + pad_y
        for surf in stat_surfs:
            self.screen.blit(surf, (data_box.x + pad_x, curr_y))
            curr_y += surf.get_height() + line_spacing
        
        gap = 28
        self.build_go_buttons(start_y=data_box.bottom + gap)
        mouse_pos = pygame.mouse.get_pos()
        for key, rect in self.go_button_rects:
            label = "PLAY AGAIN" if key == "restart" else "MAIN MENU"
            hovered = rect.collidepoint(*mouse_pos)
            fill = (60, 30, 30) if hovered else (40, 20, 20)
            border = (255, 100, 100) if hovered else (150, 60, 60)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
            text_surf = self.hud_font.render(label, True, (255, 100, 100))
            tx = rect.x + (rect.width - text_surf.get_width()) // 2
            ty = rect.y + (rect.height - text_surf.get_height()) // 2
            self.screen.blit(text_surf, (tx, ty))

    def hard_drop(self) -> None:
        """Hard drop piece (unchanged logic)."""
        if self.game_over or self.clearing or not self.current_piece:
            return
        while self.can_move(0, 1):
            self.piece_pos[1] += 1
        self.lock_piece()
