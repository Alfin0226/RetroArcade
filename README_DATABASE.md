# Database Setup Guide

## 1. Create Neon Database

1. Go to [Neon Console](https://console.neon.tech/)
2. Create a new project
3. Copy your connection string (looks like: `postgresql://user:pass@host/db?sslmode=require`)

## 2. Configure Environment

1. Copy `.env.example` to `.env`:
   ```bash
   copy .env.example .env
   ```

2. Edit `.env` and paste your Neon connection string:
   ```
   DATABASE_URL=postgresql://your_actual_connection_string
   ```

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## 4. Initialize Schema

Run this once to create tables:

```python
import asyncio
from database import DatabaseManager
from settings import Settings

async def setup():
    cfg = Settings()
    db = DatabaseManager(cfg.db)
    await db.connect()
    await db.init_schema()
    await db.disconnect()

asyncio.run(setup())
```

## 5. Usage Example

```python
# In your game code:
import asyncio
from database import db

# Save score
asyncio.run(db.save_score("Player1", "tetris", 5000, 10))

# Get leaderboard
leaderboard = asyncio.run(db.get_leaderboard("tetris", limit=10))
for entry in leaderboard:
    print(f"{entry['player_name']}: {entry['score']}")
```

## Notes

- Neon uses SSL by default (`?sslmode=require` in connection string)
- Connection pool keeps 2-10 connections alive
- All queries are async (use `asyncio.run()` or `await`)
- Schema auto-creates on first `init_schema()` call
