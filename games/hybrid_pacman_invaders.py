"""
Hybrid Mode 3: Pac-Man + Space Invaders
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

# Import pre-defined constants from original games
from .pac_man import (
    MAZE_COLOR, PELLET_COLOR, ENERGIZER_COLOR, PLAYER_COLOR, 
    FRIGHTENED_COLOR, FRUIT_TABLE, RAW_MAP
)
from .space_invaders import ENEMY_PATTERNS

# Hybrid-specific: Space Invader colors for the 4 "ghosts"
INVADER_COLORS = [
    (255, 80, 80),    # Red Invader (was Blinky)
    (255, 80, 255),   # Magenta Invader (was Pinky)
    (80, 255, 255),   # Cyan Invader (was Inky)
    (255, 165, 80),   # Orange Invader (was Clyde)
]

# Use first 4 patterns from space_invaders for the 4 invader enemies
INVADER_PATTERNS = ENEMY_PATTERNS[:4]

# Hybrid-specific: Frightened invader pattern (same for all when vulnerable)
FRIGHTENED_PATTERN = [
    [0,1,1,1,1,1,1,1,1,0],
    [1,1,1,1,1,1,1,1,1,1],
    [1,1,0,1,1,1,1,0,1,1],
    [1,1,1,1,1,1,1,1,1,1],
    [1,0,1,0,1,1,0,1,0,1],
    [1,1,0,1,0,0,1,0,1,1],
    [0,1,1,1,1,1,1,1,1,0],
    [0,0,1,0,0,0,0,1,0,0],
]

Vec2 = Tuple[int, int]

@dataclass
class Invader:
    """Space Invader enemy (replaces Ghost visually, same AI behavior)."""
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


@register_game("hybrid_pacman_invaders")
class HybridPacManInvadersGame(BaseGame):
    
    def __init__(self, screen: pygame.Surface, cfg, sounds, user_id=None):
        super().__init__(screen, cfg, sounds, user_id=user_id)
        self.name = "hybrid_pacman_invaders"
        (
            self.grid,
            self.pellets,
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
        self.pellets = {p for p in self.pellets if p in reachable and p not in self.player_block}
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
        
        # Release rules
        self.release_elapsed = 0.0
        self.pinky_delay = 10.0
        self.inky_threshold = 30
        self.clyde_threshold = 60
        self.pinky_unlocked = False
        self.inky_unlocked = False
        self.clyde_unlocked = False
        
        # Ghost/Invader house
        ghost_positions = self._ghost_start_positions()
        self.ghost_house = ghost_positions[0]
        self.ghost_exit = self._find_house_exit(self.ghost_house)
        
        while len(ghost_positions) < 4:
            ghost_positions.append(ghost_positions[-1])
        
        # Initialize 4 Invaders (replacing ghosts)
        self.invaders: List[Invader] = [
            Invader(0, pygame.Vector2(self.ghost_exit[0], self.ghost_exit[1] - 1), "normal", scatter_corner=(self.w - 2, 1), dot_limit=0),
            Invader(1, pygame.Vector2(*ghost_positions[0]), "caged", scatter_corner=(1, 1), dot_limit=0),
            Invader(2, pygame.Vector2(*ghost_positions[1]), "caged", scatter_corner=(self.w - 2, self.h - 2), dot_limit=30),
            Invader(3, pygame.Vector2(*ghost_positions[2]), "caged", scatter_corner=(1, self.h - 2), dot_limit=60),
        ]
        for inv in self.invaders:
            inv.last_dir = (0, 0)
            inv.reversed_this_fright = False
        
        # Mode system (unchanged from Pac-Man)
        self.mode = "scatter"
        self.mode_timer = 0.0
        self.scatter_duration = 7.0
        self.chase_duration = 20.0
        self.frightened_timer = 0.0
        self.frightened_chain = 0
        
        # Cruise Elroy (unchanged)
        self.cruise_elroy_stage = 0
        self.elroy_thresholds = [(20, 1.05), (10, 1.1)]
        
        # Game state
        self.level = 1
        self.lives = 3
        self.pellets_total = len(self.pellets) + len(self.energizers)
        self.pellets_eaten = 0
        
        # Fruit
        self.fruit_active = False
        self.fruit_timer = 0.0
        self.fruit_pos = self._near_house()
        self.fruit_spawns_left = 2
        self.fruit_name = "Cherry"
        self.fruit_level_pts = 100
        
        # UI
        self.font = pygame.font.SysFont("arial", 20)
        self.title_font = pygame.font.SysFont("arial", 32)
        self.hud_font = pygame.font.SysFont("arial", 28)
        self.game_over = False
        self.win = False
        self.go_button_rects: list[tuple[str, pygame.Rect]] = []
        self.level_time = 0.0
        self.score_breakdown: ScoreBreakdown | None = None
        
        # Ghost release
        self.global_timeout = 0.0
        self.global_timeout_limit = 4.0
        
        # Death animation
        self.death_animation = False
        self.death_timer = 0.0
        self.death_duration = 1.5
        
        # Pause
        self.paused = False
        self.pause_button_rects: list[tuple[str, pygame.Rect]] = []
        
        # Animation timer for invaders
        self.invader_anim_timer = 0.0

    def _parse_map(self, raw: str):
        lines = raw.splitlines()
        width = max(len(r) for r in lines)
        grid: List[List[int]] = []
        pellets: Set[Vec2] = set()
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
                        pellets.add((x, y))
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
        return grid, pellets, energizers, player_start, ghost_tiles, tunnels, house_spaces

    def _reachable_from(self, start: Vec2, forbid: Set[Vec2] | None = None) -> Set[Vec2]:
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
        x, y = house_pos
        for dy in range(-3, 0):
            check_y = y + dy
            if 0 <= check_y < self.h and self.grid[check_y][x] == 0:
                if (x, check_y) not in self.house_spaces and (x, check_y) not in self.ghost_house_tiles:
                    return (x, check_y)
        return (x, max(0, y - 3))

    def _near_house(self) -> Vec2:
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
                self.pellets,
                self.energizers,
                self.player_start,
                self.ghost_house_tiles,
                self.tunnels,
                self.house_spaces,
            ) = self._parse_map(RAW_MAP)
            self.player_block = set(self.ghost_house_tiles) | set(self.house_spaces)
            reachable = self._reachable_from(self.player_start, forbid=self.player_block)
            self.pellets = {p for p in self.pellets if p in reachable and p not in self.player_block}
            self.energizers = {e for e in self.energizers if e in reachable and e not in self.player_block}
            self.pellets_total = len(self.pellets) + len(self.energizers)
            self.pellets_eaten = 0
            self.fruit_spawns_left = 2
            self.level_time = 0.0
        
        self.player.update(*self.player_start)
        self.current_dir = (0, 0)
        self.desired_dir = (0, 0)
        self.player_accum = 0.0
        
        ghost_positions = self._ghost_start_positions()
        while len(ghost_positions) < 4:
            ghost_positions.append(ghost_positions[-1])
        
        self.ghost_house = ghost_positions[0]
        self.ghost_exit = self._find_house_exit(self.ghost_house)
        
        self.invaders = [
            Invader(0, pygame.Vector2(self.ghost_exit[0], self.ghost_exit[1] - 1), "normal", scatter_corner=(self.w - 2, 1), dot_limit=0),
            Invader(1, pygame.Vector2(*ghost_positions[0]), "caged", scatter_corner=(1, 1), dot_limit=0),
            Invader(2, pygame.Vector2(*ghost_positions[1]), "caged", scatter_corner=(self.w - 2, self.h - 2), dot_limit=30),
            Invader(3, pygame.Vector2(*ghost_positions[2]), "caged", scatter_corner=(1, self.h - 2), dot_limit=60),
        ]
        for inv in self.invaders:
            inv.step_accum = 0.0
            inv.dot_counter = 0
            inv.last_dir = (0, 0)
            inv.reversed_this_fright = False
        
        self.release_elapsed = 0.0
        self.pinky_unlocked = False
        self.inky_unlocked = False
        self.clyde_unlocked = False
        self.global_timeout = 0.0
        self.cruise_elroy_stage = 0
        self.death_animation = False
        self.death_timer = 0.0
        self.mode = "scatter"
        self.mode_timer = 0.0
        self.frightened_timer = 0.0
        self.frightened_chain = 0
        self.fruit_active = False
        self.fruit_timer = 0.0
        self.game_over = False
        self.win = False
        self.go_button_rects.clear()
        self.score_breakdown = None
        self.invader_anim_timer = 0.0

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
                            self._restart_level(full_reset=True)
                            self.paused = False
                        elif key == "back":
                            pygame.event.post(pygame.event.Event(pygame.USEREVENT, {"action": "back_to_menu"}))
                        break
            return
        
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
        self.invader_anim_timer += dt
        
        # Global timeout for invader release
        self.global_timeout += dt
        if self.global_timeout >= self.global_timeout_limit:
            self._force_release_next_invader()
            self.global_timeout = 0.0
        
        # Mode switching (unchanged)
        if self.frightened_timer > 0:
            self.frightened_timer = max(0.0, self.frightened_timer - dt)
            if self.frightened_timer == 0:
                self.frightened_chain = 0
                for inv in self.invaders:
                    if inv.state == "frightened":
                        inv.state = "normal"
                    inv.reversed_this_fright = False
        else:
            self.mode_timer += dt
            if self.mode == "scatter" and self.mode_timer >= self.scatter_duration:
                self.mode = "chase"
                self.mode_timer = 0.0
            elif self.mode == "chase" and self.mode_timer >= self.chase_duration:
                self.mode = "scatter"
                self.mode_timer = 0.0
        
        # Cruise Elroy
        remaining = len(self.pellets) + len(self.energizers)
        for thresh, _ in self.elroy_thresholds:
            if remaining <= thresh:
                self.cruise_elroy_stage = max(self.cruise_elroy_stage, self.elroy_thresholds.index((thresh, _)) + 1)
        
        # Fruit spawning
        if self.fruit_active:
            self.fruit_timer -= dt
            if self.fruit_timer <= 0:
                self.fruit_active = False
        elif self.fruit_spawns_left > 0 and self.pellets_eaten in (70, 170):
            self._spawn_fruit()
        
        # Speed
        pps = self.player_speed
        gps = self.ghost_speed
        if self.cruise_elroy_stage > 0:
            gps *= self.elroy_thresholds[self.cruise_elroy_stage - 1][1]
        
        # Step player
        step_time_p = 1.0 / pps
        self.player_accum += dt
        while self.player_accum >= step_time_p:
            self.player_accum -= step_time_p
            self._step_player()
        
        # Step invaders (same as ghost AI)
        for inv in self.invaders:
            if inv.state == "eyes":
                eyes_speed = gps * 2.0
                step_time_g = 1.0 / eyes_speed
                inv.step_accum += dt
                while inv.step_accum >= step_time_g:
                    inv.step_accum -= step_time_g
                    self._step_invader_eyes(inv)
                continue
            
            if inv.state == "caged":
                if self._should_release(inv):
                    path = self._ghost_astar((int(inv.pos.x), int(inv.pos.y)), self.ghost_exit)
                    if path:
                        if len(path) > 1:
                            next_pos = path[1]
                            inv.last_dir = (next_pos[0] - int(inv.pos.x), next_pos[1] - int(inv.pos.y))
                            inv.pos.update(*next_pos)
                        else:
                            inv.pos.update(*path[0])
                        if tuple(map(int, (inv.pos.x, inv.pos.y))) == self.ghost_exit:
                            inv.state = "normal"
                            inv.reversed_this_fright = False
                    else:
                        exit_neighbors = self._neighbors((int(inv.pos.x), int(inv.pos.y)))
                        if self.ghost_exit in exit_neighbors:
                            inv.pos.update(*self.ghost_exit)
                            inv.state = "normal"
                            inv.reversed_this_fright = False
                continue
            
            node = (int(inv.pos.x), int(inv.pos.y))
            factor = self.tunnel_speed_factor if node in self.tunnels else 1.0
            step_time_g = 1.0 / (gps * factor)
            inv.step_accum += dt
            while inv.step_accum >= step_time_g:
                inv.step_accum -= step_time_g
                self._step_invader(inv)
        
        # Win condition
        if not self.pellets and not self.energizers:
            self._advance_level()

    def _step_player(self) -> None:
        if self._can_move(self.player, self.desired_dir, is_player=True):
            self.current_dir = self.desired_dir
        if self._can_move(self.player, self.current_dir, is_player=True):
            self.player += pygame.Vector2(self.current_dir)
            self.player.update(*self._apply_tunnel(self.player))
        
        pnode = (int(self.player.x), int(self.player.y))
        
        pellet_eaten = False
        if pnode in self.pellets:
            self.pellets.remove(pnode)
            self.pellets_eaten += 1
            self.score += 10
            pellet_eaten = True
            self.sounds.play("eat")
        if pnode in self.energizers:
            self.energizers.remove(pnode)
            self.pellets_eaten += 1
            self.score += 50
            self._trigger_frightened()
            pellet_eaten = True
        if pellet_eaten:
            self.global_timeout = 0.0
        
        if self.fruit_active and pnode == self.fruit_pos:
            self.score += self.fruit_level_pts
            self.fruit_active = False
            self.sounds.play("power_up")
        
        for inv in self.invaders:
            self._resolve_collision(inv)

    def _step_invader(self, inv: Invader) -> None:
        start = (int(inv.pos.x), int(inv.pos.y))
        
        if self.frightened_timer > 0:
            if not inv.reversed_this_fright and inv.last_dir != (0, 0):
                inv.last_dir = (-inv.last_dir[0], -inv.last_dir[1])
                inv.reversed_this_fright = True
            inv.state = "frightened"
            nbs = self._neighbors(start)
            if nbs:
                chosen = random.choice(nbs)
                inv.last_dir = (chosen[0] - start[0], chosen[1] - start[1])
                inv.pos.update(*chosen)
        else:
            inv.state = "normal"
            target = inv.scatter_corner if self.mode == "scatter" else self._chase_target(inv)
            path = self._ghost_astar(start, target)
            if path and len(path) > 1:
                next_pos = path[1]
                inv.last_dir = (next_pos[0] - start[0], next_pos[1] - start[1])
                inv.pos.update(*next_pos)
            else:
                nbs = self._neighbors(start)
                if nbs:
                    chosen = random.choice(nbs)
                    inv.last_dir = (chosen[0] - start[0], chosen[1] - start[1])
                    inv.pos.update(*chosen)
            inv.reversed_this_fright = False
        
        new_node = (int(inv.pos.x), int(inv.pos.y))
        if new_node in self.tunnels:
            inv.pos.update(*self._apply_tunnel(inv.pos))
        self._resolve_collision(inv)

    def _step_invader_eyes(self, inv: Invader) -> None:
        start = (int(inv.pos.x), int(inv.pos.y))
        path = self._ghost_astar_eyes(start, self.ghost_house)
        if path and len(path) > 1:
            next_pos = path[1]
            inv.last_dir = (next_pos[0] - start[0], next_pos[1] - start[1])
            inv.pos.update(*next_pos)
        if tuple(map(int, (inv.pos.x, inv.pos.y))) == self.ghost_house:
            inv.state = "normal"
            inv.reversed_this_fright = False

    def _neighbors(self, node: Vec2) -> List[Vec2]:
        x, y = node
        out = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
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

    def _should_release(self, inv: Invader) -> bool:
        if inv.idx == 0:
            return True
        if inv.idx == 1:
            if not self.pinky_unlocked and self.release_elapsed >= self.pinky_delay:
                self.pinky_unlocked = True
            return self.pinky_unlocked
        if inv.idx == 2:
            if not self.pinky_unlocked:
                return False
            if not self.inky_unlocked and self.pellets_eaten >= self.inky_threshold:
                self.inky_unlocked = True
            return self.inky_unlocked
        if inv.idx == 3:
            if not self.inky_unlocked:
                return False
            if not self.clyde_unlocked and self.pellets_eaten >= self.clyde_threshold:
                self.clyde_unlocked = True
            return self.clyde_unlocked
        return False

    def _force_release_next_invader(self) -> None:
        for idx in (1, 2, 3):
            inv = self.invaders[idx]
            if inv.state == "caged":
                if idx == 1:
                    self.pinky_unlocked = True
                    self.release_elapsed = self.pinky_delay
                    break
                elif idx == 2:
                    if self.pellets_eaten >= self.inky_threshold:
                        self.inky_unlocked = True
                        break
                elif idx == 3:
                    if self.pellets_eaten >= self.clyde_threshold:
                        self.clyde_unlocked = True
                        break

    def _resolve_collision(self, inv: Invader) -> None:
        pnode = (int(self.player.x), int(self.player.y))
        inode = (int(inv.pos.x), int(inv.pos.y))
        if pnode != inode:
            return
        
        if self.frightened_timer > 0 and inv.state == "frightened":
            points = [200, 400, 800, 1600][min(self.frightened_chain, 3)]
            self.score += points
            self.frightened_chain += 1
            inv.state = "eyes"
            self.sounds.play("power_up")
        elif inv.state not in ("eyes", "caged"):
            self.lives -= 1
            self.death_animation = True
            self.death_timer = 0.0
            self.cruise_elroy_stage = 0

    def _trigger_frightened(self) -> None:
        base = 6.0
        duration = max(0.5, base - 0.3 * (self.level - 1))
        self.frightened_timer = duration
        self.frightened_chain = 0
        for inv in self.invaders:
            inv.reversed_this_fright = False
        self.sounds.play("power_up")

    def _advance_level(self) -> None:
        self.level += 1
        self.scatter_duration = max(2.0, 7.0 - 0.3 * (self.level - 1))
        (
            self.grid,
            self.pellets,
            self.energizers,
            self.player_start,
            self.ghost_house_tiles,
            self.tunnels,
            self.house_spaces,
        ) = self._parse_map(RAW_MAP)
        self.player_block = set(self.ghost_house_tiles) | set(self.house_spaces)
        reachable = self._reachable_from(self.player_start, forbid=self.player_block)
        self.pellets = {p for p in self.pellets if p in reachable and p not in self.player_block}
        self.energizers = {e for e in self.energizers if e in reachable and e not in self.player_block}
        self.pellets_total = len(self.pellets) + len(self.energizers)
        self.pellets_eaten = 0
        self.fruit_spawns_left = 2
        self._restart_level(full_reset=False)

    def _spawn_fruit(self) -> None:
        if self.fruit_spawns_left <= 0:
            return
        self.fruit_spawns_left -= 1
        self.fruit_active = True
        self.fruit_timer = 9.0
        self._update_fruit_for_level()

    def _update_fruit_for_level(self) -> None:
        pts = 100
        name = "Cherry"
        for lvl, lname, lpts in FRUIT_TABLE:
            if self.level <= lvl:
                name, pts = lname, lpts
                break
        self.fruit_name = name
        self.fruit_level_pts = pts

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

    def _chase_target(self, inv: Invader) -> Vec2:
        p = (int(self.player.x), int(self.player.y))
        d = self.current_dir
        
        if inv.idx == 0:
            return p
        elif inv.idx == 1:
            return (
                max(0, min(self.w - 1, p[0] + 4 * d[0])),
                max(0, min(self.h - 1, p[1] + 4 * d[1]))
            )
        elif inv.idx == 2:
            two_ahead = (
                max(0, min(self.w - 1, p[0] + 2 * d[0])),
                max(0, min(self.h - 1, p[1] + 2 * d[1]))
            )
            red = next((i for i in self.invaders if i.idx == 0), self.invaders[0])
            vec = (two_ahead[0] - int(red.pos.x), two_ahead[1] - int(red.pos.y))
            return (
                max(0, min(self.w - 1, int(red.pos.x) + 2 * vec[0])),
                max(0, min(self.h - 1, int(red.pos.y) + 2 * vec[1]))
            )
        else:
            dist = abs(int(inv.pos.x) - p[0]) + abs(int(inv.pos.y) - p[1])
            return p if dist > 8 else inv.scatter_corner

    # ==================== DRAWING ====================

    def draw(self) -> None:
        self._draw_maze()
        self._draw_collectibles()
        
        if not self.death_animation:
            self._draw_player()
        else:
            self._draw_player_death()
        
        self._draw_invaders()
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
        for x, y in self.pellets:
            cx = ox + x * self.cell + self.cell // 2
            cy = oy + y * self.cell + self.cell // 2
            pygame.draw.circle(self.screen, PELLET_COLOR, (cx, cy), 2)
        for x, y in self.energizers:
            cx = ox + x * self.cell + self.cell // 2
            cy = oy + y * self.cell + self.cell // 2
            r = 6 if (pygame.time.get_ticks() // 250) % 2 == 0 else 4
            pygame.draw.circle(self.screen, ENERGIZER_COLOR, (cx, cy), r)
        if self.fruit_active:
            x, y = self.fruit_pos
            r = pygame.Rect(ox + x * self.cell + 4, oy + y * self.cell + 4, self.cell - 8, self.cell - 8)
            pygame.draw.ellipse(self.screen, (255, 50, 50), r)

    def _draw_player(self) -> None:
        ox, oy = int(self.offset.x), int(self.offset.y)
        x, y = int(self.player.x), int(self.player.y)
        r = pygame.Rect(ox + x * self.cell, oy + y * self.cell, self.cell - 2, self.cell - 2)
        t = (pygame.time.get_ticks() % 400) / 400.0
        mouth = int(20 + 25 * abs(0.5 - t) * 2)
        angle = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}.get(self.current_dir, 0)
        pygame.draw.circle(self.screen, PLAYER_COLOR, r.center, r.width // 2)
        
        rad1 = math.radians(angle - mouth)
        rad2 = math.radians(angle + mouth)
        radius = r.width // 2
        p1 = (r.center[0] + radius * math.cos(rad1), r.center[1] - radius * math.sin(rad1))
        p2 = (r.center[0] + radius * math.cos(rad2), r.center[1] - radius * math.sin(rad2))
        pygame.draw.polygon(self.screen, (0, 0, 0), [r.center, p1, p2])

    def _draw_player_death(self) -> None:
        ox, oy = int(self.offset.x), int(self.offset.y)
        x, y = int(self.player.x), int(self.player.y)
        cx = ox + x * self.cell + self.cell // 2
        cy = oy + y * self.cell + self.cell // 2
        progress = self.death_timer / self.death_duration
        radius = int((self.cell // 2) * (1.0 - progress))
        if radius > 0:
            pygame.draw.circle(self.screen, PLAYER_COLOR, (cx, cy), radius)

    def _draw_invaders(self) -> None:
        """Draw Space Invader sprites instead of ghosts."""
        ox, oy = int(self.offset.x), int(self.offset.y)
        
        for inv in self.invaders:
            x, y = int(inv.pos.x), int(inv.pos.y)
            rect = pygame.Rect(ox + x * self.cell, oy + y * self.cell, self.cell - 2, self.cell - 2)
            
            if inv.state == "eyes":
                self._draw_invader_eyes(rect, inv.idx)
                continue
            
            # Choose pattern and color based on state
            if inv.state == "frightened":
                pattern = FRIGHTENED_PATTERN
                color = FRIGHTENED_COLOR
                # Flashing effect when frightened time is low
                if self.frightened_timer < 2.0 and (pygame.time.get_ticks() // 200) % 2 == 0:
                    color = (255, 255, 255)
            else:
                pattern = INVADER_PATTERNS[inv.idx]
                color = INVADER_COLORS[inv.idx]
            
            # Draw the Space Invader pixel art
            self._draw_invader_sprite(rect, pattern, color)

    def _draw_invader_sprite(self, rect: pygame.Rect, pattern: list, color: tuple) -> None:
        """Draw a Space Invader using pixel art pattern."""
        pattern_h = len(pattern)
        pattern_w = len(pattern[0]) if pattern else 0
        
        if pattern_w == 0 or pattern_h == 0:
            return
        
        # Calculate pixel size to fit the pattern in the rect
        pixel_w = max(1, rect.width // pattern_w)
        pixel_h = max(1, rect.height // pattern_h)
        
        # Center the pattern in the rect
        start_x = rect.x + (rect.width - pattern_w * pixel_w) // 2
        start_y = rect.y + (rect.height - pattern_h * pixel_h) // 2
        
        # Simple animation: alternate legs/arms position
        anim_frame = int(self.invader_anim_timer * 3) % 2
        
        for py, row in enumerate(pattern):
            for px, pixel in enumerate(row):
                if pixel == 1:
                    # Animate bottom rows (legs)
                    offset_x = 0
                    if py >= pattern_h - 2 and anim_frame == 1:
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

    def _draw_invader_eyes(self, rect: pygame.Rect, idx: int) -> None:
        """Draw just eyes for returning invader (after being eaten)."""
        color = INVADER_COLORS[idx]
        eye_y = rect.centery
        eye_size = max(3, rect.width // 5)
        
        # Draw two glowing eyes
        pygame.draw.circle(self.screen, color, (rect.centerx - 5, eye_y), eye_size)
        pygame.draw.circle(self.screen, color, (rect.centerx + 5, eye_y), eye_size)
        pygame.draw.circle(self.screen, (255, 255, 255), (rect.centerx - 5, eye_y), eye_size - 1)
        pygame.draw.circle(self.screen, (255, 255, 255), (rect.centerx + 5, eye_y), eye_size - 1)
        pygame.draw.circle(self.screen, (0, 0, 0), (rect.centerx - 4, eye_y), 2)
        pygame.draw.circle(self.screen, (0, 0, 0), (rect.centerx + 6, eye_y), 2)

    def _draw_hud(self) -> None:
        s1 = self.font.render(f"Score: {self.score}", True, (255, 255, 255))
        s2 = self.font.render(f"Lives: {self.lives}", True, (255, 255, 255))
        s3 = self.font.render(f"Level: {self.level}", True, (255, 255, 255))
        self.screen.blit(s1, (16, 10))
        self.screen.blit(s2, (16, 32))
        self.screen.blit(s3, (16, 54))
        
        # Mode label
        mode_label = self.font.render("PAC-MAN + INVADERS", True, (255, 100, 100))
        self.screen.blit(mode_label, (self.cfg.width // 2 - mode_label.get_width() // 2, 10))

    def _build_go_buttons(self) -> None:
        self.go_button_rects.clear()
        labels = [("restart", "Play Again"), ("back", "Back To Menu")]
        spacing, padding_x, padding_y, button_width = 64, 22, 12, 360
        start_y = self.cfg.height // 2 - len(labels) * spacing // 2 + 40
        for i, (key, text) in enumerate(labels):
            surf = self.font.render(text, True, (255, 255, 255))
            w = max(button_width, surf.get_width() + padding_x * 2)
            h = surf.get_height() + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            y = start_y + i * spacing
            self.go_button_rects.append((key, pygame.Rect(x, y, w, h)))

    def _build_pause_buttons(self) -> None:
        self.pause_button_rects.clear()
        labels = [("resume", "Resume"), ("restart", "Restart"), ("back", "Back To Menu")]
        spacing, padding_x, padding_y, button_width = 64, 22, 12, 360
        start_y = self.cfg.height // 2 - len(labels) * spacing // 2
        for i, (key, text) in enumerate(labels):
            surf = self.font.render(text, True, (255, 255, 255))
            w = max(button_width, surf.get_width() + padding_x * 2)
            h = surf.get_height() + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            y = start_y + i * spacing
            self.pause_button_rects.append((key, pygame.Rect(x, y, w, h)))

    def _draw_pause_menu(self) -> None:
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        
        title = self.title_font.render("Paused", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 120))
        
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
        
        title = self.title_font.render("Game Over", True, (255, 100, 100))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 200))
        
        stats = [f"Level: {self.level}"]
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
        pygame.draw.rect(self.screen, (50, 35, 35), box, border_radius=10)
        pygame.draw.rect(self.screen, (180, 100, 100), box, 2, border_radius=10)
        
        y = box.y + pad_y
        for s in stat_surfs:
            self.screen.blit(s, (box.x + pad_x, y))
            y += s.get_height() + line_spacing
        
        gap = 28
        self._build_go_buttons()
        self.go_button_rects.clear()
        labels = [("restart", "Play Again"), ("back", "Back To Menu")]
        spacing = 50
        start_y = box.bottom + gap
        for i, (key, text) in enumerate(labels):
            surf = self.font.render(text, True, (255, 255, 255))
            w = max(340, surf.get_width() + 40)
            h = surf.get_height() + 20
            x = self.cfg.width // 2 - w // 2
            btn_y = start_y + i * spacing
            self.go_button_rects.append((key, pygame.Rect(x, btn_y, w, h)))
        
        mouse = pygame.mouse.get_pos()
        for key, rect in self.go_button_rects:
            hovered = rect.collidepoint(*mouse)
            fill = (100, 70, 70) if hovered else (60, 45, 45)
            border = (255, 255, 255) if hovered else (180, 140, 140)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=8)
            label = "Play Again" if key == "restart" else "Back To Menu"
            ts = self.font.render(label, True, (255, 255, 255))
            self.screen.blit(ts, (rect.x + (rect.width - ts.get_width()) // 2, rect.y + (rect.height - ts.get_height()) // 2))

    def _draw_win(self) -> None:
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        title = self.title_font.render("Level Complete!", True, (100, 255, 100))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 60))
