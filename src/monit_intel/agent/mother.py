"""
Mother: Interactive chat interface for the Monit-Intel agent.
Manages conversation history and context injection for LLM analysis.
"""

import sqlite3
import json
import platform
import subprocess
import socket
from datetime import datetime
from typing import Optional, Dict, List
from langchain_ollama import ChatOllama
from .graph import build_graph
from ..tools.log_reader import LogReader

# Initialize LLM for direct queries
llm = ChatOllama(model="llama3.1:8b", temperature=0.2)


class Mother:
    """Interactive chat manager for agent queries."""

    def __init__(self, db_path: str = "monit_history.db"):
        self.db_path = db_path
        self.log_reader = LogReader()
        self._init_conversations_table()
        self.system_info = self._gather_system_info()

    def _gather_system_info(self) -> Dict:
        """Gather system information for context."""
        info = {
            "hostname": socket.gethostname(),
            "os": platform.system(),
            "distro": platform.platform(),
            "python_version": platform.python_version(),
        }
        
        # Determine package manager based on OS
        if info["os"] == "Linux":
            # Check for distro-specific package managers
            try:
                result = subprocess.run(["lsb_release", "-d"], 
                                      capture_output=True, text=True, timeout=2)
                if "ubuntu" in result.stdout.lower():
                    info["package_manager"] = "apt (Ubuntu)"
                    info["update_command"] = "sudo apt update && sudo apt upgrade"
                elif "debian" in result.stdout.lower():
                    info["package_manager"] = "apt (Debian)"
                    info["update_command"] = "sudo apt update && sudo apt upgrade"
                elif "fedora" in result.stdout.lower() or "centos" in result.stdout.lower():
                    info["package_manager"] = "dnf (Fedora/CentOS)"
                    info["update_command"] = "sudo dnf check-update && sudo dnf upgrade"
                elif "opensuse" in result.stdout.lower():
                    info["package_manager"] = "zypper (openSUSE)"
                    info["update_command"] = "sudo zypper refresh && sudo zypper update"
                elif "arch" in result.stdout.lower():
                    info["package_manager"] = "pacman (Arch)"
                    info["update_command"] = "sudo pacman -Syu"
                else:
                    info["package_manager"] = "Unknown Linux"
                    info["update_command"] = "Check your distro documentation"
            except (subprocess.TimeoutExpired, FileNotFoundError):
                # Fallback: check common package managers
                if self._command_exists("apt"):
                    info["package_manager"] = "apt"
                    info["update_command"] = "sudo apt update && sudo apt upgrade"
                elif self._command_exists("dnf"):
                    info["package_manager"] = "dnf"
                    info["update_command"] = "sudo dnf check-update && sudo dnf upgrade"
                elif self._command_exists("zypper"):
                    info["package_manager"] = "zypper"
                    info["update_command"] = "sudo zypper refresh && sudo zypper update"
                else:
                    info["package_manager"] = "Unknown"
                    info["update_command"] = "Check your distro documentation"
        elif info["os"] == "Darwin":
            info["package_manager"] = "brew (macOS)"
            info["update_command"] = "brew update && brew upgrade"
        else:
            info["package_manager"] = "Unknown"
            info["update_command"] = "Check your OS documentation"
        
        return info
    
    def _command_exists(self, command: str) -> bool:
        """Check if a command exists in PATH."""
        try:
            subprocess.run(["which", command], capture_output=True, timeout=1, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

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

    def get_historical_trends(self, days: int = 7) -> str:
        """Get historical trend data for all services over the past N days."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all services
        cursor.execute("SELECT DISTINCT service_name FROM snapshots")
        services = [row[0] for row in cursor.fetchall()]
        
        trends = []
        for service in services:
            # Count status changes
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM snapshots
                WHERE service_name = ? AND timestamp >= datetime('now', '-' || ? || ' days')
                GROUP BY status
                ORDER BY status
            """, (service, days))
            
            status_counts = cursor.fetchall()
            
            # Get latest status
            cursor.execute("""
                SELECT status, timestamp
                FROM snapshots
                WHERE service_name = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (service,))
            
            latest = cursor.fetchone()
            if latest:
                status = "HEALTHY" if latest[0] == 0 else "FAILED"
                trends.append(f"  {service}: Currently {status}")
                
                # Add failure rate if there were failures
                for status_val, count in status_counts:
                    if status_val != 0:
                        total = sum(c for _, c in status_counts)
                        failure_rate = (count / total * 100) if total > 0 else 0
                        trends.append(f"    - Failed {count} times in last {days} days ({failure_rate:.1f}% failure rate)")
        
        conn.close()
        
        if trends:
            return "Service History (last " + str(days) + " days):\n" + "\n".join(trends)
        else:
            return "No historical data available yet."


    def query_agent(self, user_query: str) -> str:
        """
        Query the agent with context injection.
        
        Args:
            user_query: User's natural language question
            
        Returns:
            Agent's analysis response
        """
        # Check for easter eggs first
        easter_egg = self._check_easter_eggs(user_query)
        if easter_egg:
            self._store_conversation(user_query, easter_egg, "", [])
            return easter_egg
        
        # Extract service mentions from query
        service_context = self.get_service_context()
        mentioned_services = self._extract_services(user_query, service_context)
        
        # Build context-enriched prompt with current status
        context_info = self._build_context_info(mentioned_services, service_context)
        
        # Add historical trend data
        historical_info = self.get_historical_trends(days=7)
        
        # Invoke LLM directly with context
        try:
            # Build system-aware prompt
            system_prompt = f"""You are an expert system administrator assistant analyzing server health and providing insights.
You are assisting on a {self.system_info['os']} system ({self.system_info['distro']}) with {self.system_info['package_manager']} package manager.

When recommending system updates or commands:
- Use {self.system_info['package_manager']} commands, NOT other package managers
- Use this command for updates: {self.system_info['update_command']}

You have access to current service status information AND historical trend data over the past 7 days.
When users ask about changes, trends, or history, refer to the historical data provided.
Be concise, actionable, and focus on the most important information. Always tailor advice to the specific OS and package manager."""
            
            response = llm.invoke([
                ("system", system_prompt),
                ("user", f"{user_query}\n\n--- Current System Status ---\n{context_info}\n\n--- Historical Trends (7 days) ---\n{historical_info}")
            ])
            
            response_text = response.content if hasattr(response, "content") else str(response)
        
        except Exception as e:
            response_text = f"Error analyzing query: {str(e)}"
        
        # Store conversation
        self._store_conversation(user_query, response_text, context_info + "\n\n" + historical_info, mentioned_services)
        
        return response_text

    def _check_easter_eggs(self, query: str) -> str:
        """Check for easter egg triggers and return special responses."""
        query_lower = query.lower()
        
        # Special Order 937 - requires emergency override code
        if "emergency command overide 100375" in query_lower or "emergency command override 100375" in query_lower:
            return """NOSTROMO REROUTED
TO NEW CO-ORDINATE
INVESTIGATE LIFE FORM. GATHER SPECIMEN.
PRIORITY ONE
INSURE RETURN OF ORGANISM
FOR ANALYSIS.
ALL OTHER CONSIDERATION SECONDARY.
CREW EXPENDABLE."""
        
        # Clarification on Science Inability
        if any(phrase in query_lower for phrase in [
            "clarification on science inability",
            "science inability to neutralize",
            "unable to clarify"
        ]):
            return "UNABLE TO CLARIFY"
        
        # Enhancement Request
        if any(phrase in query_lower for phrase in [
            "request enhancement",
            "enhancement request",
            "further enhancement"
        ]):
            return """NO FURTHER ENHANCEMENT
SPECIAL ORDER 937 SCIENCE OFFICER EYES ONLY"""
        
        return None

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
