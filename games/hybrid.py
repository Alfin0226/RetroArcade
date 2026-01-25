"""
Hybrid Mode 1: Snake + Pac-Man

Combines Pac-Man's maze-based movement with Snake-style collectibles.
The player navigates a Pac-Man maze collecting apples instead of pellets.
Ghosts behave normally with power-up mechanics intact.

Win condition: Collect all apples
Lose condition: Collision with a ghost (unless powered up)
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass
from typing import List, Tuple, Set
from collections import deque
import pygame
from . import BaseGame, register_game
from systems.rules import get_rules
from systems.ai import astar
from systems.scoring import ScoreBreakdown, calculate_score_breakdown

#Import pre-defined constants from original games
from .pac_man import (
    MAZE_COLOR, ENERGIZER_COLOR, FRIGHTENED_COLOR, GHOST_COLORS, RAW_MAP
)

# Hybrid-specific colors (Snake theme)
APPLE_COLOR = (255, 50, 50)
APPLE_STEM_COLOR = (139, 90, 43)
APPLE_LEAF_COLOR = (34, 139, 34)
PLAYER_COLOR = (50, 205, 50)  # Green snake-like player

Vec2 = Tuple[int, int]

@dataclass
class Ghost:
    idx: int
    pos: pygame.Vector2
    state: str = "caged"
    target: Vec2 = (0, 0)
    scatter_corner: Vec2 = (0, 0)
    step_accum: float = 0.0
    dot_counter: int = 0
    dot_limit: int = 0
    last_dir: Vec2 = (0, 0)
    reversed_this_fright: bool = False

@register_game("hybrid")
class HybridGame(BaseGame):
    """Snake + Pac-Man Hybrid: Collect apples in a maze while avoiding ghosts."""
    
    def __init__(self, screen: pygame.Surface, cfg, sounds, user_id=None):
        super().__init__(screen, cfg, sounds, user_id=user_id)
        (
            self.grid,
            self.apples,  # Renamed from pellets
            self.energizers,
            self.player_start,
            self.ghost_house_tiles,
            self.tunnels,
            self.house_spaces,
        ) = self._parse_map(RAW_MAP)
        self.h = len(self.grid)
        self.w = len(self.grid[0])
        
        # Player-blocked tiles (ghost house)
        self.player_block = set(self.ghost_house_tiles) | set(self.house_spaces)
        
        # Filter unreachable collectibles
        reachable = self._reachable_from(self.player_start, forbid=self.player_block)
        self.apples = {p for p in self.apples if p in reachable and p not in self.player_block}
        self.energizers = {e for e in self.energizers if e in reachable and e not in self.player_block}
        
        # Cell sizing
        usable_w = max(400, self.cfg.width - 160)
        usable_h = max(400, self.cfg.height - 160)
        self.cell = max(18, min(24, min(usable_w // self.w, usable_h // self.h)))
        self.offset = pygame.Vector2(
            (self.cfg.width - self.w * self.cell) // 2,
            (self.cfg.height - self.h * self.cell) // 2
        )
        
        # Player
        self.player = pygame.Vector2(*self.player_start)
        self.desired_dir: Vec2 = (0, 0)
        self.current_dir: Vec2 = (0, 0)
        self.player_speed = 10.0
        self.player_accum = 0.0
        self.ghost_speed = 9.0
        self.tunnel_speed_factor = 0.5
        
        # Release rules (Pinky timer, Inky/Clyde apple thresholds)
        self.release_elapsed = 0.0
        self.pinky_delay = 10.0
        self.inky_threshold = 30
        self.clyde_threshold = 60
        self.pinky_unlocked = False
        self.inky_unlocked = False
        self.clyde_unlocked = False
        
        # Ghost house and exit
        ghost_positions = self._ghost_start_positions()
        self.ghost_house = ghost_positions[0]
        self.ghost_exit = self._find_house_exit(self.ghost_house)
        
        # Ensure we have at least 4 positions for ghosts
        while len(ghost_positions) < 4:
            ghost_positions.append(ghost_positions[-1])
        
        # Initialize 4 ghosts
        self.ghosts: List[Ghost] = [
            Ghost(0, pygame.Vector2(self.ghost_exit[0], self.ghost_exit[1] - 1), "normal", scatter_corner=(self.w - 2, 1), dot_limit=0),
            Ghost(1, pygame.Vector2(*ghost_positions[0]), "caged", scatter_corner=(1, 1), dot_limit=0),
            Ghost(2, pygame.Vector2(*ghost_positions[1]), "caged", scatter_corner=(self.w - 2, self.h - 2), dot_limit=30),
            Ghost(3, pygame.Vector2(*ghost_positions[2]), "caged", scatter_corner=(1, self.h - 2), dot_limit=60),
        ]
        for g in self.ghosts:
            g.last_dir = (0, 0)
            g.reversed_this_fright = False
        
        # Mode system
        self.mode = "scatter"
        self.mode_timer = 0.0
        self.scatter_duration = 7.0
        self.chase_duration = 20.0
        self.frightened_timer = 0.0
        self.frightened_chain = 0
        
        # Game state
        self.level = 1
        self.lives = 3
        self.apples_total = len(self.apples) + len(self.energizers)
        self.apples_eaten = 0
        
        # UI
        self.font = pygame.font.SysFont("arial", 20)
        self.title_font = pygame.font.SysFont("arial", 32)
        self.hud_font = pygame.font.SysFont("arial", 28)
        self.game_over = False
        self.win = False
        self.go_button_rects: list[tuple[str, pygame.Rect]] = []
        self.level_time = 0.0
        self.completion_time = 0.0
        self.score_breakdown: ScoreBreakdown | None = None

        # Ghost release system
        self.global_timeout = 0.0
        self.global_timeout_limit = 4.0
        
        # Death animation
        self.death_animation = False
        self.death_timer = 0.0
        self.death_duration = 1.5
        
        # Pause system
        self.paused = False
        self.pause_button_rects: list[tuple[str, pygame.Rect]] = []

    def _parse_map(self, raw: str):
        lines = raw.splitlines()
        width = max(len(r) for r in lines)
        grid: List[List[int]] = []
        apples: Set[Vec2] = set()
        energizers: Set[Vec2] = set()
        tunnels: List[Vec2] = []
        ghost_tiles: Set[Vec2] = set()
        house_spaces: List[Vec2] = []
        player_start: Vec2 = (1, 1)
        center_x, center_y = width // 2, len(lines) // 2
        for y, row_text in enumerate(lines):
            row = []
            for x in range(width):
                ch = row_text[x] if x < len(row_text) else "#"
                if ch == "#":
                    row.append(1)
                else:
                    row.append(0)
                    if ch == ".":
                        apples.add((x, y))
                    elif ch == "o":
                        energizers.add((x, y))
                    elif ch == "P":
                        player_start = (x, y)
                    elif ch == "-":
                        ghost_tiles.add((x, y))
                    elif ch == "T":
                        tunnels.append((x, y))
                    elif ch == " " and abs(x - center_x) <= 2 and abs(y - center_y) <= 2:
                        house_spaces.append((x, y))
            grid.append(row)
        tunnels = tunnels[:2]
        if not house_spaces and ghost_tiles:
            house_spaces.extend(ghost_tiles)
        return grid, apples, energizers, player_start, ghost_tiles, tunnels, house_spaces

    def _reachable_from(self, start: Vec2, forbid: Set[Vec2] | None = None) -> Set[Vec2]:
        """BFS to find all tiles reachable from start."""
        if forbid is None:
            forbid = set()
        visited: Set[Vec2] = set()
        queue = deque([start])
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            x, y = node
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.w and 0 <= ny < self.h and self.grid[ny][nx] == 0:
                    if (nx, ny) not in visited and (nx, ny) not in forbid:
                        queue.append((nx, ny))
        return visited

    def _ghost_start_positions(self) -> List[Vec2]:
        positions = sorted(self.house_spaces, key=lambda p: (p[1], p[0]))
        if not positions:
            positions = [(self.w // 2, self.h // 2)]
        while len(positions) < 3:
            positions.append(positions[-1])
        return positions[:3]

    def _find_house_exit(self, house_pos: Vec2) -> Vec2:
        """Find the exit tile above the ghost house."""
        x, y = house_pos
        for dy in range(-3, 0):
            check_y = y + dy
            if 0 <= check_y < self.h and self.grid[check_y][x] == 0:
                if (x, check_y) not in self.house_spaces and (x, check_y) not in self.ghost_house_tiles:
                    return (x, check_y)
        return (x, max(0, y - 3))

    def _near_house(self) -> Vec2:
        """Find a tile near the ghost house for fruit spawning (not used in hybrid but kept for compatibility)."""
        if self.ghost_house:
            x, y = self.ghost_house
            for dy in range(1, 5):
                check_y = y + dy
                if 0 <= check_y < self.h and self.grid[check_y][x] == 0:
                    if (x, check_y) not in self.house_spaces:
                        return (x, check_y)
        return self.player_start

    def reset(self) -> None:
        super().reset()
        self._restart_level(full_reset=True)

    def _restart_level(self, full_reset: bool) -> None:
        if full_reset:
            self.level = 1
            self.score = 0
            self.lives = 3
            (
                self.grid,
                self.apples,
                self.energizers,
                self.player_start,
                self.ghost_house_tiles,
                self.tunnels,
                self.house_spaces,
            ) = self._parse_map(RAW_MAP)
            self.player_block = set(self.ghost_house_tiles) | set(self.house_spaces)
            reachable = self._reachable_from(self.player_start, forbid=self.player_block)
            self.apples = {p for p in self.apples if p in reachable and p not in self.player_block}
            self.energizers = {e for e in self.energizers if e in reachable and e not in self.player_block}
            self.apples_total = len(self.apples) + len(self.energizers)
            self.apples_eaten = 0
            self.level_time = 0.0
        
        self.player.update(*self.player_start)
        self.current_dir = (0, 0)
        self.desired_dir = (0, 0)
        self.player_accum = 0.0
        
        # Ensure 4 valid ghost positions
        ghost_positions = self._ghost_start_positions()
        while len(ghost_positions) < 4:
            ghost_positions.append(ghost_positions[-1])
        
        self.ghost_house = ghost_positions[0]
        self.ghost_exit = self._find_house_exit(self.ghost_house)
        
        self.ghosts = [
            Ghost(0, pygame.Vector2(self.ghost_exit[0], self.ghost_exit[1] - 1), "normal", scatter_corner=(self.w - 2, 1), dot_limit=0),
            Ghost(1, pygame.Vector2(*ghost_positions[0]), "caged", scatter_corner=(1, 1), dot_limit=0),
            Ghost(2, pygame.Vector2(*ghost_positions[1]), "caged", scatter_corner=(self.w - 2, self.h - 2), dot_limit=30),
            Ghost(3, pygame.Vector2(*ghost_positions[2]), "caged", scatter_corner=(1, self.h - 2), dot_limit=60),
        ]
        for g in self.ghosts:
            g.step_accum = 0.0
            g.dot_counter = 0
            g.last_dir = (0, 0)
            g.reversed_this_fright = False
        
        self.release_elapsed = 0.0
        self.pinky_unlocked = False
        self.inky_unlocked = False
        self.clyde_unlocked = False
        self.global_timeout = 0.0
        self.death_animation = False
        self.death_timer = 0.0
        self.mode = "scatter"
        self.mode_timer = 0.0
        self.frightened_timer = 0.0
        self.frightened_chain = 0
        self.game_over = False
        self.win = False
        self.go_button_rects.clear()
        self.score_breakdown = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.game_over or self.win:
            if not self.go_button_rects:
                self._build_go_buttons()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for key, rect in self.go_button_rects:
                    if rect.collidepoint(mx, my):
                        if key == "restart":
                            self._restart_level(full_reset=True)
                        else:
                            pygame.event.post(pygame.event.Event(pygame.USEREVENT, {"action": "back_to_menu"}))
                        break
            return

        # Pause toggle on ESC
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.paused = not self.paused
            return

        # Handle pause menu
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
                            self._restart_level(full_reset=True)
                            self.paused = False
                        elif key == "back":
                            pygame.event.post(pygame.event.Event(pygame.USEREVENT, {"action": "back_to_menu"}))
                        break
            return

        # Block input during death animation
        if self.death_animation:
            return

        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_LEFT, pygame.K_a):
            self.desired_dir = (-1, 0)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self.desired_dir = (1, 0)
        elif event.key in (pygame.K_UP, pygame.K_w):
            self.desired_dir = (0, -1)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.desired_dir = (0, 1)

    def update(self, dt: float) -> None:
        if self.game_over or self.win or self.paused:
            return

        # Death animation
        if self.death_animation:
            self.death_timer += dt
            if self.death_timer >= self.death_duration:
                self.death_animation = False
                self.death_timer = 0.0
                if self.lives <= 0:
                    self.game_over = True
                    self._calculate_final_score()
                    self.go_button_rects.clear()
                    self.save_score()
                else:
                    self._restart_level(full_reset=False)
            return

        self.level_time += dt
        self.release_elapsed += dt

        # Global timeout for ghost release
        self.global_timeout += dt
        if self.global_timeout >= self.global_timeout_limit:
            self._force_release_next_ghost()
            self.global_timeout = 0.0

        # Mode switching
        if self.frightened_timer > 0:
            self.frightened_timer = max(0.0, self.frightened_timer - dt)
            if self.frightened_timer == 0:
                self.frightened_chain = 0
                for g in self.ghosts:
                    if g.state == "frightened":
                        g.state = "normal"
                    g.reversed_this_fright = False
        else:
            self.mode_timer += dt
            if self.mode == "scatter" and self.mode_timer >= self.scatter_duration:
                self.mode = "chase"
                self.mode_timer = 0.0
            elif self.mode == "chase" and self.mode_timer >= self.chase_duration:
                self.mode = "scatter"
                self.mode_timer = 0.0

        # Speed
        pps = self.player_speed
        gps = self.ghost_speed

        # Step player
        step_time_p = 1.0 / pps
        self.player_accum += dt
        while self.player_accum >= step_time_p:
            self.player_accum -= step_time_p
            self._step_player()

        # Step ghosts
        for g in self.ghosts:
            if g.state == "eyes":
                eyes_speed = gps * 2.0
                step_time_g = 1.0 / eyes_speed
                g.step_accum += dt
                while g.step_accum >= step_time_g:
                    g.step_accum -= step_time_g
                    self._step_ghost_eyes(g)
                continue

            if g.state == "caged":
                if self._should_release(g):
                    path = self._ghost_astar((int(g.pos.x), int(g.pos.y)), self.ghost_exit)
                    if path:
                        if len(path) > 1:
                            next_pos = path[1]
                            g.last_dir = (next_pos[0] - int(g.pos.x), next_pos[1] - int(g.pos.y))
                            g.pos.update(*next_pos)
                        else:
                            g.pos.update(*path[0])
                        if tuple(map(int, (g.pos.x, g.pos.y))) == self.ghost_exit:
                            g.state = "normal"
                            g.reversed_this_fright = False
                    else:
                        exit_neighbors = self._neighbors((int(g.pos.x), int(g.pos.y)))
                        if self.ghost_exit in exit_neighbors:
                            g.pos.update(*self.ghost_exit)
                            g.state = "normal"
                            g.reversed_this_fright = False
                continue

            # Normal/frightened ghosts
            node = (int(g.pos.x), int(g.pos.y))
            factor = self.tunnel_speed_factor if node in self.tunnels else 1.0
            step_time_g = 1.0 / (gps * factor)
            g.step_accum += dt
            while g.step_accum >= step_time_g:
                g.step_accum -= step_time_g
                self._step_ghost(g)

        # Win condition: all apples collected
        if not self.apples and not self.energizers:
            self.win = True
            self.completion_time = self.level_time
            self._calculate_final_score()
            self.go_button_rects.clear()
            self.save_score()
            return

    def _step_player(self) -> None:
        if self._can_move(self.player, self.desired_dir, is_player=True):
            self.current_dir = self.desired_dir
        if self._can_move(self.player, self.current_dir, is_player=True):
            self.player += pygame.Vector2(self.current_dir)
            self.player.update(*self._apply_tunnel(self.player))

        pnode = (int(self.player.x), int(self.player.y))
        
        # Eating apples
        apple_eaten = False
        if pnode in self.apples:
            self.apples.remove(pnode)
            self.apples_eaten += 1
            self.score += 10
            apple_eaten = True
            self.sounds.play("eat")
        if pnode in self.energizers:
            self.energizers.remove(pnode)
            self.apples_eaten += 1
            self.score += 50
            self._trigger_frightened()
            apple_eaten = True
        if apple_eaten:
            self.global_timeout = 0.0

        # Collision with ghosts
        for g in self.ghosts:
            self._resolve_collision(g)

    def _step_ghost(self, g: Ghost) -> None:
        start = (int(g.pos.x), int(g.pos.y))

        if self.frightened_timer > 0:
            if not g.reversed_this_fright and g.last_dir != (0, 0):
                g.last_dir = (-g.last_dir[0], -g.last_dir[1])
                g.reversed_this_fright = True
            g.state = "frightened"
            nbs = self._neighbors(start)
            if nbs:
                chosen = random.choice(nbs)
                g.last_dir = (chosen[0] - start[0], chosen[1] - start[1])
                g.pos.update(*chosen)
        else:
            g.state = "normal"
            target = g.scatter_corner if self.mode == "scatter" else self._chase_target(g)
            path = self._ghost_astar(start, target)
            if path and len(path) > 1:
                next_pos = path[1]
                g.last_dir = (next_pos[0] - start[0], next_pos[1] - start[1])
                g.pos.update(*next_pos)
            else:
                nbs = self._neighbors(start)
                if nbs:
                    chosen = random.choice(nbs)
                    g.last_dir = (chosen[0] - start[0], chosen[1] - start[1])
                    g.pos.update(*chosen)
            g.reversed_this_fright = False

        new_node = (int(g.pos.x), int(g.pos.y))
        if new_node in self.tunnels:
            g.pos.update(*self._apply_tunnel(g.pos))
        self._resolve_collision(g)

    def _step_ghost_eyes(self, g: Ghost) -> None:
        """Eyes return to house."""
        start = (int(g.pos.x), int(g.pos.y))
        path = self._ghost_astar_eyes(start, self.ghost_house)
        if path and len(path) > 1:
            next_pos = path[1]
            g.last_dir = (next_pos[0] - start[0], next_pos[1] - start[1])
            g.pos.update(*next_pos)
        if tuple(map(int, (g.pos.x, g.pos.y))) == self.ghost_house:
            g.state = "normal"
            g.reversed_this_fright = False

    def _neighbors(self, node: Vec2) -> List[Vec2]:
        x, y = node
        out = []
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.w and 0 <= ny < self.h and self.grid[ny][nx] == 0:
                if (nx, ny) not in self.house_spaces:
                    out.append((nx, ny))
        return out

    def _ghost_astar(self, start: Vec2, goal: Vec2) -> List[Vec2] | None:
        temp_grid = [row[:] for row in self.grid]
        for tx, ty in self.tunnels:
            if 0 <= ty < len(temp_grid) and 0 <= tx < len(temp_grid[0]):
                temp_grid[ty][tx] = 1
        for hx, hy in self.house_spaces:
            if (hx, hy) not in (start, goal) and 0 <= hy < len(temp_grid) and 0 <= hx < len(temp_grid[0]):
                temp_grid[hy][hx] = 1
        return astar(start, goal, temp_grid)

    def _ghost_astar_eyes(self, start: Vec2, goal: Vec2) -> List[Vec2] | None:
        temp_grid = [row[:] for row in self.grid]
        for tx, ty in self.tunnels:
            if 0 <= ty < len(temp_grid) and 0 <= tx < len(temp_grid[0]):
                temp_grid[ty][tx] = 1
        return astar(start, goal, temp_grid)

    def _should_release(self, g: Ghost) -> bool:
        if g.idx == 0:
            return True
        if g.idx == 1:
            if not self.pinky_unlocked and self.release_elapsed >= self.pinky_delay:
                self.pinky_unlocked = True
            return self.pinky_unlocked
        if g.idx == 2:
            if not self.pinky_unlocked:
                return False
            if not self.inky_unlocked and self.apples_eaten >= self.inky_threshold:
                self.inky_unlocked = True
            return self.inky_unlocked
        if g.idx == 3:
            if not self.inky_unlocked:
                return False
            if not self.clyde_unlocked and self.apples_eaten >= self.clyde_threshold:
                self.clyde_unlocked = True
            return self.clyde_unlocked
        return False

    def _force_release_next_ghost(self) -> None:
        for idx in (1, 2, 3):
            g = self.ghosts[idx]
            if g.state == "caged":
                if idx == 1:
                    self.pinky_unlocked = True
                    self.release_elapsed = self.pinky_delay
                    break
                elif idx == 2:
                    if self.apples_eaten >= self.inky_threshold:
                        self.inky_unlocked = True
                        break
                elif idx == 3:
                    if self.apples_eaten >= self.clyde_threshold:
                        self.clyde_unlocked = True
                        break

    def _resolve_collision(self, g: Ghost) -> None:
        pnode = (int(self.player.x), int(self.player.y))
        gnode = (int(g.pos.x), int(g.pos.y))
        if pnode != gnode:
            return
        
        if self.frightened_timer > 0 and g.state == "frightened":
            points = [200, 400, 800, 1600][min(self.frightened_chain, 3)]
            self.score += points
            self.frightened_chain += 1
            g.state = "eyes"
            self.sounds.play("power_up")
        elif g.state not in ("eyes", "caged"):
            self.lives -= 1
            self.death_animation = True
            self.death_timer = 0.0

    def _trigger_frightened(self) -> None:
        duration = 6.0
        self.frightened_timer = duration
        self.frightened_chain = 0
        for g in self.ghosts:
            g.reversed_this_fright = False
        self.sounds.play("power_up")

    def _can_move(self, pos: pygame.Vector2, d: Vec2, is_player: bool = False) -> bool:
        if d == (0, 0):
            return False
        nx = int(pos.x + d[0])
        ny = int(pos.y + d[1])
        if not (0 <= nx < self.w and 0 <= ny < self.h):
            return False
        if self.grid[ny][nx] != 0:
            return False
        if is_player and (nx, ny) in self.player_block:
            return False
        return True

    def _apply_tunnel(self, pos: pygame.Vector2) -> Vec2:
        node = (int(pos.x), int(pos.y))
        if len(self.tunnels) == 2:
            if node == self.tunnels[0]:
                return self.tunnels[1]
            if node == self.tunnels[1]:
                return self.tunnels[0]
        return node

    def _chase_target(self, g: Ghost) -> Vec2:
        p = (int(self.player.x), int(self.player.y))
        d = self.current_dir
        
        if g.idx == 0:
            return p
        elif g.idx == 1:
            return (
                max(0, min(self.w - 1, p[0] + 4 * d[0])),
                max(0, min(self.h - 1, p[1] + 4 * d[1]))
            )
        elif g.idx == 2:
            two_ahead = (
                max(0, min(self.w - 1, p[0] + 2 * d[0])),
                max(0, min(self.h - 1, p[1] + 2 * d[1]))
            )
            red = next((gh for gh in self.ghosts if gh.idx == 0), self.ghosts[0])
            vec = (two_ahead[0] - int(red.pos.x), two_ahead[1] - int(red.pos.y))
            return (
                max(0, min(self.w - 1, int(red.pos.x) + 2 * vec[0])),
                max(0, min(self.h - 1, int(red.pos.y) + 2 * vec[1]))
            )
        else:
            dist = abs(int(g.pos.x) - p[0]) + abs(int(g.pos.y) - p[1])
            return p if dist > 8 else g.scatter_corner

    # ==================== DRAWING ====================

    def draw(self) -> None:
        self._draw_maze()
        self._draw_collectibles()
        
        if not self.death_animation:
            self._draw_player()
        else:
            self._draw_player_death()
        
        self._draw_ghosts()
        self._draw_hud()
        
        if self.paused:
            self._draw_pause_menu()
        elif self.game_over:
            self._draw_game_over()
        elif self.win:
            self._draw_win()

    def _draw_maze(self) -> None:
        ox, oy = int(self.offset.x), int(self.offset.y)
        for y, row in enumerate(self.grid):
            for x, cell in enumerate(row):
                if cell == 1:
                    pygame.draw.rect(
                        self.screen, MAZE_COLOR,
                        pygame.Rect(ox + x * self.cell, oy + y * self.cell, self.cell - 1, self.cell - 1),
                        border_radius=4
                    )

    def _draw_collectibles(self) -> None:
        ox, oy = int(self.offset.x), int(self.offset.y)
        
        # Draw apples (instead of pellets)
        for x, y in self.apples:
            cx = ox + x * self.cell + self.cell // 2
            cy = oy + y * self.cell + self.cell // 2
            self._draw_apple(cx, cy, 5)
        
        # Draw energizers (power-ups)
        for x, y in self.energizers:
            cx = ox + x * self.cell + self.cell // 2
            cy = oy + y * self.cell + self.cell // 2
            r = 7 if (pygame.time.get_ticks() // 250) % 2 == 0 else 5
            pygame.draw.circle(self.screen, ENERGIZER_COLOR, (cx, cy), r)

    def _draw_apple(self, cx: int, cy: int, size: int) -> None:
        """Draw a simple apple sprite."""
        # Apple body
        pygame.draw.circle(self.screen, APPLE_COLOR, (cx, cy), size)
        # Stem
        pygame.draw.line(self.screen, APPLE_STEM_COLOR, (cx, cy - size), (cx + 1, cy - size - 3), 2)
        # Leaf
        if size >= 4:
            pygame.draw.ellipse(self.screen, APPLE_LEAF_COLOR, 
                              pygame.Rect(cx + 1, cy - size - 4, 4, 3))

    def _draw_player(self) -> None:
        """Draw snake-style player (green square head)."""
        ox, oy = int(self.offset.x), int(self.offset.y)
        x, y = int(self.player.x), int(self.player.y)
        r = pygame.Rect(ox + x * self.cell + 2, oy + y * self.cell + 2, self.cell - 4, self.cell - 4)
        
        # Snake head (green rounded square)
        pygame.draw.rect(self.screen, PLAYER_COLOR, r, border_radius=4)
        
        # Eyes based on direction
        eye_size = 3
        eye_offset = 4
        if self.current_dir == (1, 0):  # Right
            pygame.draw.circle(self.screen, (255, 255, 255), (r.right - eye_offset, r.centery - 3), eye_size)
            pygame.draw.circle(self.screen, (255, 255, 255), (r.right - eye_offset, r.centery + 3), eye_size)
            pygame.draw.circle(self.screen, (0, 0, 0), (r.right - eye_offset + 1, r.centery - 3), 1)
            pygame.draw.circle(self.screen, (0, 0, 0), (r.right - eye_offset + 1, r.centery + 3), 1)
        elif self.current_dir == (-1, 0):  # Left
            pygame.draw.circle(self.screen, (255, 255, 255), (r.left + eye_offset, r.centery - 3), eye_size)
            pygame.draw.circle(self.screen, (255, 255, 255), (r.left + eye_offset, r.centery + 3), eye_size)
            pygame.draw.circle(self.screen, (0, 0, 0), (r.left + eye_offset - 1, r.centery - 3), 1)
            pygame.draw.circle(self.screen, (0, 0, 0), (r.left + eye_offset - 1, r.centery + 3), 1)
        elif self.current_dir == (0, -1):  # Up
            pygame.draw.circle(self.screen, (255, 255, 255), (r.centerx - 3, r.top + eye_offset), eye_size)
            pygame.draw.circle(self.screen, (255, 255, 255), (r.centerx + 3, r.top + eye_offset), eye_size)
            pygame.draw.circle(self.screen, (0, 0, 0), (r.centerx - 3, r.top + eye_offset - 1), 1)
            pygame.draw.circle(self.screen, (0, 0, 0), (r.centerx + 3, r.top + eye_offset - 1), 1)
        elif self.current_dir == (0, 1):  # Down
            pygame.draw.circle(self.screen, (255, 255, 255), (r.centerx - 3, r.bottom - eye_offset), eye_size)
            pygame.draw.circle(self.screen, (255, 255, 255), (r.centerx + 3, r.bottom - eye_offset), eye_size)
            pygame.draw.circle(self.screen, (0, 0, 0), (r.centerx - 3, r.bottom - eye_offset + 1), 1)
            pygame.draw.circle(self.screen, (0, 0, 0), (r.centerx + 3, r.bottom - eye_offset + 1), 1)
        else:  # Stationary - face forward
            pygame.draw.circle(self.screen, (255, 255, 255), (r.centerx - 3, r.centery - 2), eye_size)
            pygame.draw.circle(self.screen, (255, 255, 255), (r.centerx + 3, r.centery - 2), eye_size)
            pygame.draw.circle(self.screen, (0, 0, 0), (r.centerx - 3, r.centery - 2), 1)
            pygame.draw.circle(self.screen, (0, 0, 0), (r.centerx + 3, r.centery - 2), 1)

    def _draw_player_death(self) -> None:
        ox, oy = int(self.offset.x), int(self.offset.y)
        x, y = int(self.player.x), int(self.player.y)
        cx = ox + x * self.cell + self.cell // 2
        cy = oy + y * self.cell + self.cell // 2
        progress = self.death_timer / self.death_duration
        radius = int((self.cell // 2) * (1.0 - progress))
        if radius > 0:
            pygame.draw.circle(self.screen, PLAYER_COLOR, (cx, cy), radius)

    def _draw_ghosts(self) -> None:
        ox, oy = int(self.offset.x), int(self.offset.y)
        for g in self.ghosts:
            x, y = int(g.pos.x), int(g.pos.y)
            rect = pygame.Rect(ox + x * self.cell, oy + y * self.cell, self.cell - 2, self.cell - 2)
            
            if g.state == "eyes":
                self._draw_eyes(rect)
                continue
            
            color = FRIGHTENED_COLOR if g.state == "frightened" else GHOST_COLORS[g.idx]
            
            # Ghost body
            pygame.draw.rect(self.screen, color, 
                           pygame.Rect(rect.x, rect.y + rect.height // 3, rect.width, rect.height * 2 // 3))
            pygame.draw.circle(self.screen, color, (rect.centerx, rect.y + rect.height // 3), rect.width // 2)
            
            # Wavy bottom
            wave_count = 3
            wave_width = rect.width // wave_count
            for i in range(wave_count):
                pygame.draw.circle(self.screen, color, 
                                 (rect.x + wave_width // 2 + i * wave_width, rect.bottom), wave_width // 2)
            
            # Eyes
            if g.state != "frightened":
                eye_y = rect.y + rect.height // 3
                pygame.draw.circle(self.screen, (255, 255, 255), (rect.centerx - 4, eye_y), 4)
                pygame.draw.circle(self.screen, (255, 255, 255), (rect.centerx + 4, eye_y), 4)
                pygame.draw.circle(self.screen, (0, 0, 255), (rect.centerx - 4, eye_y), 2)
                pygame.draw.circle(self.screen, (0, 0, 255), (rect.centerx + 4, eye_y), 2)
            else:
                # Frightened face
                eye_y = rect.y + rect.height // 3
                pygame.draw.circle(self.screen, (255, 255, 255), (rect.centerx - 4, eye_y), 3)
                pygame.draw.circle(self.screen, (255, 255, 255), (rect.centerx + 4, eye_y), 3)

    def _draw_eyes(self, rect: pygame.Rect) -> None:
        """Draw just eyes for returning ghost."""
        eye_y = rect.centery
        pygame.draw.circle(self.screen, (255, 255, 255), (rect.centerx - 5, eye_y), 5)
        pygame.draw.circle(self.screen, (255, 255, 255), (rect.centerx + 5, eye_y), 5)
        pygame.draw.circle(self.screen, (0, 0, 255), (rect.centerx - 5, eye_y), 2)
        pygame.draw.circle(self.screen, (0, 0, 255), (rect.centerx + 5, eye_y), 2)

    def _draw_hud(self) -> None:
        ox = int(self.offset.x)
        
        # Draw apple icon and count
        apple_icon_x = 10
        apple_icon_y = 12
        self._draw_apple(apple_icon_x + 8, apple_icon_y + 8, 8)
        apples_left = len(self.apples) + len(self.energizers)
        apple_text = self.font.render(f"x {apples_left}", True, (255, 255, 255))
        self.screen.blit(apple_text, (apple_icon_x + 22, apple_icon_y))
        
        # Score
        score_text = self.font.render(f"SCORE: {self.score}", True, (255, 255, 255))
        self.screen.blit(score_text, (self.cfg.width // 2 - score_text.get_width() // 2, 10))
        
        # Lives
        lives_text = self.font.render(f"LIVES: {self.lives}", True, (255, 255, 255))
        self.screen.blit(lives_text, (self.cfg.width - lives_text.get_width() - 10, 10))
        
        # Mode title
        mode_text = self.font.render("SNAKE + PAC-MAN", True, (50, 205, 50))
        self.screen.blit(mode_text, (self.cfg.width // 2 - mode_text.get_width() // 2, self.cfg.height - 30))

    def _build_go_buttons(self) -> None:
        self.go_button_rects.clear()
        labels = [("restart", "Play Again"), ("back", "Back To Menu")]
        spacing, padding_x, padding_y, button_width = 50, 20, 10, 340
        for i, (key, text) in enumerate(labels):
            surf = self.font.render(text, True, (255, 255, 255))
            w = max(button_width, surf.get_width() + padding_x * 2)
            h = surf.get_height() + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            self.go_button_rects.append((key, pygame.Rect(x, 0, w, h)))

    def _build_pause_buttons(self) -> None:
        self.pause_button_rects.clear()
        labels = [("resume", "Resume"), ("restart", "Restart"), ("back", "Back To Menu")]
        spacing, padding_x, padding_y, button_width = 50, 20, 10, 300
        total_h = len(labels) * spacing
        start_y = self.cfg.height // 2 - total_h // 2 + 40
        for i, (key, text) in enumerate(labels):
            surf = self.font.render(text, True, (255, 255, 255))
            w = max(button_width, surf.get_width() + padding_x * 2)
            h = surf.get_height() + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            y = start_y + i * spacing
            self.pause_button_rects.append((key, pygame.Rect(x, y, w, h)))

    def _draw_pause_menu(self) -> None:
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        title = self.title_font.render("PAUSED", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 100))
        
        if not self.pause_button_rects:
            self._build_pause_buttons()
        
        mouse = pygame.mouse.get_pos()
        for key, rect in self.pause_button_rects:
            hovered = rect.collidepoint(*mouse)
            fill = (70, 80, 120) if hovered else (40, 45, 85)
            border = (255, 255, 255) if hovered else (140, 150, 190)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=8)
            label = {"resume": "Resume", "restart": "Restart", "back": "Back To Menu"}[key]
            ts = self.font.render(label, True, (255, 255, 255))
            self.screen.blit(ts, (rect.x + (rect.width - ts.get_width()) // 2, rect.y + (rect.height - ts.get_height()) // 2))

    def _calculate_final_score(self) -> None:
        login_streak, daily_streak = self.get_user_streaks()
        self.score_breakdown = calculate_score_breakdown(
            base_score=self.score,
            difficulty=self.cfg.difficulty,
            levels=self.level,
            login_streak=login_streak,
            daily_streak=daily_streak,
            time_played=int(self.level_time)
        )
        self.score = self.score_breakdown.final_score

    def _draw_game_over(self) -> None:
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        title = self.title_font.render("Game Over", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 200))
        
        # Score breakdown
        stats = [f"Apples Eaten: {self.apples_eaten}"]
        if self.score_breakdown:
            stats.extend(self.score_breakdown.as_display_lines())
        else:
            stats.append(f"Score: {self.score}")
        
        stat_surfs = [self.font.render(s, True, (220, 220, 240)) for s in stats]
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
        
        # Buttons
        gap = 28
        self.go_button_rects.clear()
        labels = [("restart", "Play Again"), ("back", "Back To Menu")]
        spacing, padding_x, padding_y, button_width = 50, 20, 10, 340
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
            label = "Play Again" if key == "restart" else "Back To Menu"
            ts = self.font.render(label, True, (255, 255, 255))
            self.screen.blit(ts, (rect.x + (rect.width - ts.get_width()) // 2, rect.y + (rect.height - ts.get_height()) // 2))

    def _draw_win(self) -> None:
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        title = self.title_font.render("Level Complete!", True, (50, 255, 50))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 200))
        
        # Time and score
        minutes = int(self.completion_time // 60)
        seconds = int(self.completion_time % 60)
        
        stats = [
            f"Time: {minutes}:{seconds:02d}",
            f"Apples Collected: {self.apples_eaten}",
        ]
        if self.score_breakdown:
            stats.extend(self.score_breakdown.as_display_lines())
        else:
            stats.append(f"Score: {self.score}")
        
        stat_surfs = [self.font.render(s, True, (220, 220, 240)) for s in stats]
        if self.score_breakdown and len(stat_surfs) > 0:
            stat_surfs[-1] = self.font.render(stats[-1], True, (255, 255, 100))
        
        pad_x, pad_y = 16, 14
        line_spacing = 6
        content_w = max(s.get_width() for s in stat_surfs)
        content_h = sum(s.get_height() for s in stat_surfs) + line_spacing * (len(stat_surfs) - 1)
        box_w = max(320, content_w + pad_x * 2)
        box_h = content_h + pad_y * 2
        box = pygame.Rect(self.cfg.width // 2 - box_w // 2, self.cfg.height // 2 - 120, box_w, box_h)
        pygame.draw.rect(self.screen, (35, 60, 40), box, border_radius=10)
        pygame.draw.rect(self.screen, (100, 200, 100), box, 2, border_radius=10)
        
        y = box.y + pad_y
        for s in stat_surfs:
            self.screen.blit(s, (box.x + pad_x, y))
            y += s.get_height() + line_spacing
        
        # Buttons
        gap = 28
        self.go_button_rects.clear()
        labels = [("restart", "Play Again"), ("back", "Back To Menu")]
        spacing, padding_x, padding_y, button_width = 50, 20, 10, 340
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
            fill = (70, 100, 80) if hovered else (40, 65, 55)
            border = (255, 255, 255) if hovered else (140, 190, 150)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=8)
            label = "Play Again" if key == "restart" else "Back To Menu"
            ts = self.font.render(label, True, (255, 255, 255))
            self.screen.blit(ts, (rect.x + (rect.width - ts.get_width()) // 2, rect.y + (rect.height - ts.get_height()) // 2))
