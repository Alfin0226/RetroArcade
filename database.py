from __future__ import annotations
import asyncpg
from typing import Optional, Dict
from datetime import datetime, date
from settings import DatabaseConfig

class DatabaseManager:
    """Async database manager for Neon/Postgres with connection pooling."""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self) -> None:
        """Create connection pool."""
        if not self.config.is_configured:
            print("⚠️  Database not configured - skipping connection")
            return
        
        try:
            if self.config.connection_string:
                self.pool = await asyncpg.create_pool(
                    self.config.connection_string,
                    min_size=2,
                    max_size=10,
                    command_timeout=60
                )
            else:
                self.pool = await asyncpg.create_pool(
                    host=self.config.host,
                    port=self.config.port,
                    database=self.config.database,
                    user=self.config.user,
                    password=self.config.password,
                    min_size=2,
                    max_size=10,
                    command_timeout=60
                )
            print("✅ Database connected successfully")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            self.pool = None
    
    async def disconnect(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            print("🔌 Database disconnected")
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query that doesn't return rows (INSERT, UPDATE, DELETE)."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Fetch multiple rows."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args, column: int = 0):
        """Fetch a single value."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args, column=column)
    
    # ========== USER MANAGEMENT ==========
    
    async def create_user(self, username: str, email: str, password_hash: str) -> Optional[int]:
        """Create a new user account. Returns user_id if successful."""
        query = """
            INSERT INTO users (username, email, password_hash, created_at)
            VALUES ($1, $2, $3, NOW())
            RETURNING user_id
        """
        try:
            user_id = await self.fetchval(query, username, email, password_hash)
            # Create default scores and settings
            await self._init_user_data(user_id)
            return user_id
        except asyncpg.UniqueViolationError:
            return None  # Username or email already exists
    
    async def _init_user_data(self, user_id: int) -> None:
        """Initialize default scores and settings for new user."""
        scores_query = """
            INSERT INTO scores (user_id, total_score, pacman_score, tetris_score, 
                              snake_score, space_invaders_score, login_streak, last_login_date)
            VALUES ($1, 0, 0, 0, 0, 0, 0, NULL)
        """
        settings_query = """
            INSERT INTO user_settings (user_id, difficulty, volume, keybinds)
            VALUES ($1, 'intermediate', 100, '{}')
        """
        await self.execute(scores_query, user_id)
        await self.execute(settings_query, user_id)
    
    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user by username."""
        query = "SELECT * FROM users WHERE username = $1"
        row = await self.fetchrow(query, username)
        return dict(row) if row else None
    
    async def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user by email."""
        query = "SELECT * FROM users WHERE email = $1"
        row = await self.fetchrow(query, email)
        return dict(row) if row else None
    
    async def verify_login(self, username: str, password_hash: str) -> Optional[int]:
        """Verify login credentials. Returns user_id if valid."""
        query = "SELECT user_id FROM users WHERE username = $1 AND password_hash = $2"
        return await self.fetchval(query, username, password_hash)
    
    async def update_login_streak(self, user_id: int) -> int:
        """Update login streak for user. Returns new streak count."""
        # Get last login date
        query = "SELECT last_login_date FROM scores WHERE user_id = $1"
        last_login = await self.fetchval(query, user_id)
        
        today = date.today()
        new_streak = 1
        
        if last_login:
            days_diff = (today - last_login).days
            if days_diff == 1:
                # Consecutive day
                query = "SELECT login_streak FROM scores WHERE user_id = $1"
                old_streak = await self.fetchval(query, user_id)
                new_streak = old_streak + 1
            elif days_diff > 1:
                # Streak broken
                new_streak = 1
        
        # Update streak and last login
        query = """
            UPDATE scores 
            SET login_streak = $1, last_login_date = $2
            WHERE user_id = $3
        """
        await self.execute(query, new_streak, today, user_id)
        return new_streak
    
    # ========== SCORE MANAGEMENT ==========
    
    async def update_game_score(self, user_id: int, game: str, score: int) -> bool:
        """Update score for a specific game if it's a new high score."""
        game_col = f"{game.lower()}_score"
        
        # Check if it's a high score
        query = f"SELECT {game_col} FROM scores WHERE user_id = $1"
        current_high = await self.fetchval(query, user_id)
        
        if score > current_high:
            # Update game score and recalculate total
            update_query = f"""
                UPDATE scores 
                SET {game_col} = $1,
                    total_score = pacman_score + tetris_score + snake_score + space_invaders_score
                WHERE user_id = $2
            """
            # Replace the specific game score in the calculation
            update_query = update_query.replace(game_col, str(score))
            await self.execute(update_query, score, user_id)
            return True
        return False
    
    async def get_user_scores(self, user_id: int) -> Dict:
        """Get all scores for a user."""
        query = "SELECT * FROM scores WHERE user_id = $1"
        row = await self.fetchrow(query, user_id)
        return dict(row) if row else {}
    
    async def get_global_leaderboard(self, limit: int = 10) -> list[Dict]:
        """Get global leaderboard by total score."""
        query = """
            SELECT u.username, s.total_score, s.login_streak
            FROM users u
            JOIN scores s ON u.user_id = s.user_id
            ORDER BY s.total_score DESC
            LIMIT $1
        """
        rows = await self.fetch(query, limit)
        return [dict(row) for row in rows]
    
    async def get_game_leaderboard(self, game: str, limit: int = 10) -> list[Dict]:
        """Get leaderboard for a specific game."""
        game_col = f"{game.lower()}_score"
        query = f"""
            SELECT u.username, s.{game_col} as score
            FROM users u
            JOIN scores s ON u.user_id = s.user_id
            WHERE s.{game_col} > 0
            ORDER BY s.{game_col} DESC
            LIMIT $1
        """
        rows = await self.fetch(query, limit)
        return [dict(row) for row in rows]
    
    # ========== USER SETTINGS ==========
    
    async def get_user_settings(self, user_id: int) -> Dict:
        """Get user settings."""
        query = "SELECT * FROM user_settings WHERE user_id = $1"
        row = await self.fetchrow(query, user_id)
        return dict(row) if row else {}
    
    async def update_user_settings(self, user_id: int, **kwargs) -> None:
        """Update user settings. Pass difficulty, volume, and/or keybinds as kwargs."""
        updates = []
        values = []
        param_num = 1
        
        for key, value in kwargs.items():
            if key in ('difficulty', 'volume', 'keybinds'):
                updates.append(f"{key} = ${param_num}")
                values.append(value)
                param_num += 1
        
        if updates:
            values.append(user_id)
            query = f"UPDATE user_settings SET {', '.join(updates)} WHERE user_id = ${param_num}"
            await self.execute(query, *values)
    
    # ========== DATABASE INITIALIZATION ==========
    
    async def init_schema(self) -> None:
        """Initialize all database tables with proper relationships."""
        if not self.pool:
            return
        
        schema = """
            -- Users table (authentication)
            CREATE TABLE IF NOT EXISTS users (
                user_id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            
            -- Scores table (game statistics)
            CREATE TABLE IF NOT EXISTS scores (
                user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                total_score INTEGER DEFAULT 0,
                pacman_score INTEGER DEFAULT 0,
                tetris_score INTEGER DEFAULT 0,
                snake_score INTEGER DEFAULT 0,
                space_invaders_score INTEGER DEFAULT 0,
                login_streak INTEGER DEFAULT 0,
                last_login_date DATE
            );
            
            -- User settings table (preferences)
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                difficulty VARCHAR(20) DEFAULT 'intermediate',
                volume INTEGER DEFAULT 100,
                keybinds TEXT DEFAULT '{}'
            );
            
            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_scores_total ON scores(total_score DESC);
            CREATE INDEX IF NOT EXISTS idx_scores_pacman ON scores(pacman_score DESC);
            CREATE INDEX IF NOT EXISTS idx_scores_tetris ON scores(tetris_score DESC);
            CREATE INDEX IF NOT EXISTS idx_scores_snake ON scores(snake_score DESC);
            CREATE INDEX IF NOT EXISTS idx_scores_space_invaders ON scores(space_invaders_score DESC);
        """
        async with self.pool.acquire() as conn:
            await conn.execute(schema)
        print("📊 Database schema initialized with users, scores, and user_settings tables")

# Global instance (initialized in main.py)
db: Optional[DatabaseManager] = None
