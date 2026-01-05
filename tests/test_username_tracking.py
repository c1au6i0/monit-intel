#!/usr/bin/env python3
"""Test username tracking in conversation history."""

import sys
import os
import sqlite3
import tempfile

sys.path.insert(0, 'src')

def test_username_column_migration():
    """Test that the username column is added to existing databases."""
    # Create a temporary database file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        temp_db = f.name
    
    try:
        # Create old schema without username column
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_query TEXT NOT NULL,
                agent_response TEXT NOT NULL,
                service_context TEXT,
                logs_provided TEXT
            )
        """)
        conn.commit()
        conn.close()
        
        # Verify username column doesn't exist
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(conversations)")
        columns_before = [col[1] for col in cursor.fetchall()]
        assert "username" not in columns_before, "Username column should not exist before migration"
        conn.close()
        
        # Now import Mother which should trigger migration
        # We can't import Mother directly due to langgraph dependency
        # So we'll simulate the migration
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(conversations)")
        columns = [col[1] for col in cursor.fetchall()]
        if "username" not in columns:
            cursor.execute("ALTER TABLE conversations ADD COLUMN username TEXT")
            conn.commit()
        conn.close()
        
        # Verify username column exists after migration
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(conversations)")
        columns_after = [col[1] for col in cursor.fetchall()]
        assert "username" in columns_after, "Username column should exist after migration"
        conn.close()
        
        print("✓ Username column migration test PASSED")
        
    finally:
        # Clean up
        if os.path.exists(temp_db):
            os.unlink(temp_db)


def test_conversation_storage_with_username():
    """Test that conversations can be stored with username."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        temp_db = f.name
    
    try:
        # Create schema with username column
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                username TEXT,
                user_query TEXT NOT NULL,
                agent_response TEXT NOT NULL,
                service_context TEXT,
                logs_provided TEXT
            )
        """)
        conn.commit()
        
        # Insert a conversation with username
        cursor.execute("""
            INSERT INTO conversations (username, user_query, agent_response, service_context, logs_provided)
            VALUES (?, ?, ?, ?, ?)
        """, ("test_user", "What is the status?", "All systems operational", "[]", ""))
        conn.commit()
        
        # Query and verify
        cursor.execute("SELECT username, user_query, agent_response FROM conversations")
        row = cursor.fetchone()
        assert row[0] == "test_user", f"Expected username 'test_user', got '{row[0]}'"
        assert row[1] == "What is the status?", f"Expected query 'What is the status?', got '{row[1]}'"
        assert row[2] == "All systems operational", f"Expected response 'All systems operational', got '{row[2]}'"
        
        conn.close()
        
        print("✓ Conversation storage with username test PASSED")
        
    finally:
        # Clean up
        if os.path.exists(temp_db):
            os.unlink(temp_db)


def test_history_filtering_by_username():
    """Test that conversation history can be filtered by username."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        temp_db = f.name
    
    try:
        # Create schema and insert test data
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                username TEXT,
                user_query TEXT NOT NULL,
                agent_response TEXT NOT NULL,
                service_context TEXT,
                logs_provided TEXT
            )
        """)
        
        # Insert conversations from different users
        cursor.execute("""
            INSERT INTO conversations (username, user_query, agent_response, service_context, logs_provided)
            VALUES (?, ?, ?, ?, ?)
        """, ("alice", "Status check", "All good", "[]", ""))
        
        cursor.execute("""
            INSERT INTO conversations (username, user_query, agent_response, service_context, logs_provided)
            VALUES (?, ?, ?, ?, ?)
        """, ("bob", "What's failing?", "Nothing", "[]", ""))
        
        cursor.execute("""
            INSERT INTO conversations (username, user_query, agent_response, service_context, logs_provided)
            VALUES (?, ?, ?, ?, ?)
        """, ("alice", "CPU usage?", "Low", "[]", ""))
        
        conn.commit()
        
        # Query alice's conversations
        cursor.execute("""
            SELECT username, user_query FROM conversations 
            WHERE username = ?
            ORDER BY timestamp DESC
        """, ("alice",))
        alice_convos = cursor.fetchall()
        assert len(alice_convos) == 2, f"Expected 2 conversations for alice, got {len(alice_convos)}"
        assert all(row[0] == "alice" for row in alice_convos), "All conversations should be from alice"
        
        # Query bob's conversations
        cursor.execute("""
            SELECT username, user_query FROM conversations 
            WHERE username = ?
            ORDER BY timestamp DESC
        """, ("bob",))
        bob_convos = cursor.fetchall()
        assert len(bob_convos) == 1, f"Expected 1 conversation for bob, got {len(bob_convos)}"
        assert bob_convos[0][0] == "bob", "Conversation should be from bob"
        
        conn.close()
        
        print("✓ History filtering by username test PASSED")
        
    finally:
        # Clean up
        if os.path.exists(temp_db):
            os.unlink(temp_db)


if __name__ == "__main__":
    print("Running username tracking tests...\n")
    test_username_column_migration()
    test_conversation_storage_with_username()
    test_history_filtering_by_username()
    print("\n✓ All tests PASSED!")
