"""
Mother: Interactive chat interface for the Monit-Intel agent.
Manages conversation history and context injection for LLM analysis.
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional, Dict, List
from agent.graph import build_graph
from tools.log_reader import LogReader


class Mother:
    """Interactive chat manager for agent queries."""

    def __init__(self, db_path: str = "monit_history.db"):
        self.db_path = db_path
        self.log_reader = LogReader()
        self._init_conversations_table()

    def _init_conversations_table(self):
        """Create conversations table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
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

    def get_service_context(self) -> Dict:
        """Fetch current service status as context for LLM."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get latest status for each service (SQLite compatible)
        cursor.execute("""
            SELECT service_name, status, timestamp 
            FROM snapshots 
            WHERE (service_name, timestamp) IN (
                SELECT service_name, MAX(timestamp) 
                FROM snapshots 
                GROUP BY service_name
            )
        """)
        
        services = {}
        for service_name, status, timestamp in cursor.fetchall():
            services[service_name] = {
                "status": status,
                "last_checked": timestamp,
                "healthy": status == 0
            }
        
        conn.close()
        return services

    def get_failure_context(self, service_name: str, days: int = 7) -> Dict:
        """Fetch failure history for a service."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, status 
            FROM snapshots 
            WHERE service_name = ? AND timestamp >= datetime('now', '-' || ? || ' days')
            ORDER BY timestamp DESC
        """, (service_name, days))
        
        records = cursor.fetchall()
        failures = [r for r in records if r[1] != 0]
        
        conn.close()
        return {
            "service": service_name,
            "total_checks": len(records),
            "failures": len(failures),
            "failure_percentage": (len(failures) / len(records) * 100) if records else 0,
            "recent_failures": failures[:5]
        }

    def query_agent(self, user_query: str) -> str:
        """
        Query the agent with context injection.
        
        Args:
            user_query: User's natural language question
            
        Returns:
            Agent's analysis response
        """
        # Extract service mentions from query
        service_context = self.get_service_context()
        mentioned_services = self._extract_services(user_query, service_context)
        
        # Build context-enriched prompt
        context_info = self._build_context_info(mentioned_services, service_context)
        enriched_query = f"{user_query}\n\n--- System Context ---\n{context_info}"
        
        # Invoke agent graph
        try:
            graph = build_graph()
            state = {
                "messages": [{"role": "user", "content": enriched_query}],
                "context_data": context_info,
                "is_critical": any(not service_context[s]["healthy"] for s in mentioned_services 
                                  if s in service_context)
            }
            result = graph.invoke(state)
            
            # Extract response from messages (handle both tuple and object formats)
            response = "No response"
            if result.get("messages"):
                last_msg = result["messages"][-1]
                if isinstance(last_msg, tuple) and len(last_msg) > 1:
                    response = last_msg[1]
                elif hasattr(last_msg, "content"):
                    response = last_msg.content
                elif isinstance(last_msg, dict) and "content" in last_msg:
                    response = last_msg["content"]
        except Exception as e:
            response = f"Error analyzing query: {str(e)}"
        
        # Store conversation
        self._store_conversation(user_query, response, context_info, mentioned_services)
        
        return response

    def _extract_services(self, query: str, service_context: Dict) -> List[str]:
        """Extract mentioned service names from user query."""
        mentioned = []
        query_lower = query.lower()
        
        for service in service_context.keys():
            if service.lower() in query_lower or service.replace("_", " ").lower() in query_lower:
                mentioned.append(service)
        
        return mentioned if mentioned else list(service_context.keys())[:3]

    def _build_context_info(self, services: List[str], context: Dict) -> str:
        """Build formatted context information for LLM."""
        lines = ["Current Service Status:", ""]
        
        for service in services:
            if service in context:
                info = context[service]
                status = "✓ HEALTHY" if info["healthy"] else "✗ FAILED"
                lines.append(f"  {service}: {status} (last checked: {info['last_checked']})")
        
        return "\n".join(lines)

    def _store_conversation(self, user_query: str, response: str, 
                          context: str, services: List[str]):
        """Store conversation in SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO conversations (user_query, agent_response, service_context, logs_provided)
            VALUES (?, ?, ?, ?)
        """, (user_query, response, json.dumps(services), context))
        
        conn.commit()
        conn.close()

    def get_history(self, limit: int = 10) -> List[Dict]:
        """Retrieve conversation history."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, timestamp, user_query, agent_response 
            FROM conversations 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        
        history = []
        for row in cursor.fetchall():
            history.append({
                "id": row[0],
                "timestamp": row[1],
                "user_query": row[2],
                "agent_response": row[3]
            })
        
        conn.close()
        return history

    def clear_history(self):
        """Clear conversation history."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations")
        conn.commit()
        conn.close()
