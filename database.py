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
    
    async def executemany(self, query: str, args_list: List[tuple]) -> None:
        """Execute a query multiple times with different arguments."""
        if not self.pool:
            raise RuntimeError("PostgreSQL not connected")
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args_list)
    
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
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
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
                last_login_date DATE,
                games_played_today INTEGER DEFAULT 0,
                last_played_date DATE,
                updated_at TIMESTAMP DEFAULT NOW()
            );
            
            -- User settings table (preferences)
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                difficulty VARCHAR(20) DEFAULT 'intermediate',
                volume INTEGER DEFAULT 100,
                keybinds TEXT DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT NOW()
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
            # Run migrations for existing databases (adds new columns like hybrid_score, updated_at)
            await self._run_migrations(conn)
            # Create indexes after migrations ensure all columns exist
            try:
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_scores_hybrid ON scores(hybrid_score DESC)")
            except Exception:
                pass
    
    async def _run_migrations(self, conn) -> None:
        """Run database migrations for existing PostgreSQL databases."""
        migrations_run = False
        
        # Add hybrid_score column to scores if not exists
        try:
            result = await conn.fetchval("SELECT column_name FROM information_schema.columns WHERE table_name='scores' AND column_name='hybrid_score'")
            if not result:
                await conn.execute("ALTER TABLE scores ADD COLUMN hybrid_score INTEGER DEFAULT 0")
                migrations_run = True
                print("  ✅ Added hybrid_score column")
        except Exception as e:
            print(f"  Migration note (hybrid_score): {e}")
        
        # Add updated_at column to users if not exists
        try:
            result = await conn.fetchval("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='updated_at'")
            if not result:
                await conn.execute("ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT NOW()")
                migrations_run = True
                print("  ✅ Added updated_at to users")
        except Exception as e:
            print(f"  Migration note (users.updated_at): {e}")
        
        # Add updated_at column to scores if not exists
        try:
            result = await conn.fetchval("SELECT column_name FROM information_schema.columns WHERE table_name='scores' AND column_name='updated_at'")
            if not result:
                await conn.execute("ALTER TABLE scores ADD COLUMN updated_at TIMESTAMP DEFAULT NOW()")
                migrations_run = True
                print("  ✅ Added updated_at to scores")
        except Exception as e:
            print(f"  Migration note (scores.updated_at): {e}")
        
        # Add updated_at column to user_settings if not exists
        try:
            result = await conn.fetchval("SELECT column_name FROM information_schema.columns WHERE table_name='user_settings' AND column_name='updated_at'")
            if not result:
                await conn.execute("ALTER TABLE user_settings ADD COLUMN updated_at TIMESTAMP DEFAULT NOW()")
                migrations_run = True
                print("  ✅ Added updated_at to user_settings")
        except Exception as e:
            print(f"  Migration note (user_settings.updated_at): {e}")
        
        # Add games_played_today column to scores if not exists
        try:
            result = await conn.fetchval("SELECT column_name FROM information_schema.columns WHERE table_name='scores' AND column_name='games_played_today'")
            if not result:
                await conn.execute("ALTER TABLE scores ADD COLUMN games_played_today INTEGER DEFAULT 0")
                migrations_run = True
                print("  ✅ Added games_played_today to scores")
        except Exception as e:
            print(f"  Migration note (games_played_today): {e}")
        
        # Add last_played_date column to scores if not exists
        try:
            result = await conn.fetchval("SELECT column_name FROM information_schema.columns WHERE table_name='scores' AND column_name='last_played_date'")
            if not result:
                await conn.execute("ALTER TABLE scores ADD COLUMN last_played_date DATE")
                migrations_run = True
                print("  ✅ Added last_played_date to scores")
        except Exception as e:
            print(f"  Migration note (last_played_date): {e}")
        
        if migrations_run:
            print("  ✅ Database migrations completed")


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
    
    async def executemany(self, query: str, args_list: List[tuple]) -> None:
        """Execute a query multiple times with different arguments."""
        if not self.conn:
            raise RuntimeError("SQLite not connected")
        converted_query = self._convert_query(query)
        await self.conn.executemany(converted_query, args_list)
        await self.conn.commit()
    
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
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
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
                last_login_date TEXT,
                games_played_today INTEGER DEFAULT 0,
                last_played_date TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            
            -- User settings table (preferences)
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                difficulty TEXT DEFAULT 'intermediate',
                volume INTEGER DEFAULT 100,
                keybinds TEXT DEFAULT '{}',
                updated_at TEXT DEFAULT (datetime('now'))
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
        
        # Add updated_at column to users if not exists
        try:
            await self.conn.execute("SELECT updated_at FROM users LIMIT 1")
        except Exception:
            try:
                await self.conn.execute("ALTER TABLE users ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))")
                await self.conn.commit()
                print("✅ Added updated_at column to users table")
            except Exception as e:
                print(f"Migration note: {e}")
        
        # Add updated_at column to scores if not exists
        try:
            await self.conn.execute("SELECT updated_at FROM scores LIMIT 1")
        except Exception:
            try:
                await self.conn.execute("ALTER TABLE scores ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))")
                await self.conn.commit()
                print("✅ Added updated_at column to scores table")
            except Exception as e:
                print(f"Migration note: {e}")
        
        # Add updated_at column to user_settings if not exists
        try:
            await self.conn.execute("SELECT updated_at FROM user_settings LIMIT 1")
        except Exception:
            try:
                await self.conn.execute("ALTER TABLE user_settings ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))")
                await self.conn.commit()
                print("✅ Added updated_at column to user_settings table")
            except Exception as e:
                print(f"Migration note: {e}")
        
        # Add games_played_today column to scores if not exists
        try:
            await self.conn.execute("SELECT games_played_today FROM scores LIMIT 1")
        except Exception:
            try:
                await self.conn.execute("ALTER TABLE scores ADD COLUMN games_played_today INTEGER DEFAULT 0")
                await self.conn.commit()
                print("✅ Added games_played_today column to scores table")
            except Exception as e:
                print(f"Migration note: {e}")
        
        # Add last_played_date column to scores if not exists
        try:
            await self.conn.execute("SELECT last_played_date FROM scores LIMIT 1")
        except Exception:
            try:
                await self.conn.execute("ALTER TABLE scores ADD COLUMN last_played_date TEXT")
                await self.conn.commit()
                print("✅ Added last_played_date column to scores table")
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
                print("🔄 Updating online database schema...")
                await self.postgres.init_schema()  # Initialize schema and run migrations
                print("✅ Online database schema updated")
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
        
        # Sync local data to online if both are available
        if self.using_production and self.using_local:
            await self._try_sync_on_connect()
    
    async def _try_sync_on_connect(self) -> None:
        """Try to sync local data to online database on connect. Silent on failure."""
        try:
            # Check if there are local users that don't exist online
            local_users = await self.sqlite.fetch("SELECT username FROM users")
            for local_user in local_users:
                username = local_user['username']
                online_user = await self.postgres.fetchrow(
                    "SELECT user_id FROM users WHERE username = $1", username
                )
                if not online_user:
                    # This user exists locally but not online - sync up
                    print(f"🔄 Syncing local user '{username}' to online...")
                    local_data = await self.sqlite.fetchrow(
                        "SELECT * FROM users WHERE username = $1", username
                    )
                    if local_data:
                        await self._push_user_to_online(local_data)
                else:
                    # User exists in both - sync scores (take highest values)
                    await self._sync_user_scores(username, online_user['user_id'])
            print("✅ Local data synced to online")
        except Exception as e:
            # Silent failure - sync is best effort
            print(f"ℹ️  Sync skipped: {e}")
    
    async def _sync_user_scores(self, username: str, online_user_id: int) -> None:
        """Sync scores for a user that exists in both databases. Takes highest score for each game."""
        try:
            # Get local scores
            local_scores = await self.sqlite.fetchrow("""
                SELECT s.* FROM scores s 
                JOIN users u ON s.user_id = u.user_id 
                WHERE u.username = $1
            """, username)
            
            # Get online scores
            online_scores = await self.postgres.fetchrow(
                "SELECT * FROM scores WHERE user_id = $1", online_user_id
            )
            
            if not local_scores:
                return  # No local scores to sync
            
            if not online_scores:
                # Online has no scores record - create one with local data
                last_login = local_scores.get('last_login_date')
                if isinstance(last_login, str) and last_login:
                    last_login = date.fromisoformat(last_login)
                elif not last_login:
                    last_login = None
                
                await self.postgres.execute("""
                    INSERT INTO scores (user_id, total_score, pacman_score, tetris_score,
                        snake_score, space_invaders_score, hybrid_score, login_streak, 
                        last_login_date, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                """, online_user_id, local_scores.get('total_score', 0),
                    local_scores.get('pacman_score', 0), local_scores.get('tetris_score', 0),
                    local_scores.get('snake_score', 0), local_scores.get('space_invaders_score', 0),
                    local_scores.get('hybrid_score', 0), local_scores.get('login_streak', 0),
                    last_login)
                print(f"  ↑ Created online scores for '{username}'")
                return
            
            # Both have scores - take the HIGHEST value for each game score
            # This ensures scores only go up, never down (prevents data loss)
            merged_scores = {
                'total_score': max(local_scores.get('total_score', 0) or 0, online_scores.get('total_score', 0) or 0),
                'pacman_score': max(local_scores.get('pacman_score', 0) or 0, online_scores.get('pacman_score', 0) or 0),
                'tetris_score': max(local_scores.get('tetris_score', 0) or 0, online_scores.get('tetris_score', 0) or 0),
                'snake_score': max(local_scores.get('snake_score', 0) or 0, online_scores.get('snake_score', 0) or 0),
                'space_invaders_score': max(local_scores.get('space_invaders_score', 0) or 0, online_scores.get('space_invaders_score', 0) or 0),
                'hybrid_score': max(local_scores.get('hybrid_score', 0) or 0, online_scores.get('hybrid_score', 0) or 0),
            }
            
            # Recalculate total score as sum of all game scores
            merged_scores['total_score'] = (
                merged_scores['pacman_score'] + merged_scores['tetris_score'] + 
                merged_scores['snake_score'] + merged_scores['space_invaders_score'] + 
                merged_scores['hybrid_score']
            )
            
            # Take higher login streak
            merged_scores['login_streak'] = max(
                local_scores.get('login_streak', 0) or 0, 
                online_scores.get('login_streak', 0) or 0
            )
            
            # Use more recent last_login_date
            local_login = local_scores.get('last_login_date')
            online_login = online_scores.get('last_login_date')
            if isinstance(local_login, str) and local_login:
                local_login = date.fromisoformat(local_login)
            if isinstance(online_login, str) and online_login:
                online_login = date.fromisoformat(online_login)
            
            if local_login and online_login:
                last_login = max(local_login, online_login)
            else:
                last_login = local_login or online_login
            
            # Update online database with merged scores
            await self.postgres.execute("""
                UPDATE scores SET total_score = $1, pacman_score = $2, tetris_score = $3,
                    snake_score = $4, space_invaders_score = $5, hybrid_score = $6,
                    login_streak = $7, last_login_date = $8, updated_at = NOW()
                WHERE user_id = $9
            """, merged_scores['total_score'], merged_scores['pacman_score'],
                merged_scores['tetris_score'], merged_scores['snake_score'],
                merged_scores['space_invaders_score'], merged_scores['hybrid_score'],
                merged_scores['login_streak'], last_login, online_user_id)
            
            # Also update local database with merged scores (in case online had higher)
            local_user = await self.sqlite.fetchrow(
                "SELECT user_id FROM users WHERE username = $1", username
            )
            if local_user:
                last_login_str = last_login.isoformat() if last_login else None
                await self.sqlite.execute("""
                    UPDATE scores SET total_score = $1, pacman_score = $2, tetris_score = $3,
                        snake_score = $4, space_invaders_score = $5, hybrid_score = $6,
                        login_streak = $7, last_login_date = $8, updated_at = $9
                    WHERE user_id = $10
                """, merged_scores['total_score'], merged_scores['pacman_score'],
                    merged_scores['tetris_score'], merged_scores['snake_score'],
                    merged_scores['space_invaders_score'], merged_scores['hybrid_score'],
                    merged_scores['login_streak'], last_login_str, datetime.now().isoformat(),
                    local_user['user_id'])
            
            print(f"  ↔ Synced scores for '{username}' (merged highest values)")
        except Exception as e:
            print(f"  ⚠️ Failed to sync scores for '{username}': {e}")
    
    async def _push_user_to_online(self, local_user: Dict) -> None:
        """Push a local user to online database."""
        try:
            # Insert user
            user_id = await self.postgres.fetchval("""
                INSERT INTO users (username, email, password_hash, created_at, updated_at)
                VALUES ($1, $2, $3, NOW(), NOW())
                RETURNING user_id
            """, local_user['username'], local_user['email'], local_user['password_hash'])
            
            # Get local scores
            local_scores = await self.sqlite.fetchrow(
                "SELECT * FROM scores WHERE user_id = $1", local_user['user_id']
            )
            
            if local_scores:
                last_login = local_scores.get('last_login_date')
                if isinstance(last_login, str) and last_login:
                    last_login = date.fromisoformat(last_login)
                elif not last_login:
                    last_login = None
                    
                await self.postgres.execute("""
                    INSERT INTO scores (user_id, total_score, pacman_score, tetris_score,
                        snake_score, space_invaders_score, hybrid_score, login_streak, 
                        last_login_date, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                """, user_id, local_scores.get('total_score', 0),
                    local_scores.get('pacman_score', 0), local_scores.get('tetris_score', 0),
                    local_scores.get('snake_score', 0), local_scores.get('space_invaders_score', 0),
                    local_scores.get('hybrid_score', 0), local_scores.get('login_streak', 0),
                    last_login)
            else:
                await self.postgres.execute("""
                    INSERT INTO scores (user_id, updated_at) VALUES ($1, NOW())
                """, user_id)
            
            # Get local settings
            local_settings = await self.sqlite.fetchrow(
                "SELECT * FROM user_settings WHERE user_id = $1", local_user['user_id']
            )
            
            if local_settings:
                await self.postgres.execute("""
                    INSERT INTO user_settings (user_id, difficulty, volume, keybinds, updated_at)
                    VALUES ($1, $2, $3, $4, NOW())
                """, user_id, local_settings.get('difficulty', 'intermediate'),
                    local_settings.get('volume', 100), local_settings.get('keybinds', '{}'))
            else:
                await self.postgres.execute("""
                    INSERT INTO user_settings (user_id, updated_at) VALUES ($1, NOW())
                """, user_id)
            
            print(f"  ↑ User '{local_user['username']}' pushed to online")
        except Exception as e:
            print(f"  ⚠️  Failed to push user: {e}")
    
    async def sync_databases(self) -> None:
        """
        Synchronize local SQLite and online PostgreSQL databases.
        Compares updated_at timestamps and syncs in both directions.
        Call this manually when you want to sync (e.g., on login, on game exit).
        """
        if not self.postgres or not self.postgres.is_connected:
            print("⚠️  PostgreSQL not available, skipping sync")
            return
        if not self.sqlite or not self.sqlite.is_connected:
            print("⚠️  SQLite not available, skipping sync")
            return
        
        print("🔄 Synchronizing databases...")
        
        try:
            await self._sync_users()
        except Exception as e:
            print(f"⚠️  User sync failed: {e}")
        
        try:
            await self._sync_scores()
        except Exception as e:
            print(f"⚠️  Scores sync failed: {e}")
        
        try:
            await self._sync_settings()
        except Exception as e:
            print(f"⚠️  Settings sync failed: {e}")
        
        print("✅ Database sync completed")
    
    async def _parse_timestamp(self, ts) -> Optional[datetime]:
        """Parse timestamp from various formats."""
        if ts is None:
            return None
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except:
                try:
                    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except:
                    return None
        return None
    
    async def _sync_users(self) -> None:
        """Sync users table between local and online."""
        # Get all users from both databases
        local_users = await self.sqlite.fetch("SELECT * FROM users")
        online_users = await self.postgres.fetch("SELECT * FROM users")
        
        # Create lookup by username
        local_by_username = {u['username']: u for u in local_users}
        online_by_username = {u['username']: u for u in online_users}
        
        # Sync each user
        for username, local_user in local_by_username.items():
            if username in online_by_username:
                online_user = online_by_username[username]
                local_ts = await self._parse_timestamp(local_user.get('updated_at'))
                online_ts = await self._parse_timestamp(online_user.get('updated_at'))
                
                if local_ts and online_ts:
                    if local_ts > online_ts:
                        # Local is newer, update online
                        await self._update_user_online(local_user, online_user['user_id'])
                        print(f"  ↑ Synced user '{username}' to online")
                    elif online_ts > local_ts:
                        # Online is newer, update local
                        await self._update_user_local(online_user, local_user['user_id'])
                        print(f"  ↓ Synced user '{username}' to local")
            else:
                # User only exists locally, push to online
                await self._create_user_online(local_user)
                print(f"  ↑ Created user '{username}' online")
        
        # Users that exist only online
        for username, online_user in online_by_username.items():
            if username not in local_by_username:
                await self._create_user_local(online_user)
                print(f"  ↓ Created user '{username}' locally")
    
    async def _update_user_online(self, local_user: Dict, online_user_id: int) -> None:
        """Update online user with local data."""
        query = """
            UPDATE users SET email = $1, password_hash = $2, updated_at = $3
            WHERE user_id = $4
        """
        await self.postgres.execute(
            query,
            local_user['email'],
            local_user['password_hash'],
            datetime.now(),
            online_user_id
        )
    
    async def _update_user_local(self, online_user: Dict, local_user_id: int) -> None:
        """Update local user with online data."""
        query = """
            UPDATE users SET email = $1, password_hash = $2, updated_at = $3
            WHERE user_id = $4
        """
        await self.sqlite.execute(
            query,
            online_user['email'],
            online_user['password_hash'],
            datetime.now().isoformat(),
            local_user_id
        )
    
    async def _create_user_online(self, local_user: Dict) -> None:
        """Create user on online database."""
        # Insert user
        query = """
            INSERT INTO users (username, email, password_hash, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING user_id
        """
        created_at = local_user.get('created_at') or datetime.now()
        if isinstance(created_at, str):
            created_at = await self._parse_timestamp(created_at) or datetime.now()
        
        new_user_id = await self.postgres.fetchval(
            query,
            local_user['username'],
            local_user['email'],
            local_user['password_hash'],
            created_at,
            datetime.now()
        )
        
        # Get local scores and settings
        local_scores = await self.sqlite.fetchrow(
            "SELECT * FROM scores WHERE user_id = $1", local_user['user_id']
        )
        local_settings = await self.sqlite.fetchrow(
            "SELECT * FROM user_settings WHERE user_id = $1", local_user['user_id']
        )
        
        # Create scores entry
        if local_scores:
            await self.postgres.execute("""
                INSERT INTO scores (user_id, total_score, pacman_score, tetris_score, 
                    snake_score, space_invaders_score, hybrid_score, login_streak, 
                    last_login_date, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """, new_user_id, local_scores.get('total_score', 0),
                local_scores.get('pacman_score', 0), local_scores.get('tetris_score', 0),
                local_scores.get('snake_score', 0), local_scores.get('space_invaders_score', 0),
                local_scores.get('hybrid_score', 0), local_scores.get('login_streak', 0),
                local_scores.get('last_login_date'), datetime.now())
        else:
            await self.postgres.execute("""
                INSERT INTO scores (user_id, updated_at) VALUES ($1, $2)
            """, new_user_id, datetime.now())
        
        # Create settings entry
        if local_settings:
            await self.postgres.execute("""
                INSERT INTO user_settings (user_id, difficulty, volume, keybinds, updated_at)
                VALUES ($1, $2, $3, $4, $5)
            """, new_user_id, local_settings.get('difficulty', 'intermediate'),
                local_settings.get('volume', 100), local_settings.get('keybinds', '{}'),
                datetime.now())
        else:
            await self.postgres.execute("""
                INSERT INTO user_settings (user_id, updated_at) VALUES ($1, $2)
            """, new_user_id, datetime.now())
    
    async def _create_user_local(self, online_user: Dict) -> None:
        """Create user on local database."""
        # Insert user
        query = """
            INSERT INTO users (username, email, password_hash, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5)
        """
        created_at = online_user.get('created_at')
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        
        await self.sqlite.execute(
            query,
            online_user['username'],
            online_user['email'],
            online_user['password_hash'],
            created_at or datetime.now().isoformat(),
            datetime.now().isoformat()
        )
        
        new_user_id = await self.sqlite.fetchval("SELECT last_insert_rowid()")
        
        # Get online scores and settings
        online_scores = await self.postgres.fetchrow(
            "SELECT * FROM scores WHERE user_id = $1", online_user['user_id']
        )
        online_settings = await self.postgres.fetchrow(
            "SELECT * FROM user_settings WHERE user_id = $1", online_user['user_id']
        )
        
        # Create scores entry
        if online_scores:
            last_login = online_scores.get('last_login_date')
            if isinstance(last_login, date):
                last_login = last_login.isoformat()
            await self.sqlite.execute("""
                INSERT INTO scores (user_id, total_score, pacman_score, tetris_score, 
                    snake_score, space_invaders_score, hybrid_score, login_streak, 
                    last_login_date, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """, new_user_id, online_scores.get('total_score', 0),
                online_scores.get('pacman_score', 0), online_scores.get('tetris_score', 0),
                online_scores.get('snake_score', 0), online_scores.get('space_invaders_score', 0),
                online_scores.get('hybrid_score', 0), online_scores.get('login_streak', 0),
                last_login, datetime.now().isoformat())
        else:
            await self.sqlite.execute("""
                INSERT INTO scores (user_id, updated_at) VALUES ($1, $2)
            """, new_user_id, datetime.now().isoformat())
        
        # Create settings entry
        if online_settings:
            await self.sqlite.execute("""
                INSERT INTO user_settings (user_id, difficulty, volume, keybinds, updated_at)
                VALUES ($1, $2, $3, $4, $5)
            """, new_user_id, online_settings.get('difficulty', 'intermediate'),
                online_settings.get('volume', 100), online_settings.get('keybinds', '{}'),
                datetime.now().isoformat())
        else:
            await self.sqlite.execute("""
                INSERT INTO user_settings (user_id, updated_at) VALUES ($1, $2)
            """, new_user_id, datetime.now().isoformat())
    
    async def _sync_scores(self) -> None:
        """Sync scores table between local and online. Takes highest values to prevent data loss."""
        # Get all scores with usernames for matching
        local_scores = await self.sqlite.fetch("""
            SELECT s.*, u.username FROM scores s 
            JOIN users u ON s.user_id = u.user_id
        """)
        online_scores = await self.postgres.fetch("""
            SELECT s.*, u.username FROM scores s 
            JOIN users u ON s.user_id = u.user_id
        """)
        
        local_by_username = {s['username']: s for s in local_scores}
        online_by_username = {s['username']: s for s in online_scores}
        
        for username, local_score in local_by_username.items():
            if username in online_by_username:
                online_score = online_by_username[username]
                
                # Merge scores - take HIGHEST value for each game to prevent data loss
                merged_scores = {
                    'pacman_score': max(local_score.get('pacman_score', 0) or 0, online_score.get('pacman_score', 0) or 0),
                    'tetris_score': max(local_score.get('tetris_score', 0) or 0, online_score.get('tetris_score', 0) or 0),
                    'snake_score': max(local_score.get('snake_score', 0) or 0, online_score.get('snake_score', 0) or 0),
                    'space_invaders_score': max(local_score.get('space_invaders_score', 0) or 0, online_score.get('space_invaders_score', 0) or 0),
                    'hybrid_score': max(local_score.get('hybrid_score', 0) or 0, online_score.get('hybrid_score', 0) or 0),
                }
                
                # Recalculate total score
                merged_scores['total_score'] = sum([
                    merged_scores['pacman_score'], merged_scores['tetris_score'],
                    merged_scores['snake_score'], merged_scores['space_invaders_score'],
                    merged_scores['hybrid_score']
                ])
                
                # Take higher login streak
                merged_scores['login_streak'] = max(
                    local_score.get('login_streak', 0) or 0,
                    online_score.get('login_streak', 0) or 0
                )
                
                # Use more recent last_login_date
                local_login = local_score.get('last_login_date')
                online_login = online_score.get('last_login_date')
                if isinstance(local_login, str) and local_login:
                    local_login = date.fromisoformat(local_login)
                if isinstance(online_login, str) and online_login:
                    online_login = date.fromisoformat(online_login)
                if isinstance(local_login, date) and isinstance(online_login, date):
                    last_login = max(local_login, online_login)
                else:
                    last_login = local_login or online_login
                
                # Update online with merged scores
                last_login_for_pg = last_login
                if isinstance(last_login_for_pg, str):
                    last_login_for_pg = date.fromisoformat(last_login_for_pg)
                    
                await self.postgres.execute("""
                    UPDATE scores SET total_score = $1, pacman_score = $2, tetris_score = $3,
                        snake_score = $4, space_invaders_score = $5, hybrid_score = $6,
                        login_streak = $7, last_login_date = $8, updated_at = NOW()
                    WHERE user_id = $9
                """, merged_scores['total_score'], merged_scores['pacman_score'],
                    merged_scores['tetris_score'], merged_scores['snake_score'],
                    merged_scores['space_invaders_score'], merged_scores['hybrid_score'],
                    merged_scores['login_streak'], last_login_for_pg, online_score['user_id'])
                
                # Update local with merged scores
                last_login_str = last_login.isoformat() if isinstance(last_login, date) else last_login
                await self.sqlite.execute("""
                    UPDATE scores SET total_score = $1, pacman_score = $2, tetris_score = $3,
                        snake_score = $4, space_invaders_score = $5, hybrid_score = $6,
                        login_streak = $7, last_login_date = $8, updated_at = $9
                    WHERE user_id = $10
                """, merged_scores['total_score'], merged_scores['pacman_score'],
                    merged_scores['tetris_score'], merged_scores['snake_score'],
                    merged_scores['space_invaders_score'], merged_scores['hybrid_score'],
                    merged_scores['login_streak'], last_login_str, datetime.now().isoformat(),
                    local_score['user_id'])
                
                print(f"  ↔ Merged scores for '{username}'")
    
    async def _update_scores_online(self, local_score: Dict, online_user_id: int) -> None:
        """Update online scores with local data."""
        last_login = local_score.get('last_login_date')
        if isinstance(last_login, str) and last_login:
            last_login = date.fromisoformat(last_login)
        
        await self.postgres.execute("""
            UPDATE scores SET total_score = $1, pacman_score = $2, tetris_score = $3,
                snake_score = $4, space_invaders_score = $5, hybrid_score = $6,
                login_streak = $7, last_login_date = $8, updated_at = $9
            WHERE user_id = $10
        """, local_score.get('total_score', 0), local_score.get('pacman_score', 0),
            local_score.get('tetris_score', 0), local_score.get('snake_score', 0),
            local_score.get('space_invaders_score', 0), local_score.get('hybrid_score', 0),
            local_score.get('login_streak', 0), last_login, datetime.now(), online_user_id)
    
    async def _update_scores_local(self, online_score: Dict, local_user_id: int) -> None:
        """Update local scores with online data."""
        last_login = online_score.get('last_login_date')
        if isinstance(last_login, date):
            last_login = last_login.isoformat()
        
        await self.sqlite.execute("""
            UPDATE scores SET total_score = $1, pacman_score = $2, tetris_score = $3,
                snake_score = $4, space_invaders_score = $5, hybrid_score = $6,
                login_streak = $7, last_login_date = $8, updated_at = $9
            WHERE user_id = $10
        """, online_score.get('total_score', 0), online_score.get('pacman_score', 0),
            online_score.get('tetris_score', 0), online_score.get('snake_score', 0),
            online_score.get('space_invaders_score', 0), online_score.get('hybrid_score', 0),
            online_score.get('login_streak', 0), last_login, datetime.now().isoformat(),
            local_user_id)
    
    async def _sync_settings(self) -> None:
        """Sync user_settings table between local and online."""
        local_settings = await self.sqlite.fetch("""
            SELECT s.*, u.username FROM user_settings s 
            JOIN users u ON s.user_id = u.user_id
        """)
        online_settings = await self.postgres.fetch("""
            SELECT s.*, u.username FROM user_settings s 
            JOIN users u ON s.user_id = u.user_id
        """)
        
        local_by_username = {s['username']: s for s in local_settings}
        online_by_username = {s['username']: s for s in online_settings}
        
        for username, local_setting in local_by_username.items():
            if username in online_by_username:
                online_setting = online_by_username[username]
                local_ts = await self._parse_timestamp(local_setting.get('updated_at'))
                online_ts = await self._parse_timestamp(online_setting.get('updated_at'))
                
                if local_ts and online_ts:
                    if local_ts > online_ts:
                        await self._update_settings_online(local_setting, online_setting['user_id'])
                        print(f"  ↑ Synced settings for '{username}' to online")
                    elif online_ts > local_ts:
                        await self._update_settings_local(online_setting, local_setting['user_id'])
                        print(f"  ↓ Synced settings for '{username}' to local")
    
    async def _update_settings_online(self, local_setting: Dict, online_user_id: int) -> None:
        """Update online settings with local data."""
        await self.postgres.execute("""
            UPDATE user_settings SET difficulty = $1, volume = $2, keybinds = $3, updated_at = $4
            WHERE user_id = $5
        """, local_setting.get('difficulty', 'intermediate'),
            local_setting.get('volume', 100), local_setting.get('keybinds', '{}'),
            datetime.now(), online_user_id)
    
    async def _update_settings_local(self, online_setting: Dict, local_user_id: int) -> None:
        """Update local settings with online data."""
        await self.sqlite.execute("""
            UPDATE user_settings SET difficulty = $1, volume = $2, keybinds = $3, updated_at = $4
            WHERE user_id = $5
        """, online_setting.get('difficulty', 'intermediate'),
            online_setting.get('volume', 100), online_setting.get('keybinds', '{}'),
            datetime.now().isoformat(), local_user_id)
    
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
        # Use PostgreSQL path if production is active, otherwise SQLite
        if self.using_production:
            # PostgreSQL path
            query = """
                INSERT INTO users (username, email, password_hash, created_at, updated_at)
                VALUES ($1, $2, $3, NOW(), NOW())
                RETURNING user_id
            """
            try:
                user_id = await self.fetchval(query, username, email, password_hash)
                await self._init_user_data(user_id)
                
                # Also save to local SQLite backup
                if self.sqlite and self.sqlite.is_connected:
                    await self._backup_user_to_local(username, email, password_hash)
                
                return user_id
            except Exception as e:
                print(f"Error creating user: {e}")
                return None  # Username or email already exists
        else:
            # SQLite only path
            try:
                check_query = "SELECT user_id FROM users WHERE username = $1 OR email = $2"
                existing = await self.fetchrow(check_query, username, email)
                if existing:
                    return None  # Already exists
                
                insert_query = """
                    INSERT INTO users (username, email, password_hash, updated_at)
                    VALUES ($1, $2, $3, $4)
                """
                await self.execute(insert_query, username, email, password_hash, datetime.now().isoformat())
                
                # Get the last inserted ID
                user_id = await self.fetchval("SELECT last_insert_rowid()")
                await self._init_user_data(user_id)
                return user_id
            except Exception as e:
                print(f"Error creating user: {e}")
                return None
    
    async def _backup_user_to_local(self, username: str, email: str, password_hash: str) -> None:
        """Backup user to local SQLite database."""
        try:
            now_str = datetime.now().isoformat()
            
            # Check if user already exists locally
            existing = await self.sqlite.fetchrow(
                "SELECT user_id FROM users WHERE username = $1", username
            )
            if existing:
                return  # Already backed up
            
            # Insert user
            await self.sqlite.execute("""
                INSERT INTO users (username, email, password_hash, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5)
            """, username, email, password_hash, now_str, now_str)
            
            # Get local user_id
            local_user_id = await self.sqlite.fetchval("SELECT last_insert_rowid()")
            
            # Initialize scores and settings
            await self.sqlite.execute("""
                INSERT INTO scores (user_id, total_score, pacman_score, tetris_score,
                    snake_score, space_invaders_score, hybrid_score, login_streak, last_login_date, updated_at)
                VALUES ($1, 0, 0, 0, 0, 0, 0, 0, NULL, $2)
            """, local_user_id, now_str)
            
            await self.sqlite.execute("""
                INSERT INTO user_settings (user_id, difficulty, volume, keybinds, updated_at)
                VALUES ($1, 'intermediate', 100, '{}', $2)
            """, local_user_id, now_str)
            
            print(f"💾 User backed up to local database")
        except Exception as e:
            print(f"⚠️  Local backup failed: {e}")
    
    async def _init_user_data(self, user_id: int) -> None:
        """Initialize default scores and settings for new user."""
        # Use datetime object for PostgreSQL, ISO string for SQLite
        if self.using_production:
            now_val = datetime.now()
        else:
            now_val = datetime.now().isoformat()
        
        scores_query = """
            INSERT INTO scores (user_id, total_score, pacman_score, tetris_score, 
                              snake_score, space_invaders_score, hybrid_score, login_streak, last_login_date, updated_at)
            VALUES ($1, 0, 0, 0, 0, 0, 0, 0, NULL, $2)
        """
        settings_query = """
            INSERT INTO user_settings (user_id, difficulty, volume, keybinds, updated_at)
            VALUES ($1, 'intermediate', 100, '{}', $2)
        """
        await self.execute(scores_query, user_id, now_val)
        await self.execute(settings_query, user_id, now_val)
    
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
        # Use proper types based on backend
        if self.using_production:
            # PostgreSQL expects date and timestamp objects
            query = """
                UPDATE scores 
                SET login_streak = $1, last_login_date = $2, updated_at = $3
                WHERE user_id = $4
            """
            await self.execute(query, new_streak, today, datetime.now(), user_id)
        else:
            # SQLite uses strings
            query = """
                UPDATE scores 
                SET login_streak = $1, last_login_date = $2, updated_at = $3
                WHERE user_id = $4
            """
            await self.execute(query, new_streak, today.isoformat(), datetime.now().isoformat(), user_id)
        
        # Also update on backup database if using production
        if self.using_production and self.sqlite and self.sqlite.is_connected:
            try:
                backup_query = """
                    UPDATE scores 
                    SET login_streak = $1, last_login_date = $2, updated_at = $3
                    WHERE user_id = $4
                """
                await self.sqlite.execute(backup_query, new_streak, today.isoformat(), datetime.now().isoformat(), user_id)
            except Exception:
                pass
        
        return new_streak
    
    async def increment_daily_games(self, user_id: int) -> int:
        """Increment games played today counter. Resets if it's a new day.
        Returns the new games_played_today count (capped at 10 for bonus purposes)."""
        today = date.today()
        
        # Get last played date and current count
        query = "SELECT last_played_date, games_played_today FROM scores WHERE user_id = $1"
        row = await self.fetchrow(query, user_id)
        
        new_count = 1
        if row:
            last_played_str = row.get('last_played_date')
            current_count = row.get('games_played_today') or 0
            
            if last_played_str:
                # Parse date - handle both date object and string
                if isinstance(last_played_str, str):
                    last_played = date.fromisoformat(last_played_str)
                else:
                    last_played = last_played_str
                
                if last_played == today:
                    # Same day - increment counter
                    new_count = current_count + 1
                else:
                    # New day - reset counter
                    new_count = 1
        
        # Update the counter
        if self.using_production:
            query = """
                UPDATE scores 
                SET games_played_today = $1, last_played_date = $2, updated_at = $3
                WHERE user_id = $4
            """
            await self.execute(query, new_count, today, datetime.now(), user_id)
        else:
            query = """
                UPDATE scores 
                SET games_played_today = $1, last_played_date = $2, updated_at = $3
                WHERE user_id = $4
            """
            await self.execute(query, new_count, today.isoformat(), datetime.now().isoformat(), user_id)
        
        # Also update backup if using production
        if self.using_production and self.sqlite and self.sqlite.is_connected:
            try:
                backup_query = """
                    UPDATE scores 
                    SET games_played_today = $1, last_played_date = $2, updated_at = $3
                    WHERE user_id = $4
                """
                await self.sqlite.execute(backup_query, new_count, today.isoformat(), datetime.now().isoformat(), user_id)
            except Exception:
                pass
        
        return new_count
    
    async def get_user_streaks(self, user_id: int) -> tuple[int, int]:
        """Get user's login streak and games played today.
        Returns (login_streak, games_played_today)."""
        query = """
            SELECT login_streak, games_played_today, last_played_date
            FROM scores WHERE user_id = $1
        """
        row = await self.fetchrow(query, user_id)
        
        if not row:
            return (0, 0)
        
        login_streak = row.get('login_streak') or 0
        games_played_today = row.get('games_played_today') or 0
        last_played_str = row.get('last_played_date')
        
        # Reset games_played_today if it's a different day
        if last_played_str:
            if isinstance(last_played_str, str):
                last_played = date.fromisoformat(last_played_str)
            else:
                last_played = last_played_str
            
            if last_played != date.today():
                games_played_today = 0
        else:
            games_played_today = 0
        
        return (login_streak, games_played_today)
    
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
            # Determine the timestamp format based on backend
            if isinstance(backend, SQLiteBackend):
                now_str = datetime.now().isoformat()
            else:
                now_str = datetime.now()
            
            # Update game score with updated_at timestamp
            update_query = f"UPDATE scores SET {game_col} = $1, updated_at = $2 WHERE user_id = $3"
            await backend.execute(update_query, score, now_str, user_id)
            
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
            # Add updated_at timestamp
            now_str = datetime.now().isoformat() if self.using_local and not self.using_production else datetime.now()
            updates.append(f"updated_at = ${param_num}")
            values.append(now_str)
            param_num += 1
            
            values.append(user_id)
            query = f"UPDATE user_settings SET {', '.join(updates)} WHERE user_id = ${param_num}"
            await self.execute(query, *values)
            
            # Also update on backup database if using production
            if self.using_production and self.sqlite and self.sqlite.is_connected:
                try:
                    # Reset for SQLite with string timestamp
                    sqlite_values = values[:-2]  # Remove the datetime and user_id
                    sqlite_values.append(datetime.now().isoformat())
                    sqlite_values.append(user_id)
                    await self.sqlite.execute(query, *sqlite_values)
                except Exception:
                    pass


# Global instance (initialized in main.py)
db: Optional[DatabaseManager] = None
