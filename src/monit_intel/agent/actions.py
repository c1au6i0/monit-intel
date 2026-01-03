"""
ActionExecutor: Safe command execution for systemd and monit operations.
Implements whitelist-based access control with audit logging.
"""

import subprocess
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from enum import Enum


class ActionType(Enum):
    """Safe action types."""
    SYSTEMCTL_RESTART = "systemctl_restart"
    SYSTEMCTL_STOP = "systemctl_stop"
    SYSTEMCTL_START = "systemctl_start"
    SYSTEMCTL_STATUS = "systemctl_status"
    MONIT_MONITOR = "monit_monitor"
    MONIT_START = "monit_start"
    MONIT_STOP = "monit_stop"
    JOURNALCTL_VIEW = "journalctl_view"


class ActionExecutor:
    """Execute safe system commands with audit logging."""

    # Whitelist of allowed actions
    SAFE_ACTIONS = {
        ActionType.SYSTEMCTL_RESTART: "systemctl restart {service}",
        ActionType.SYSTEMCTL_STOP: "systemctl stop {service}",
        ActionType.SYSTEMCTL_START: "systemctl start {service}",
        ActionType.SYSTEMCTL_STATUS: "systemctl status {service}",
        ActionType.MONIT_MONITOR: "sudo monit monitor {service}",
        ActionType.MONIT_START: "sudo monit start {service}",
        ActionType.MONIT_STOP: "sudo monit stop {service}",
        ActionType.JOURNALCTL_VIEW: "journalctl -u {service} -n 50",
    }

    # Blocked commands (never allowed)
    BLOCKED_KEYWORDS = [
        "rm", "kill", "reboot", "shutdown", "halt",
        "mkfs", "dd", "truncate", "/etc/", "/root/",
        "apt", "pip", "npm", "ifconfig", "ip route",
        "passwd", "useradd", "userdel"
    ]

    def __init__(self, db_path: str = "monit_history.db"):
        self.db_path = db_path
        self._init_audit_table()

    def _init_audit_table(self):
        """Create action_audit_log table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS action_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                action_type TEXT NOT NULL,
                service_name TEXT,
                command TEXT NOT NULL,
                user_approved BOOLEAN,
                exit_code INTEGER,
                result TEXT,
                error_message TEXT
            )
        """)
        conn.commit()
        conn.close()

    def suggest_action(self, action_type: ActionType, service_name: str) -> Dict:
        """
        Suggest an action (don't execute yet).
        
        Args:
            action_type: Type of action to suggest
            service_name: Target service
            
        Returns:
            Dict with action details and command preview
        """
        if action_type not in self.SAFE_ACTIONS:
            return {
                "allowed": False,
                "reason": f"Unknown action type: {action_type}"
            }

        command = self.SAFE_ACTIONS[action_type].format(service=service_name)
        
        # Check for blocked keywords
        if self._is_blocked(command):
            return {
                "allowed": False,
                "reason": f"Action contains blocked keywords"
            }

        return {
            "allowed": True,
            "action_type": action_type.value,
            "service": service_name,
            "command": command,
            "description": self._get_action_description(action_type)
        }

    def execute_action(self, action_type: ActionType, service_name: str, 
                      user_approved: bool = False) -> Dict:
        """
        Execute a safe action with audit logging.
        
        Args:
            action_type: Type of action
            service_name: Target service
            user_approved: Did user confirm?
            
        Returns:
            Dict with execution result
        """
        suggestion = self.suggest_action(action_type, service_name)
        
        if not suggestion.get("allowed"):
            return {
                "success": False,
                "reason": suggestion.get("reason", "Action not allowed")
            }

        if not user_approved:
            return {
                "success": False,
                "reason": "User approval required",
                "action": suggestion
            }

        command = suggestion["command"]
        
        try:
            # Execute with timeout (30 seconds max)
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            success = result.returncode == 0
            
            # Log to audit table
            self._log_action(
                action_type,
                service_name,
                command,
                user_approved,
                result.returncode,
                result.stdout + result.stderr if success else result.stderr,
                None if success else f"Exit code: {result.returncode}"
            )
            
            return {
                "success": success,
                "action": action_type.value,
                "service": service_name,
                "exit_code": result.returncode,
                "output": result.stdout,
                "error": result.stderr if not success else None
            }
        
        except subprocess.TimeoutExpired:
            self._log_action(
                action_type,
                service_name,
                command,
                user_approved,
                -1,
                None,
                "Command timed out (>30 seconds)"
            )
            return {
                "success": False,
                "reason": "Command timeout (>30 seconds)"
            }
        
        except Exception as e:
            self._log_action(
                action_type,
                service_name,
                command,
                user_approved,
                -1,
                None,
                str(e)
            )
            return {
                "success": False,
                "reason": f"Execution error: {str(e)}"
            }

    def _is_blocked(self, command: str) -> bool:
        """Check if command contains blocked keywords."""
        command_lower = command.lower()
        return any(blocked in command_lower for blocked in self.BLOCKED_KEYWORDS)

    def _log_action(self, action_type: ActionType, service_name: str, 
                   command: str, approved: bool, exit_code: int,
                   result: Optional[str], error: Optional[str]):
        """Log action to audit table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO action_audit_log 
            (action_type, service_name, command, user_approved, exit_code, result, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (action_type.value, service_name, command, approved, exit_code, result, error))
        
        conn.commit()
        conn.close()

    def get_audit_log(self, limit: int = 50) -> List[Dict]:
        """Retrieve action audit log."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, timestamp, action_type, service_name, command, 
                   user_approved, exit_code, error_message
            FROM action_audit_log
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        logs = []
        for row in cursor.fetchall():
            logs.append({
                "id": row[0],
                "timestamp": row[1],
                "action_type": row[2],
                "service": row[3],
                "command": row[4],
                "approved": row[5],
                "exit_code": row[6],
                "error": row[7]
            })
        
        conn.close()
        return logs

    @staticmethod
    def _get_action_description(action_type: ActionType) -> str:
        """Get human-readable description of action."""
        descriptions = {
            ActionType.SYSTEMCTL_RESTART: "Restart the service to recover from transient failures",
            ActionType.SYSTEMCTL_STOP: "Stop the service to prevent cascading failures",
            ActionType.SYSTEMCTL_START: "Start the service to bring it online",
            ActionType.SYSTEMCTL_STATUS: "Get detailed systemd status information",
            ActionType.MONIT_MONITOR: "Force Monit to re-check the service immediately",
            ActionType.MONIT_START: "Tell Monit to bring the service online",
            ActionType.MONIT_STOP: "Tell Monit to stop monitoring the service",
            ActionType.JOURNALCTL_VIEW: "View recent systemd journal logs for the service",
        }
        return descriptions.get(action_type, "Unknown action")
