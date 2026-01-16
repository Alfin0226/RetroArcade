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

@dataclass
class ScoreBreakdown:
    # Stores all score components for display on game over screen
    base_score: int = 0
    difficulty: str = "intermediate"
    multiplier: float = 1.0
    multiplied_score: int = 0
    level_bonus: int = 0
    streak_bonus: int = 0
    time_bonus: int = 0
    final_score: int = 0
    
    def as_display_lines(self) -> list[str]:
        # Returns formatted lines for game over screen
        lines = [
            f"Base Score: {self.base_score}",
            f"Difficulty: {self.difficulty.capitalize()} (x{self.multiplier})",
        ]
        if self.level_bonus > 0:
            lines.append(f"Level Bonus: +{self.level_bonus}")
        if self.streak_bonus > 0:
            lines.append(f"Streak Bonus: +{self.streak_bonus}")
        if self.time_bonus > 0:
            lines.append(f"Time Bonus: +{self.time_bonus}")
        lines.append(f"Final Score: {self.final_score}")
        return lines

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

def score_multiplier_bonus(difficulty: str, levels: int) -> tuple[float, int]:
    difficulty_multipliers = {
        "easy": 0.8,
        "intermediate": 1.0,
        "hard": 1.5,
    }
    multiplier = difficulty_multipliers.get(difficulty.lower(), 1.0)
    
    # Every 10 levels, add a flat bonus (level * 10)
    bonus = 0
    if levels > 0 and levels % 10 == 0:
        bonus = levels * 10
    
    return multiplier, bonus

def rewarding_streak(login_streak: int, daily_streak: int) -> int:
    reward = 0
    
    if login_streak > 0:
        reward += login_streak * 10
    
    # Daily streak bonus only applies for first 10 games
    if daily_streak > 0:
        capped_streak = min(daily_streak, 10)
        reward += capped_streak * 5
    
    return reward

def time_based_addition(time: int) -> int:
    # 5-10 mins: 100 pts, 10-15 mins: 200 pts, 15+ mins: 300 pts
    if time > 900:
        return 300
    elif time > 600:
        return 200
    elif time >= 300:
        return 100
    return 0

def calculate_final_score(
    base_score: int,
    difficulty: str,
    levels: int,
    login_streak: int,
    daily_streak: int,
    time_played: int
) -> int:
    # Calculate final score using all advanced mechanics.
    # Final_Score = (Base_Score * Multiplier) + Streak_Bonus + Time_Bonus + Level_Bonus
    multiplier, level_bonus = score_multiplier_bonus(difficulty, levels)
    streak_bonus = rewarding_streak(login_streak, daily_streak)
    time_bonus = time_based_addition(time_played)
    
    final_score = int(base_score * multiplier) + streak_bonus + time_bonus + level_bonus
    return final_score

def calculate_score_breakdown(
    base_score: int,
    difficulty: str,
    levels: int,
    login_streak: int,
    daily_streak: int,
    time_played: int
) -> ScoreBreakdown:
    # Calculate final score and return full breakdown for display.
    multiplier, level_bonus = score_multiplier_bonus(difficulty, levels)
    streak_bonus = rewarding_streak(login_streak, daily_streak)
    time_bonus = time_based_addition(time_played)
    multiplied_score = int(base_score * multiplier)
    final_score = multiplied_score + streak_bonus + time_bonus + level_bonus
    
    return ScoreBreakdown(
        base_score=base_score,
        difficulty=difficulty,
        multiplier=multiplier,
        multiplied_score=multiplied_score,
        level_bonus=level_bonus,
        streak_bonus=streak_bonus,
        time_bonus=time_bonus,
        final_score=final_score,
    )
