from __future__ import annotations
from typing import Iterable, Tuple
import pygame

Rect = pygame.Rect

def rects_collide(a: Rect, b: Rect) -> bool:
    return a.colliderect(b)

def rect_vs_many(rect: Rect, others: Iterable[Rect]) -> bool:
    return any(rect.colliderect(other) for other in others)

def point_in_grid(point: Tuple[int, int], grid_size: Tuple[int, int]) -> bool:
    x, y = point
    width, height = grid_size
    return 0 <= x < width and 0 <= y < height
