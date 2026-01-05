"""
Chat authentication management - separate from Monit API credentials.
Stores chat UI credentials in SQLite database with password hashing.
"""

import sqlite3
import hashlib
import secrets
from pathlib import Path

DB_PATH = "monit_history.db"


def hash_password(password: str, salt: str = None) -> tuple:
    """Hash password with salt. Returns (hashed_password, salt)."""
    if salt is None:
        salt = secrets.token_hex(16)
    
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return hashed.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify password against stored hash."""
    hashed, _ = hash_password(password, salt)
    # Constant-time comparison to avoid timing attacks
    return secrets.compare_digest(hashed, stored_hash)


def init_chat_credentials_table():
    """Create chat_credentials table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_credentials (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


def set_chat_credentials(username: str, password: str):
    """Set or update chat credentials."""
    init_chat_credentials_table()
    
    hashed, salt = hash_password(password)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Try to update existing, or insert if new
    cursor.execute("""
        INSERT OR REPLACE INTO chat_credentials (username, password_hash, salt)
        VALUES (?, ?, ?)
    """, (username, hashed, salt))
    
    conn.commit()
    conn.close()
    
    print(f"✓ Chat credentials set: {username}")


def verify_chat_credentials(username: str, password: str) -> bool:
    """Verify chat credentials against database."""
    init_chat_credentials_table()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT password_hash, salt FROM chat_credentials WHERE username = ?",
        (username,)
    )
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return False
    
    stored_hash, salt = result
    return verify_password(password, stored_hash, salt)


def get_chat_credentials_status() -> dict:
    """Get status of chat credentials."""
    init_chat_credentials_table()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM chat_credentials")
    count = cursor.fetchone()[0]
    conn.close()
    
    return {
        "configured": count > 0,
        "count": count
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        status = get_chat_credentials_status()
        print("Chat Authentication Status:")
        print(f"  Configured: {status['configured']}")
        print(f"  Credentials count: {status['count']}")
        print()
        print("Usage: python chat_auth.py <username> <password>")
        print("Example: python chat_auth.py admin mysecurepassword")
        sys.exit(0)
    
    username = sys.argv[1]
    password = sys.argv[2]
    set_chat_credentials(username, password)
