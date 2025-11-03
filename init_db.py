"""
Run this script once to set up the database tables.
Usage: python init_db.py
"""
import asyncio
from database import DatabaseManager
from settings import Settings

async def main():
    print("🔧 Initializing database with users, scores, and user_settings tables...")
    cfg = Settings()
    
    if not cfg.db.is_configured:
        print("❌ Database not configured. Please check your .env file.")
        return
    
    db = DatabaseManager(cfg.db)
    
    try:
        await db.connect()
        await db.init_schema()
        print("✅ Database setup complete!")
        
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
