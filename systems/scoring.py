from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

@dataclass
class ScoreEvent:
    lines_cleared: int = 0
    fruits_eaten: int = 0
    pellets_eaten: int = 0
    ghosts_eaten: int = 0
    enemies_destroyed: int = 0
    level: int = 1

def tetris_score(event: ScoreEvent) -> int:
    base = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}
    return base.get(event.lines_cleared, 0) * event.level

def snake_score(event: ScoreEvent) -> int:
    return event.fruits_eaten * 10

def pacman_score(event: ScoreEvent) -> int:
    return event.pellets_eaten + event.ghosts_eaten * 5

def invaders_score(event: ScoreEvent) -> int:
    return event.enemies_destroyed * 20

def hybrid_score(event: ScoreEvent) -> int:
    return (
        tetris_score(event)
        + snake_score(event)
        + pacman_score(event)
        + invaders_score(event)
    )

FORMAT_SUFFIX = {0: "", 1: " pt", 2: " pts"}

def format_score(score: int) -> str:
    suffix = FORMAT_SUFFIX[min(len(FORMAT_SUFFIX) - 1, score if score < 3 else 2)]
    return f"{score}{suffix}"
