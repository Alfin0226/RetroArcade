from __future__ import annotations
from typing import Optional, Dict
import bcrypt
import asyncio


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


async def register_user_async(db, username: str, email: str, password: str) -> Optional[int]:
    """
    Register a new user with username, email and password.
    Returns user_id if successful, None if username/email already exists.
    """
    password_hash = hash_password(password)
    return await db.create_user(username, email, password_hash)


async def login_user_async(db, identifier: str, password: str) -> Optional[Dict]:
    """
    Login user with username OR email and password.
    Returns user data dict if successful, None otherwise.
    """
    # Try to find user by username first
    user = await db.get_user_by_username(identifier)
    
    # If not found, try by email
    if not user:
        user = await db.get_user_by_email(identifier)
    
    if not user:
        return None
    
    # Verify password
    if verify_password(password, user['password_hash']):
        # Update login streak
        await db.update_login_streak(user['user_id'])
        return user
    
    return None


def register_user(username: str, password: str) -> bool:
    """Legacy sync register (deprecated - use register_user_async)."""
    # This is kept for backward compatibility
    return False


def login_user(username: str, password: str) -> bool:
    """Legacy sync login (deprecated - use login_user_async)."""
    # This is kept for backward compatibility  
    return False


class UserSession:
    """Holds the current logged-in user's session data."""
    
    def __init__(self):
        self.user_id: Optional[int] = None
        self.username: Optional[str] = None
        self.email: Optional[str] = None
        self.is_logged_in: bool = False
    
    def login(self, user_data: Dict) -> None:
        """Set session from user data dict."""
        self.user_id = user_data.get('user_id')
        self.username = user_data.get('username')
        self.email = user_data.get('email')
        self.is_logged_in = True
    
    def logout(self) -> None:
        """Clear session data."""
        self.user_id = None
        self.username = None
        self.email = None
        self.is_logged_in = False
    
    def __repr__(self) -> str:
        if self.is_logged_in:
            return f"UserSession(user={self.username}, id={self.user_id})"
        return "UserSession(logged_out)"

