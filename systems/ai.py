from __future__ import annotations
from heapq import heappush, heappop
from typing import Dict, List, Tuple, Optional, Iterable

Grid = List[List[int]]
Node = Tuple[int, int]

def heuristic(a: Node, b: Node) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def neighbors(node: Node, grid: Grid) -> Iterable[Node]:
    x, y = node
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= ny < len(grid) and 0 <= nx < len(grid[0]) and grid[ny][nx] == 0:
            yield (nx, ny)

def astar(start: Node, goal: Node, grid: Grid) -> Optional[List[Node]]:
    open_set: List[Tuple[int, Node]] = []
    heappush(open_set, (0, start))
    came_from: Dict[Node, Optional[Node]] = {start: None}
    g_score: Dict[Node, int] = {start: 0}

    while open_set:
        _, current = heappop(open_set)
        if current == goal:
            path: List[Node] = []
            while current:
                path.append(current)
                current = came_from[current]
            return list(reversed(path))

        for nxt in neighbors(current, grid):
            tentative = g_score[current] + 1
            if tentative < g_score.get(nxt, 1_000_000):
                came_from[nxt] = current
                g_score[nxt] = tentative
                f_score = tentative + heuristic(nxt, goal)
                heappush(open_set, (f_score, nxt))
    return None
