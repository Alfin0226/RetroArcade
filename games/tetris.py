from __future__ import annotations
import random
import pygame
from . import BaseGame, register_game
from systems.rules import get_rules
from systems.scoring import ScoreEvent, tetris_score, ScoreBreakdown, calculate_score_breakdown

TETROMINOES = {
    "I": [(0, 0), (1, 0), (2, 0), (3, 0)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "L": [(0, 0), (0, 1), (0, 2), (1, 2)],
    "J": [(1, 0), (1, 1), (1, 2), (0, 2)],
    "T": [(0, 0), (1, 0), (2, 0), (1, 1)],
    "S": [(1, 0), (2, 0), (0, 1), (1, 1)],
    "Z": [(0, 0), (1, 0), (1, 1), (2, 1)],
}

SHAPE_COLORS = {
    "I": (0, 255, 255),
    "O": (255, 255, 120),
    "L": (255, 165, 0),
    "J": (80, 120, 255),
    "T": (190, 120, 255),
    "S": (120, 220, 120),
    "Z": (255, 100, 120),
}

@register_game("tetris")
class TetrisGame(BaseGame):
    def __init__(self, screen: pygame.Surface, cfg, sounds, user_id=None):
        super().__init__(screen, cfg, sounds, user_id=user_id)
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
            self.save_score()  # Save score to database
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
        # Skip rotation while clearing
        if self.clearing:
            return
        # 90-degree rotation around origin with simple wall kicks
        rotated = [(-y, x) for (x, y) in self.current_piece]
        for kick_x in (0, -1, 1, -2, 2):
            if self.can_move(kick_x, 0, rotated):
                self.current_piece = rotated
                self.piece_pos[0] += kick_x
                return
        # rotation fails -> keep as is

    def lock_piece(self) -> None:
        # Merge piece into grid
        px, py = self.piece_pos
        color = SHAPE_COLORS.get(self.current_shape_key, (200, 120, 255))
        for x, y in self.current_piece:
            gx, gy = px + x, py + y
            if 0 <= gx < self.grid_width and 0 <= gy < self.grid_height:
                self.grid[gy][gx] = color  # store the color

        # Prepare animation if there are full rows
        full_rows = [y for y, row in enumerate(self.grid) if all(cell != 0 for cell in row)]
        if full_rows:
            self.clearing_rows = full_rows
            self.clearing = True
            self.clear_anim_timer = 0.0
            # Clear active piece so it doesn't draw during animation
            self.current_piece = []
            # Start sound now for feedback
            self.sounds.play("line_clear")
            return

        # No lines to clear → spawn next (may set game_over if blocked)
        self.spawn_piece()

    def perform_line_clear(self) -> None:
        # Remove full rows, update scoring and level
        cleared = len(self.clearing_rows)
        if cleared:
            # Rebuild grid keeping only non-full rows
            new_rows = [row for y, row in enumerate(self.grid) if y not in self.clearing_rows]
            for _ in range(cleared):
                new_rows.insert(0, [0 for _ in range(self.grid_width)])
            self.grid = new_rows

            self.total_lines += cleared
            self.level = 1 + self.total_lines // 10
            self.score += tetris_score(ScoreEvent(lines_cleared=cleared, level=self.level))

        # Reset animation state and spawn next
        self.clearing_rows = []
        self.clearing = False
        self.clear_anim_timer = 0.0
        self.spawn_piece()

    def handle_event(self, event: pygame.event.Event) -> None:
        # Handle Game Over overlay clicks only
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
        # Block input while clearing animation runs
        if self.clearing:
            return
        # key handling (WASD/Arrow Keys+ Space hard drop)
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
        # Track time played
        self.time_played += dt
        # Drive line clear animation
        if self.clearing:
            self.clear_anim_timer += dt
            if self.clear_anim_timer >= self.clear_anim_duration:
                self.perform_line_clear()
            return
        # ...existing gravity/drop and lock logic...
        drop_interval = self.gravity / (self.rules["fast_drop_multiplier"] if self.soft_drop else 1)
        self.drop_timer += dt
        if self.drop_timer >= drop_interval:
            self.drop_timer = 0.0
            if self.can_move(0, 1):
                self.piece_pos[1] += 1
            else:
                self.lock_piece()

    def draw(self) -> None:
        # Board
        cell = self.cell
        ox, oy = self.offset_x, self.offset_y
        for y, row in enumerate(self.grid):
            for x, value in enumerate(row):
                if value == 0:
                    base_color = (30, 30, 50)
                else:
                    base_color = value  # value is the stored color tuple
                pygame.draw.rect(
                    self.screen, base_color,
                    pygame.Rect(ox + x * cell, oy + y * cell, cell - 1, cell - 1),
                )

        # Line clear effect overlay (flash affected rows)
        if self.clearing and self.clearing_rows:
            # Progress 0..1
            p = max(0.0, min(1.0, self.clear_anim_timer / self.clear_anim_duration))
            # Fade from bright to dim
            alpha = int(200 * (1.0 - p))
            overlay_color = (255, 255, 255, alpha)
            for y in self.clearing_rows:
                row_rect = pygame.Rect(ox, oy + y * cell, self.grid_width * cell, cell - 1)
                s = pygame.Surface((row_rect.width, row_rect.height), pygame.SRCALPHA)
                s.fill(overlay_color)
                self.screen.blit(s, row_rect.topleft)

        # Current piece (use shape's color) — not drawn during clearing
        if self.current_piece and self.current_shape_key:
            color = SHAPE_COLORS.get(self.current_shape_key, (200, 120, 255))
            for x, y in self.current_piece:
                px = ox + (self.piece_pos[0] + x) * cell
                py = oy + (self.piece_pos[1] + y) * cell
                pygame.draw.rect(self.screen, color, pygame.Rect(px, py, cell - 1, cell - 1))

        # HUD: next + score + level
        self.draw_hud()
        # Game Over overlay
        if self.game_over:
            self.draw_game_over_overlay()

    def draw_hud(self) -> None:
        # Panel at right of board
        cell = self.cell
        ox, oy = self.offset_x, self.offset_y
        board_w = self.grid_width * cell
        panel_x = ox + board_w + 24
        panel_y = oy
        # Next box
        next_label = self.hud_font.render("Next", True, (255, 255, 255))
        self.screen.blit(next_label, (panel_x, panel_y))
        box = pygame.Rect(panel_x, panel_y + 28, 120, 100)
        pygame.draw.rect(self.screen, (35, 40, 80), box, border_radius=8)
        pygame.draw.rect(self.screen, (140, 150, 190), box, width=2, border_radius=8)
        # Draw next shape centered in box (use shape's color)
        if self.next_shape_key:
            pts = TETROMINOES[self.next_shape_key]
            color = SHAPE_COLORS.get(self.next_shape_key, (200, 120, 255))
            # normalize shape to start near (0,0)
            minx = min(x for x, _ in pts)
            miny = min(y for _, y in pts)
            norm = [(x - minx, y - miny) for x, y in pts]
            # center inside box
            base_x = box.x + (box.width - 4 * cell) // 2
            base_y = box.y + (box.height - 4 * cell) // 2
            for x, y in norm:
                rx = base_x + x * cell
                ry = base_y + y * cell
                pygame.draw.rect(self.screen, color, pygame.Rect(rx, ry, cell - 1, cell - 1))
        # Score, Level, Lines
        score_y = box.bottom + 20
        score_surf = self.hud_font.render(f"Score: {self.score}", True, (255, 255, 255))
        lvl_surf = self.hud_font.render(f"Level: {self.level}", True, (200, 220, 255))
        lines_surf = self.hud_font.render(f"Lines: {self.total_lines}", True, (200, 255, 220))
        self.screen.blit(score_surf, (panel_x, score_y))
        self.screen.blit(lvl_surf, (panel_x, score_y + 30))
        self.screen.blit(lines_surf, (panel_x, score_y + 60))

    # ----- Game Over Overlay -----
    def _calculate_final_score(self) -> None:
        # Calculate score breakdown with all bonuses
        # For now, login_streak and daily_streak are 0 (would come from database)
        self.score_breakdown = calculate_score_breakdown(
            base_score=self.score,
            difficulty=self.cfg.difficulty,
            levels=self.level,
            login_streak=0,  # TODO: fetch from database
            daily_streak=0,  # TODO: fetch from database
            time_played=int(self.time_played)
        )
        # Update score to final score for saving
        self.score = self.score_breakdown.final_score
    
    def build_go_buttons(self, start_y: int | None = None) -> None:
        self.go_button_rects.clear()
        labels = [("restart", "Restart"), ("back", "Back To Main Menu")]
        spacing = 64
        padding_x, padding_y = 22, 12
        button_width = 360
        # If no start_y provided, keep previous centered behavior
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
        # Dim background
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        title_font = pygame.font.SysFont("arial", 36)
        small = self.hud_font
        title = title_font.render("Game Over", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 200))

        # Stats with score breakdown
        stats = [f"Level: {self.level}", f"Lines: {self.total_lines}"]
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
        # Place the box below the title
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

        # Buttons positioned with a gap below the data box
        gap = 28
        self.build_go_buttons(start_y=data_box.bottom + gap)
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

    def hard_drop(self) -> None:
        # Instantly drop piece to the lowest valid position and lock it
        if self.game_over or self.clearing or not self.current_piece:
            return
        while self.can_move(0, 1):
            self.piece_pos[1] += 1
        self.lock_piece()
