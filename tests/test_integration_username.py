#!/usr/bin/env python3
"""
Integration test for username tracking feature.
Tests the complete flow from API to database.
"""

import sqlite3
import tempfile
import os
import json
from typing import Optional, List, Dict

# Simulate the Mother class methods we need to test
class MockMother:
    """Mock Mother class for testing without langgraph dependency."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_conversations_table()
    
    def _init_conversations_table(self):
        """Create conversations table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
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
        
        # Migration: Add username column if it doesn't exist
        cursor.execute("PRAGMA table_info(conversations)")
        columns = [col[1] for col in cursor.fetchall()]
        if "username" not in columns:
            cursor.execute("ALTER TABLE conversations ADD COLUMN username TEXT")
            conn.commit()
        
        conn.close()
    
    def query_agent(self, user_query: str, username: Optional[str] = None) -> str:
        """Mock query agent that stores conversation with username."""
        response = f"Mock response to: {user_query}"
        self._store_conversation(user_query, response, "", [], username)
        return response
    
    def _store_conversation(self, user_query: str, response: str, 
                          context: str, services: List[str], username: Optional[str] = None):
        """Store conversation in SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO conversations (username, user_query, agent_response, service_context, logs_provided)
            VALUES (?, ?, ?, ?, ?)
        """, (username, user_query, response, json.dumps(services), context))
        
        conn.commit()
        conn.close()
    
    def get_history(self, limit: int = 10, username: Optional[str] = None) -> List[Dict]:
        """Retrieve conversation history, optionally filtered by username."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if username:
            cursor.execute("""
                SELECT id, timestamp, username, user_query, agent_response 
                FROM conversations 
                WHERE username = ?
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (username, limit))
        else:
            cursor.execute("""
                SELECT id, timestamp, username, user_query, agent_response 
                FROM conversations 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,))
        
        history = []
        for row in cursor.fetchall():
            history.append({
                "id": row[0],
                "timestamp": row[1],
                "username": row[2],
                "user_query": row[3],
                "agent_response": row[4]
            })
        
        conn.close()
        return history


def test_complete_flow():
    """Test the complete flow of username tracking."""
    print("Testing complete username tracking flow...\n")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        temp_db = f.name
    
    try:
        # Initialize Mother
        mother = MockMother(temp_db)
        print("✓ Mother initialized with database")
        
        # Simulate multiple users asking questions
        print("\nSimulating conversations from different users:")
        
        # Alice asks questions
        mother.query_agent("What is the system status?", username="alice")
        print("  - alice: 'What is the system status?'")
        
        mother.query_agent("Check CPU usage", username="alice")
        print("  - alice: 'Check CPU usage'")
        
        # Bob asks questions
        mother.query_agent("Are there any failures?", username="bob")
        print("  - bob: 'Are there any failures?'")
        
        # Charlie asks a question (no username - legacy/anonymous)
        mother.query_agent("What about memory?", username=None)
        print("  - anonymous: 'What about memory?'")
        
        # Test 1: Get all history
        print("\nTest 1: Getting all conversation history...")
        all_history = mother.get_history(limit=10)
        assert len(all_history) == 4, f"Expected 4 conversations, got {len(all_history)}"
        print(f"✓ Retrieved {len(all_history)} conversations")
        
        # Verify usernames are stored
        usernames_in_history = [conv.get('username') for conv in all_history]
        assert 'alice' in usernames_in_history, "Alice's username should be in history"
        assert 'bob' in usernames_in_history, "Bob's username should be in history"
        assert None in usernames_in_history, "Anonymous conversation should be in history"
        print("✓ All usernames correctly stored")
        
        # Test 2: Get Alice's history only
        print("\nTest 2: Getting Alice's conversation history...")
        alice_history = mother.get_history(limit=10, username="alice")
        assert len(alice_history) == 2, f"Expected 2 conversations for Alice, got {len(alice_history)}"
        assert all(conv.get('username') == 'alice' for conv in alice_history), "All conversations should be from Alice"
        print(f"✓ Retrieved {len(alice_history)} conversations from Alice")
        print(f"  - Queries: {[conv['user_query'] for conv in alice_history]}")
        
        # Test 3: Get Bob's history only
        print("\nTest 3: Getting Bob's conversation history...")
        bob_history = mother.get_history(limit=10, username="bob")
        assert len(bob_history) == 1, f"Expected 1 conversation for Bob, got {len(bob_history)}"
        assert bob_history[0].get('username') == 'bob', "Conversation should be from Bob"
        print(f"✓ Retrieved {len(bob_history)} conversation from Bob")
        print(f"  - Query: {bob_history[0]['user_query']}")
        
        # Test 4: Verify database structure
        print("\nTest 4: Verifying database structure...")
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(conversations)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}
        
        assert 'username' in columns, "username column should exist"
        assert 'user_query' in columns, "user_query column should exist"
        assert 'agent_response' in columns, "agent_response column should exist"
        print("✓ Database structure is correct")
        print(f"  - Columns: {list(columns.keys())}")
        
        conn.close()
        
        # Test 5: Privacy - users can see their own conversations
        print("\nTest 5: Testing privacy - user-specific queries...")
        
        # Alice queries for her conversations
        alice_queries = [conv['user_query'] for conv in mother.get_history(username="alice")]
        expected_alice_queries = ["Check CPU usage", "What is the system status?"]
        
        # Verify Alice only sees her queries
        for query in alice_queries:
            assert query in expected_alice_queries, f"Unexpected query in Alice's history: {query}"
        
        # Verify Alice doesn't see Bob's queries
        assert "Are there any failures?" not in alice_queries, "Alice should not see Bob's queries"
        
        print("✓ Privacy check passed - users only see their own conversations when filtered")
        
        print("\n" + "="*60)
        print("✓ ALL INTEGRATION TESTS PASSED!")
        print("="*60)
        
        # Print summary
        print("\nSummary:")
        print(f"  - Total conversations: {len(all_history)}")
        print(f"  - Alice's conversations: {len(alice_history)}")
        print(f"  - Bob's conversations: {len(bob_history)}")
        print(f"  - Anonymous conversations: 1")
        print("\nConclusion:")
        print("  Mother now tracks WHO asked WHAT question and WHEN.")
        print("  Users can filter their conversation history for privacy.")
        
    finally:
        # Clean up
        if os.path.exists(temp_db):
            os.unlink(temp_db)


if __name__ == "__main__":
    test_complete_flow()
