"""
Run this script once to set up the database tables.
Usage: python init_db.py

The database manager will:
1. Initialize local SQLite database (always)
2. Initialize PostgreSQL (production) if available
3. Both databases will be ready for use
"""
import asyncio
from database import DatabaseManager, SQLiteBackend, PostgresBackend
from settings import Settings, DATA_DIR

async def main():
    print("🔧 Initializing databases...")
    print("   - Local SQLite (offline backup)")
    print("   - PostgreSQL (online production)")
    print()
    
    cfg = Settings()
    
    # ===== Initialize Local SQLite =====
    print("📁 Setting up Local SQLite database...")
    local_db_path = DATA_DIR / "arcade.db"
    sqlite = SQLiteBackend(local_db_path)
    
    if await sqlite.connect():
        await sqlite.init_schema()
        print(f"✅ Local SQLite initialized at {local_db_path}")
    else:
        print("❌ Failed to initialize local SQLite!")
    
    await sqlite.disconnect()
    
    # ===== Initialize PostgreSQL =====
    print("\n🌐 Setting up PostgreSQL (online) database...")
    if cfg.db.is_configured:
        postgres = PostgresBackend(cfg.db)
        if await postgres.connect():
            await postgres.init_schema()
            print("✅ PostgreSQL initialized successfully")
            await postgres.disconnect()
        else:
            print("⚠️  PostgreSQL connection failed (will use local only)")
    else:
        print("ℹ️  PostgreSQL not configured (no .env file or missing credentials)")
    
    # ===== Now test with full DatabaseManager =====
    print("\n" + "="*50)
    print("🧪 Testing full database connection...")
    print("="*50)
    
    db = DatabaseManager(cfg.db)
    
    try:
        await db.connect()
        
        if not db.is_connected:
            print("❌ Failed to connect to any database!")
            return
        
        print(f"\n✅ Database setup complete!")
        print(f"   Primary: {db.backend_name}")
        print(f"   Local backup: {'Yes' if db.using_local else 'No'}")
        print(f"   Online sync: {'Yes' if db.using_production else 'No'}")
        
        # Test user creation
        print("\n🧪 Testing user registration...")
        user_id = await db.create_user("TestPlayer", "test@example.com", "hashed_password_123")
        if user_id:
            print(f"✅ Test user created with ID: {user_id}")
            
            # Test score update
            print("\n🎮 Testing score update...")
            await db.update_game_score(user_id, "tetris", 5000)
            scores = await db.get_user_scores(user_id)
            print(f"📊 User scores: {scores}")
            
            # Test settings
            print("\n⚙️  Testing user settings...")
            await db.update_user_settings(user_id, difficulty="hard", volume=80)
            settings = await db.get_user_settings(user_id)
            print(f"⚙️  User settings: {settings}")
            
            # Test leaderboard
            print("\n🏆 Testing leaderboard...")
            leaderboard = await db.get_global_leaderboard(limit=5)
            print(f"🏆 Global leaderboard: {leaderboard}")
        else:
            print("ℹ️  Test user already exists (this is okay)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
