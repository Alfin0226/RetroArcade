"""
Hybrid Mode 2: Snake + Tetris

Combines standard Tetris gameplay with a Snake-themed visual background.
The Snake map is rendered as a decorative layer behind the Tetris board.
All Tetris mechanics remain completely unchanged.

⚠️ No modifications were made to the Tetris logic for this hybrid.

Win/Lose conditions: Same as standard Tetris
Snake contributes atmosphere, not mechanics.
"""
from __future__ import annotations
import random
import pygame
from . import BaseGame, register_game
from systems.rules import get_rules
from systems.scoring import ScoreEvent, tetris_score, ScoreBreakdown, calculate_score_breakdown

# Import pre-defined constants from original game
from .tetris import TETROMINOES

# ==================== HYBRID-SPECIFIC COMPONENTS ====================

# Snake-themed colors for tetrominoes (greenish palette)
SHAPE_COLORS = {
    "I": (100, 180, 100),   # Light green
    "O": (80, 150, 80),     # Medium green
    "L": (60, 130, 60),     # Forest green
    "J": (120, 200, 120),   # Bright green
    "T": (90, 160, 90),     # Sage green
    "S": (70, 140, 70),     # Green
    "Z": (110, 190, 110),   # Lime green
}

# ==================== SNAKE BACKGROUND COMPONENTS ====================

# Snake background grid settings
SNAKE_GRID_W = 20
SNAKE_GRID_H = 15

# Snake colors matching the actual Snake game (bright green checkerboard)
SNAKE_BG_LIGHT = (176, 221, 120)  # Light grass green
SNAKE_BG_DARK = (162, 207, 106)   # Darker grass green
SNAKE_BG_BORDER = (46, 102, 46)   # Dark green border
SNAKE_BODY_COLOR = (76, 120, 255) # Blue snake body (matches snake game)
SNAKE_HEAD_COLOR = (76, 120, 255) # Blue snake head
APPLE_COLOR = (255, 80, 80)       # Bright red apple


@register_game("hybrid_tetris")
class HybridTetrisGame(BaseGame):
    """
    Hybrid Mode 2: Tetris with Snake-themed background.
    
    The Snake map is used purely as a visual background while all core
    Tetris mechanics remain unchanged. Snake elements do not interact
    with Tetris pieces.
    """
    
    def __init__(self, screen: pygame.Surface, cfg, sounds, user_id=None):
        super().__init__(screen, cfg, sounds, user_id=user_id)
        self.name = "hybrid_tetris"
        
        # ==================== TETRIS SETUP (UNCHANGED) ====================
        self.rules = get_rules("tetris").data
        self.grid_width, self.grid_height = self.rules["grid_size"]
        self.grid = [[0 for _ in range(self.grid_width)] for _ in range(self.grid_height)]
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
        self.hud_font = pygame.font.SysFont("arial", 24)
        self.title_font = pygame.font.SysFont("arial", 32)
        
        # Progress
        self.level = 1
        self.total_lines = 0
        
        # Game over UI
        self.game_over: bool = False
        self.go_button_rects: list[tuple[str, pygame.Rect]] = []
        
        # Space bar hold protection
        self.space_pressed: bool = False
        
        # Line clear animation state
        self.clearing_rows: list[int] = []
        self.clearing: bool = False
        self.clear_anim_timer: float = 0.0
        self.clear_anim_duration: float = 0.35
        
        # Time tracking for bonus calculation
        self.time_played: float = 0.0
        self.score_breakdown: ScoreBreakdown | None = None
        
        # ==================== SNAKE BACKGROUND SETUP ====================
        self._init_snake_background()

    def _init_snake_background(self) -> None:
        """Initialize the decorative snake background."""
        # Calculate snake cell size to fit behind tetris board
        board_width = self.grid_width * self.cell
        board_height = self.grid_height * self.cell
        
        self.snake_cell = max(12, min(board_width // SNAKE_GRID_W, board_height // SNAKE_GRID_H))
        
        # Center snake grid behind tetris board
        snake_total_w = SNAKE_GRID_W * self.snake_cell
        snake_total_h = SNAKE_GRID_H * self.snake_cell
        
        self.snake_offset_x = self.offset_x + (board_width - snake_total_w) // 2
        self.snake_offset_y = self.offset_y + (board_height - snake_total_h) // 2

    # ==================== TETRIS LOGIC (UNCHANGED) ====================

    def reset(self) -> None:
        super().reset()
        self.grid = [[0 for _ in range(self.grid_width)] for _ in range(self.grid_height)]
        self.level = 1
        self.total_lines = 0
        self.drop_timer = 0.0
        self.soft_drop = False
        self.current_shape_key = None
        self.next_shape_key = random.choice(list(TETROMINOES.keys()))
        self.game_over = False
        self.go_button_rects.clear()
        self.space_pressed = False
        # Reset animation state
        self.clearing_rows = []
        self.clearing = False
        self.clear_anim_timer = 0.0
        self.time_played = 0.0
        self.score_breakdown = None
        self.spawn_piece()

    def spawn_piece(self) -> None:
        # Use next shape, then pick the next preview
        self.current_shape_key = self.next_shape_key
        self.next_shape_key = random.choice(list(TETROMINOES.keys()))
        self.current_piece = list(TETROMINOES[self.current_shape_key])
        self.piece_pos = [self.grid_width // 2 - 2, 0]
        # If spawn position is blocked then is Game Over
        if not self.can_move(0, 0, self.current_piece, self.piece_pos):
            self.game_over = True
            self._calculate_final_score()
            self.save_score()
            return

    def can_move(self, dx: int, dy: int, piece: list[tuple[int, int]] | None = None, pos: list[int] | None = None) -> bool:
        piece = piece or self.current_piece
        px, py = (pos or self.piece_pos)
        for x, y in piece:
            nx = px + x + dx
            ny = py + y + dy
            if nx < 0 or nx >= self.grid_width or ny < 0 or ny >= self.grid_height:
                return False
            if self.grid[ny][nx]:
                return False
        return True

    def try_rotate(self) -> None:
        if self.clearing:
            return
        rotated = [(-y, x) for (x, y) in self.current_piece]
        for kick_x in (0, -1, 1, -2, 2):
            if self.can_move(kick_x, 0, rotated):
                self.current_piece = rotated
                self.piece_pos[0] += kick_x
                return

    def lock_piece(self) -> None:
        px, py = self.piece_pos
        color = SHAPE_COLORS.get(self.current_shape_key, (100, 180, 100))
        for x, y in self.current_piece:
            gx, gy = px + x, py + y
            if 0 <= gx < self.grid_width and 0 <= gy < self.grid_height:
                self.grid[gy][gx] = color

        full_rows = [y for y, row in enumerate(self.grid) if all(cell != 0 for cell in row)]
        if full_rows:
            self.clearing_rows = full_rows
            self.clearing = True
            self.clear_anim_timer = 0.0
            self.current_piece = []
            self.sounds.play("line_clear")
            return

        self.spawn_piece()

    def perform_line_clear(self) -> None:
        cleared = len(self.clearing_rows)
        if cleared:
            new_rows = [row for y, row in enumerate(self.grid) if y not in self.clearing_rows]
            for _ in range(cleared):
                new_rows.insert(0, [0 for _ in range(self.grid_width)])
            self.grid = new_rows

            self.total_lines += cleared
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
        
        if self.clearing:
            return
        
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
        if self.game_over:
            return
        
        self.time_played += dt
        
        if self.clearing:
            self.clear_anim_timer += dt
            if self.clear_anim_timer >= self.clear_anim_duration:
                self.perform_line_clear()
            return
        
        drop_interval = self.gravity / (self.rules["fast_drop_multiplier"] if self.soft_drop else 1)
        self.drop_timer += dt
        if self.drop_timer >= drop_interval:
            self.drop_timer = 0.0
            if self.can_move(0, 1):
                self.piece_pos[1] += 1
            else:
                self.lock_piece()

    def hard_drop(self) -> None:
        if self.game_over or self.clearing or not self.current_piece:
            return
        while self.can_move(0, 1):
            self.piece_pos[1] += 1
        self.lock_piece()

    # ==================== DRAWING (LAYERED RENDERING) ====================

    def draw(self) -> None:
        """
        Rendering order:
        1. Snake-style green checkerboard background
        2. Tetris grid with tetrominoes (decorated with snake/apple)
        3. UI / score
        """
        # Layer 1 & 2: Tetris board with snake-style background
        self._draw_tetris_board()
        
        # Layer 3: UI
        self.draw_hud()
        
        # Game Over overlay
        if self.game_over:
            self.draw_game_over_overlay()

    def _draw_tetris_board(self) -> None:
        """Draw the Tetris board with Snake-style green checkerboard background."""
        cell = self.cell
        ox, oy = self.offset_x, self.offset_y
        board_w = self.grid_width * cell
        board_h = self.grid_height * cell
        
        # Draw dark green border around the board (like Snake game)
        border_rect = pygame.Rect(ox - 4, oy - 4, board_w + 8, board_h + 8)
        pygame.draw.rect(self.screen, SNAKE_BG_BORDER, border_rect, border_radius=4)
        
        # Draw Snake-style green checkerboard background for empty cells
        for y in range(self.grid_height):
            for x in range(self.grid_width):
                cell_rect = pygame.Rect(ox + x * cell, oy + y * cell, cell, cell)
                
                # Alternating green checkerboard pattern
                bg_color = SNAKE_BG_LIGHT if (x + y) % 2 == 0 else SNAKE_BG_DARK
                pygame.draw.rect(self.screen, bg_color, cell_rect)
        
        # Draw locked pieces on the grid with snake/apple decorations
        for y, row in enumerate(self.grid):
            for x, value in enumerate(row):
                if value != 0:
                    cell_rect = pygame.Rect(ox + x * cell, oy + y * cell, cell - 1, cell - 1)
                    # Draw the tetromino cell
                    pygame.draw.rect(self.screen, value, cell_rect, border_radius=3)
                    # Add snake segment decoration (small circle pattern)
                    cx, cy = cell_rect.centerx, cell_rect.centery
                    pygame.draw.circle(self.screen, (255, 255, 255, 80), (cx, cy), 4)
                    pygame.draw.circle(self.screen, value, (cx, cy), 3)
        
        # Line clear effect overlay
        if self.clearing and self.clearing_rows:
            p = max(0.0, min(1.0, self.clear_anim_timer / self.clear_anim_duration))
            alpha = int(200 * (1.0 - p))
            overlay_color = (150, 255, 150, alpha)  # Green-tinted flash
            for y in self.clearing_rows:
                row_rect = pygame.Rect(ox, oy + y * cell, self.grid_width * cell, cell - 1)
                s = pygame.Surface((row_rect.width, row_rect.height), pygame.SRCALPHA)
                s.fill(overlay_color)
                self.screen.blit(s, row_rect.topleft)
        
        # Current falling piece with snake/apple decorations
        if self.current_piece and self.current_shape_key:
            color = SHAPE_COLORS.get(self.current_shape_key, (100, 180, 100))
            for idx, (x, y) in enumerate(self.current_piece):
                px = ox + (self.piece_pos[0] + x) * cell
                py = oy + (self.piece_pos[1] + y) * cell
                piece_rect = pygame.Rect(px, py, cell - 1, cell - 1)
                pygame.draw.rect(self.screen, color, piece_rect, border_radius=3)
                
                # Add decoration: first block gets apple, others get snake segment look
                cx, cy = piece_rect.centerx, piece_rect.centery
                if idx == 0:
                    # Apple decoration on first block
                    pygame.draw.circle(self.screen, APPLE_COLOR, (cx, cy), 5)
                    pygame.draw.line(self.screen, (139, 90, 43), (cx, cy - 5), (cx + 1, cy - 8), 2)
                    pygame.draw.ellipse(self.screen, (34, 139, 34), pygame.Rect(cx + 1, cy - 10, 4, 3))
                else:
                    # Snake segment decoration (eyes on one block)
                    if idx == 1:
                        # Snake head with eyes
                        pygame.draw.circle(self.screen, (245, 248, 255), (cx - 3, cy - 1), 3)
                        pygame.draw.circle(self.screen, (245, 248, 255), (cx + 3, cy - 1), 3)
                        pygame.draw.circle(self.screen, (30, 70, 160), (cx - 2, cy - 1), 1)
                        pygame.draw.circle(self.screen, (30, 70, 160), (cx + 4, cy - 1), 1)
                    else:
                        # Snake body segment pattern
                        pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), 4)
                        pygame.draw.circle(self.screen, color, (cx, cy), 3)

    def draw_hud(self) -> None:
        """Draw HUD with snake-themed styling."""
        cell = self.cell
        ox, oy = self.offset_x, self.offset_y
        board_w = self.grid_width * cell
        panel_x = ox + board_w + 24
        panel_y = oy
        
        # Mode label
        mode_label = self.hud_font.render("SNAKE + TETRIS", True, (100, 200, 100))
        self.screen.blit(mode_label, (panel_x, panel_y - 30))
        
        # Next box
        next_label = self.hud_font.render("Next", True, (200, 255, 200))
        self.screen.blit(next_label, (panel_x, panel_y))
        box = pygame.Rect(panel_x, panel_y + 28, 120, 100)
        pygame.draw.rect(self.screen, (30, 50, 30), box, border_radius=8)
        pygame.draw.rect(self.screen, (80, 140, 80), box, width=2, border_radius=8)
        
        # Draw next shape
        if self.next_shape_key:
            pts = TETROMINOES[self.next_shape_key]
            color = SHAPE_COLORS.get(self.next_shape_key, (100, 180, 100))
            minx = min(x for x, _ in pts)
            miny = min(y for _, y in pts)
            norm = [(x - minx, y - miny) for x, y in pts]
            base_x = box.x + (box.width - 4 * cell) // 2
            base_y = box.y + (box.height - 4 * cell) // 2
            for x, y in norm:
                rx = base_x + x * cell
                ry = base_y + y * cell
                pygame.draw.rect(self.screen, color, pygame.Rect(rx, ry, cell - 1, cell - 1))
        
        # Score, Level, Lines with snake theme
        score_y = box.bottom + 20
        score_surf = self.hud_font.render(f"Score: {self.score}", True, (200, 255, 200))
        lvl_surf = self.hud_font.render(f"Level: {self.level}", True, (180, 230, 180))
        lines_surf = self.hud_font.render(f"Lines: {self.total_lines}", True, (160, 210, 160))
        self.screen.blit(score_surf, (panel_x, score_y))
        self.screen.blit(lvl_surf, (panel_x, score_y + 30))
        self.screen.blit(lines_surf, (panel_x, score_y + 60))
        
        # Decorative apple icon in HUD (non-interactive)
        apple_x = panel_x + 100
        apple_y = score_y + 100
        pygame.draw.circle(self.screen, (180, 80, 80), (apple_x, apple_y), 8)
        pygame.draw.line(self.screen, (100, 70, 50), (apple_x, apple_y - 8), (apple_x + 2, apple_y - 12), 2)
        pygame.draw.ellipse(self.screen, (80, 160, 80), pygame.Rect(apple_x + 2, apple_y - 14, 6, 4))

    # ==================== GAME OVER ====================

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
        labels = [("restart", "Play Again"), ("back", "Back To Menu")]
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
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        title = self.title_font.render("Game Over", True, (200, 255, 200))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 200))

        # Stats with score breakdown
        stats = [f"Level: {self.level}", f"Lines: {self.total_lines}"]
        if self.score_breakdown:
            stats.extend(self.score_breakdown.as_display_lines())
        else:
            stats.append(f"Score: {self.score}")
        
        stat_surfs = [self.hud_font.render(line, True, (200, 240, 200)) for line in stats]
        if self.score_breakdown and len(stat_surfs) > 0:
            stat_surfs[-1] = self.hud_font.render(stats[-1], True, (200, 255, 150))
        
        # Data box
        pad_x, pad_y = 16, 14
        line_spacing = 6
        content_w = max(s.get_width() for s in stat_surfs)
        content_h = sum(s.get_height() for s in stat_surfs) + line_spacing * (len(stat_surfs) - 1)
        box_w = max(320, content_w + pad_x * 2)
        box_h = content_h + pad_y * 2
        box_x = self.cfg.width // 2 - box_w // 2
        box_y = self.cfg.height // 2 - 140
        data_box = pygame.Rect(box_x, box_y, box_w, box_h)
        
        pygame.draw.rect(self.screen, (30, 50, 35), data_box, border_radius=10)
        pygame.draw.rect(self.screen, (80, 150, 100), data_box, width=2, border_radius=10)
        
        curr_y = data_box.y + pad_y
        for surf in stat_surfs:
            self.screen.blit(surf, (data_box.x + pad_x, curr_y))
            curr_y += surf.get_height() + line_spacing

        # Buttons
        gap = 28
        self.build_go_buttons(start_y=data_box.bottom + gap)
        mouse_pos = pygame.mouse.get_pos()
        for key, rect in self.go_button_rects:
            label = "Play Again" if key == "restart" else "Back To Menu"
            hovered = rect.collidepoint(*mouse_pos)
            fill = (50, 80, 60) if hovered else (35, 55, 45)
            border = (150, 255, 150) if hovered else (80, 140, 100)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
            text_surf = self.hud_font.render(label, True, (200, 255, 200))
            tx = rect.x + (rect.width - text_surf.get_width()) // 2
            ty = rect.y + (rect.height - text_surf.get_height()) // 2
            self.screen.blit(text_surf, (tx, ty))
