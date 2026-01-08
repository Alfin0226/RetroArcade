from __future__ import annotations
import asyncio
import aiosqlite
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from pathlib import Path
import re

try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False
    asyncpg = None

from settings import DatabaseConfig, DATA_DIR


class DatabaseBackend(ABC):
    """Abstract base class for database backends."""
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to database. Returns True if successful."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close database connection."""
        pass
    
    @abstractmethod
    async def execute(self, query: str, *args) -> Any:
        """Execute a query that doesn't return rows."""
        pass
    
    @abstractmethod
    async def fetch(self, query: str, *args) -> List[Dict]:
        """Fetch multiple rows as list of dicts."""
        pass
    
    @abstractmethod
    async def fetchrow(self, query: str, *args) -> Optional[Dict]:
        """Fetch a single row as dict."""
        pass
    
    @abstractmethod
    async def fetchval(self, query: str, *args, column: int = 0) -> Any:
        """Fetch a single value."""
        pass
    
    @abstractmethod
    async def init_schema(self) -> None:
        """Initialize database schema."""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if database is connected."""
        pass
    
    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Return the backend name for logging."""
        pass


class PostgresBackend(DatabaseBackend):
    """PostgreSQL/Neon database backend using asyncpg."""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
    
    @property
    def is_connected(self) -> bool:
        return self.pool is not None
    
    @property
    def backend_name(self) -> str:
        return "PostgreSQL (Production)"
    
    async def connect(self) -> bool:
        """Create connection pool."""
        if not HAS_ASYNCPG:
            print("⚠️  asyncpg not installed - PostgreSQL unavailable")
            return False
        
        if not self.config.is_configured:
            print("⚠️  PostgreSQL not configured - skipping")
            return False
        
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
            return True
        except Exception as e:
            print(f"❌ PostgreSQL connection failed: {e}")
            self.pool = None
            return False
    
    async def disconnect(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query that doesn't return rows."""
        if not self.pool:
            raise RuntimeError("PostgreSQL not connected")
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> List[Dict]:
        """Fetch multiple rows."""
        if not self.pool:
            raise RuntimeError("PostgreSQL not connected")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]
    
    async def fetchrow(self, query: str, *args) -> Optional[Dict]:
        """Fetch a single row."""
        if not self.pool:
            raise RuntimeError("PostgreSQL not connected")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None
    
    async def fetchval(self, query: str, *args, column: int = 0) -> Any:
        """Fetch a single value."""
        if not self.pool:
            raise RuntimeError("PostgreSQL not connected")
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args, column=column)
    
    async def init_schema(self) -> None:
        """Initialize PostgreSQL schema."""
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
                hybrid_score INTEGER DEFAULT 0,
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
            CREATE INDEX IF NOT EXISTS idx_scores_hybrid ON scores(hybrid_score DESC);
        """
        async with self.pool.acquire() as conn:
            await conn.execute(schema)


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend using aiosqlite for local storage."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None
    
    @property
    def is_connected(self) -> bool:
        return self.conn is not None
    
    @property
    def backend_name(self) -> str:
        return "SQLite (Local)"
    
    async def connect(self) -> bool:
        """Open SQLite database connection."""
        try:
            # Ensure data directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            # Add timeout to prevent database locked errors
            self.conn = await aiosqlite.connect(
                str(self.db_path),
                timeout=30.0  # 30 second timeout
            )
            self.conn.row_factory = aiosqlite.Row
            # Enable WAL mode for better concurrent access
            await self.conn.execute("PRAGMA journal_mode=WAL")
            # Enable foreign keys
            await self.conn.execute("PRAGMA foreign_keys = ON")
            # Set busy timeout
            await self.conn.execute("PRAGMA busy_timeout = 30000")
            await self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ SQLite connection failed: {e}")
            self.conn = None
            return False
    
    async def disconnect(self) -> None:
        """Close SQLite connection."""
        if self.conn:
            await self.conn.close()
            self.conn = None
    
    def _convert_query(self, query: str) -> str:
        """Convert PostgreSQL query syntax to SQLite."""
        result = query
        # Replace $N with ?
        result = re.sub(r'\$\d+', '?', result)
        # Replace NOW() with datetime('now')
        result = result.replace('NOW()', "datetime('now')")
        # Replace SERIAL with INTEGER (SQLite auto-increments INTEGER PRIMARY KEY)
        result = result.replace('SERIAL', 'INTEGER')
        # Remove VARCHAR length limits (SQLite doesn't enforce them)
        result = re.sub(r'VARCHAR\(\d+\)', 'TEXT', result)
        # Replace TIMESTAMP with TEXT (SQLite stores as text)
        result = result.replace('TIMESTAMP', 'TEXT')
        return result
    
    async def execute(self, query: str, *args) -> Any:
        """Execute a query that doesn't return rows."""
        if not self.conn:
            raise RuntimeError("SQLite not connected")
        converted_query = self._convert_query(query)
        await self.conn.execute(converted_query, args)
        await self.conn.commit()
        return "OK"
    
    async def fetch(self, query: str, *args) -> List[Dict]:
        """Fetch multiple rows."""
        if not self.conn:
            raise RuntimeError("SQLite not connected")
        converted_query = self._convert_query(query)
        async with self.conn.execute(converted_query, args) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def fetchrow(self, query: str, *args) -> Optional[Dict]:
        """Fetch a single row."""
        if not self.conn:
            raise RuntimeError("SQLite not connected")
        converted_query = self._convert_query(query)
        async with self.conn.execute(converted_query, args) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def fetchval(self, query: str, *args, column: int = 0) -> Any:
        """Fetch a single value."""
        if not self.conn:
            raise RuntimeError("SQLite not connected")
        converted_query = self._convert_query(query)
        async with self.conn.execute(converted_query, args) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[column]
            return None
    
    async def init_schema(self) -> None:
        """Initialize SQLite schema."""
        if not self.conn:
            return
        
        # Create tables first (without indexes that may depend on columns we need to add)
        tables_schema = """
            -- Users table (authentication)
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            
            -- Scores table (game statistics) - base columns only
            CREATE TABLE IF NOT EXISTS scores (
                user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                total_score INTEGER DEFAULT 0,
                pacman_score INTEGER DEFAULT 0,
                tetris_score INTEGER DEFAULT 0,
                snake_score INTEGER DEFAULT 0,
                space_invaders_score INTEGER DEFAULT 0,
                login_streak INTEGER DEFAULT 0,
                last_login_date TEXT
            );
            
            -- User settings table (preferences)
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                difficulty TEXT DEFAULT 'intermediate',
                volume INTEGER DEFAULT 100,
                keybinds TEXT DEFAULT '{}'
            );
        """
        # Execute table creation
        for statement in tables_schema.split(';'):
            statement = statement.strip()
            if statement:
                await self.conn.execute(statement)
        await self.conn.commit()
        
        # Run migrations to add new columns to existing databases
        await self._run_migrations()
        
        # Now create indexes (after migrations ensure all columns exist)
        indexes_schema = """
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_scores_total ON scores(total_score DESC);
            CREATE INDEX IF NOT EXISTS idx_scores_pacman ON scores(pacman_score DESC);
            CREATE INDEX IF NOT EXISTS idx_scores_tetris ON scores(tetris_score DESC);
            CREATE INDEX IF NOT EXISTS idx_scores_snake ON scores(snake_score DESC);
            CREATE INDEX IF NOT EXISTS idx_scores_space_invaders ON scores(space_invaders_score DESC);
            CREATE INDEX IF NOT EXISTS idx_scores_hybrid ON scores(hybrid_score DESC);
        """
        for statement in indexes_schema.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    await self.conn.execute(statement)
                except Exception:
                    pass  # Index might already exist or column might not exist yet
        await self.conn.commit()
    
    async def _run_migrations(self) -> None:
        """Run database migrations for existing databases."""
        if not self.conn:
            return
        
        # Check if hybrid_score column exists, add if not
        try:
            await self.conn.execute("SELECT hybrid_score FROM scores LIMIT 1")
        except Exception:
            # Column doesn't exist, add it
            try:
                await self.conn.execute("ALTER TABLE scores ADD COLUMN hybrid_score INTEGER DEFAULT 0")
                await self.conn.commit()
                print("✅ Added hybrid_score column to scores table")
            except Exception as e:
                print(f"Migration note: {e}")


class DatabaseManager:
    """
    Hybrid database manager that prioritizes production (PostgreSQL) 
    and falls back to local (SQLite) if connection fails.
    """
    
    def __init__(self, config: DatabaseConfig, local_db_path: Optional[Path] = None):
        self.config = config
        self.local_db_path = local_db_path or (DATA_DIR / "arcade.db")
        
        # Backends
        self.postgres: Optional[PostgresBackend] = None
        self.sqlite: Optional[SQLiteBackend] = None
        self.active_backend: Optional[DatabaseBackend] = None
        
        # Track which mode we're in
        self.using_production = False
        self.using_local = False
    
    @property
    def is_connected(self) -> bool:
        return self.active_backend is not None and self.active_backend.is_connected
    
    @property
    def backend_name(self) -> str:
        if self.active_backend:
            return self.active_backend.backend_name
        return "Not connected"
    
    async def connect(self) -> None:
        """
        Connect to databases:
        1. Always connect to SQLite (local) for offline backup
        2. Try PostgreSQL (production) if configured
        3. Use PostgreSQL as primary if available, otherwise SQLite
        """
        # Always set up SQLite for local backup
        self.sqlite = SQLiteBackend(self.local_db_path)
        if await self.sqlite.connect():
            await self.sqlite.init_schema()
            self.using_local = True
            print(f"✅ Connected to SQLite (Local) at {self.local_db_path}")
        
        # Try PostgreSQL (production) if configured
        if self.config.is_configured and HAS_ASYNCPG:
            print("🔄 Attempting PostgreSQL (production) connection...")
            self.postgres = PostgresBackend(self.config)
            if await self.postgres.connect():
                self.active_backend = self.postgres
                self.using_production = True
                print(f"✅ Connected to {self.backend_name}")
            else:
                print("⚠️  PostgreSQL unavailable, using local storage only...")
                self.active_backend = self.sqlite
        else:
            if not self.config.is_configured:
                print("ℹ️  No production database configured")
            if not HAS_ASYNCPG:
                print("ℹ️  asyncpg not installed")
            self.active_backend = self.sqlite
        
        if not self.active_backend or not self.active_backend.is_connected:
            print("❌ Failed to connect to any database!")
    
    async def disconnect(self) -> None:
        """Close all database connections."""
        if self.postgres and self.postgres.is_connected:
            await self.postgres.disconnect()
        if self.sqlite and self.sqlite.is_connected:
            await self.sqlite.disconnect()
        
        self.active_backend = None
        self.using_production = False
        self.using_local = False
        print("🔌 Database disconnected")
    
    async def execute(self, query: str, *args) -> Any:
        """Execute a query that doesn't return rows."""
        if not self.active_backend:
            raise RuntimeError("Database not connected")
        return await self.active_backend.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> List[Dict]:
        """Fetch multiple rows as list of dicts."""
        if not self.active_backend:
            raise RuntimeError("Database not connected")
        return await self.active_backend.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[Dict]:
        """Fetch a single row as dict."""
        if not self.active_backend:
            raise RuntimeError("Database not connected")
        return await self.active_backend.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args, column: int = 0) -> Any:
        """Fetch a single value."""
        if not self.active_backend:
            raise RuntimeError("Database not connected")
        return await self.active_backend.fetchval(query, *args, column=column)
    
    async def init_schema(self) -> None:
        """Initialize database schema."""
        if not self.active_backend:
            raise RuntimeError("Database not connected")
        await self.active_backend.init_schema()
        print(f"📊 Database schema initialized ({self.backend_name})")
    
    # ========== USER MANAGEMENT ==========
    
    async def create_user(self, username: str, email: str, password_hash: str) -> Optional[int]:
        """Create a new user account. Returns user_id if successful."""
        # SQLite doesn't support RETURNING well, so handle differently
        if self.using_local:
            try:
                check_query = "SELECT user_id FROM users WHERE username = $1 OR email = $2"
                existing = await self.fetchrow(check_query, username, email)
                if existing:
                    return None  # Already exists
                
                insert_query = """
                    INSERT INTO users (username, email, password_hash)
                    VALUES ($1, $2, $3)
                """
                await self.execute(insert_query, username, email, password_hash)
                
                # Get the last inserted ID
                user_id = await self.fetchval("SELECT last_insert_rowid()")
                await self._init_user_data(user_id)
                return user_id
            except Exception as e:
                print(f"Error creating user: {e}")
                return None
        else:
            # PostgreSQL path
            query = """
                INSERT INTO users (username, email, password_hash, created_at)
                VALUES ($1, $2, $3, NOW())
                RETURNING user_id
            """
            try:
                user_id = await self.fetchval(query, username, email, password_hash)
                await self._init_user_data(user_id)
                return user_id
            except Exception:
                return None  # Username or email already exists
    
    async def _init_user_data(self, user_id: int) -> None:
        """Initialize default scores and settings for new user."""
        scores_query = """
            INSERT INTO scores (user_id, total_score, pacman_score, tetris_score, 
                              snake_score, space_invaders_score, hybrid_score, login_streak, last_login_date)
            VALUES ($1, 0, 0, 0, 0, 0, 0, 0, NULL)
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
        return await self.fetchrow(query, username)
    
    async def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user by email."""
        query = "SELECT * FROM users WHERE email = $1"
        return await self.fetchrow(query, email)
    
    async def verify_login(self, username: str, password_hash: str) -> Optional[int]:
        """Verify login credentials. Returns user_id if valid."""
        query = "SELECT user_id FROM users WHERE username = $1 AND password_hash = $2"
        return await self.fetchval(query, username, password_hash)
    
    async def update_login_streak(self, user_id: int) -> int:
        """Update login streak for user. Returns new streak count."""
        # Get last login date
        query = "SELECT last_login_date FROM scores WHERE user_id = $1"
        last_login_str = await self.fetchval(query, user_id)
        
        today = date.today()
        new_streak = 1
        
        if last_login_str:
            # Parse date - handle both date object and string
            if isinstance(last_login_str, str):
                last_login = date.fromisoformat(last_login_str)
            else:
                last_login = last_login_str
            
            days_diff = (today - last_login).days
            if days_diff == 1:
                # Consecutive day
                query = "SELECT login_streak FROM scores WHERE user_id = $1"
                old_streak = await self.fetchval(query, user_id)
                new_streak = (old_streak or 0) + 1
            elif days_diff == 0:
                # Same day - keep current streak
                query = "SELECT login_streak FROM scores WHERE user_id = $1"
                new_streak = await self.fetchval(query, user_id) or 1
            elif days_diff > 1:
                # Streak broken
                new_streak = 1
        
        # Update streak and last login
        query = """
            UPDATE scores 
            SET login_streak = $1, last_login_date = $2
            WHERE user_id = $3
        """
        await self.execute(query, new_streak, today.isoformat(), user_id)
        return new_streak
    
    # ========== SCORE MANAGEMENT ==========
    
    async def update_game_score(self, user_id: int, game: str, score: int) -> bool:
        """Update score for a specific game if it's a new high score.
        Saves to BOTH local and production databases when available."""
        game_col = f"{game.lower()}_score"
        is_new_high = False
        
        # Save to primary (active) backend
        if self.active_backend and self.active_backend.is_connected:
            is_new_high = await self._update_score_on_backend(self.active_backend, user_id, game_col, score)
        
        # Also save to SQLite if we're using production as primary
        # This ensures local backup always has the scores
        if self.using_production and self.sqlite and self.sqlite.is_connected:
            try:
                await self._update_score_on_backend(self.sqlite, user_id, game_col, score)
                print("💾 Score also saved to local backup")
            except Exception as e:
                print(f"⚠️ Failed to save to local backup: {e}")
        
        return is_new_high
    
    async def _update_score_on_backend(self, backend: DatabaseBackend, user_id: int, game_col: str, score: int) -> bool:
        """Update score on a specific backend. Returns True if new high score."""
        # Check if it's a high score
        query = f"SELECT {game_col} FROM scores WHERE user_id = $1"
        current_high = await backend.fetchval(query, user_id)
        
        if current_high is None:
            current_high = 0
        
        if score > current_high:
            # Update game score
            update_query = f"UPDATE scores SET {game_col} = $1 WHERE user_id = $2"
            await backend.execute(update_query, score, user_id)
            
            # Recalculate total score (sum of all game high scores)
            total_query = """
                UPDATE scores 
                SET total_score = pacman_score + tetris_score + snake_score + space_invaders_score + hybrid_score
                WHERE user_id = $1
            """
            await backend.execute(total_query, user_id)
            return True
        return False
    
    async def get_user_scores(self, user_id: int) -> Dict:
        """Get all scores for a user."""
        query = "SELECT * FROM scores WHERE user_id = $1"
        row = await self.fetchrow(query, user_id)
        return row if row else {}
    
    async def get_global_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Get global leaderboard by total score."""
        query = """
            SELECT u.username, s.total_score, s.login_streak
            FROM users u
            JOIN scores s ON u.user_id = s.user_id
            ORDER BY s.total_score DESC
            LIMIT $1
        """
        return await self.fetch(query, limit)
    
    async def get_game_leaderboard(self, game: str, limit: int = 10) -> List[Dict]:
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
        return await self.fetch(query, limit)
    
    # ========== USER SETTINGS ==========
    
    async def get_user_settings(self, user_id: int) -> Dict:
        """Get user settings."""
        query = "SELECT * FROM user_settings WHERE user_id = $1"
        row = await self.fetchrow(query, user_id)
        return row if row else {}
    
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


# Global instance (initialized in main.py)
db: Optional[DatabaseManager] = None
