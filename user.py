from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Optional, Dict
import bcrypt
from settings import DATA_DIR

DB_PATH = DATA_DIR / "users.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS progress (
    username TEXT NOT NULL,
    game TEXT NOT NULL,
    score INTEGER NOT NULL,
    PRIMARY KEY (username, game),
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
);
"""

def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn

def register_user(username: str, password: str) -> bool:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    with _connect() as conn:
        try:
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed))
        except sqlite3.IntegrityError:
            return False
    return True

def login_user(username: str, password: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), row[0])

def save_progress(username: str, game: str, score: int) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO progress (username, game, score)
            VALUES (?, ?, ?)
            ON CONFLICT(username, game) DO UPDATE SET score = MAX(score, excluded.score)
            """,
            (username, game, score),
        )

def load_progress(username: str) -> Dict[str, int]:
    with _connect() as conn:
        rows = conn.execute("SELECT game, score FROM progress WHERE username = ?", (username,)).fetchall()
    return {game: score for game, score in rows}

def reset_account(username: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM progress WHERE username = ?", (username,))
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
