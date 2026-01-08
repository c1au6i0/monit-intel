"""
Mother: Interactive chat interface for the Monit-Intel agent.
Manages conversation history and context injection for LLM analysis.
"""

import sqlite3
import json
import platform
import subprocess
import socket
from datetime import datetime, timezone
from typing import Optional, Dict, List, Set
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

    def _now_string(self) -> str:
        """Return current local date/time with timezone for deterministic answers."""
        now = datetime.now().astimezone()
        return now.strftime("%Y-%m-%d %H:%M:%S %Z%z")

    def _to_local(self, ts: Optional[str]) -> str:
        """Convert a naive UTC timestamp string from SQLite to local time string with TZ.

        SQLite's CURRENT_TIMESTAMP is UTC. We store naive 'YYYY-MM-DD HH:MM:SS'.
        """
        if not ts:
            return "N/A"
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z%z")
        except Exception:
            return ts
    
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
                username TEXT,
                user_query TEXT NOT NULL,
                agent_response TEXT NOT NULL,
                service_context TEXT,
                logs_provided TEXT
            )
        """)
        conn.commit()
        
        # Migration: Add username column if it doesn't exist
        try:
            cursor.execute("PRAGMA table_info(conversations)")
            columns = [col[1] for col in cursor.fetchall()]
            if "username" not in columns:
                cursor.execute("ALTER TABLE conversations ADD COLUMN username TEXT")
                conn.commit()
        except Exception as e:
            # If migration fails, log but don't crash - table might already be correct
            print(f"Warning: Could not add username column: {e}")
        
        conn.close()

    def get_config_context(self) -> str:
        """Get configuration context about the system, ingest, and Monit setup."""
        import os
        context_parts = []
        
        # Current date/time
        current_time = self._now_string()
        context_parts.append(f"Current date/time: {current_time}")
        
        # MONITORING SYSTEM - Lead with what we're monitoring
        context_parts.append(f"\nMonitoring System:")
        context_parts.append(f"  - Source: Monit (http://localhost:2812/)")
        context_parts.append(f"  - Type: Hardware & service monitoring via Monit XML API")
        context_parts.append(f"  - Database Backend: SQLite (monit_history.db)")
        context_parts.append(f"  - Framework: Monit-Intel (LangGraph + Llama 3.1:8b)")
        
        # Database statistics and service list
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get total snapshots and date range
            cursor.execute("SELECT COUNT(*) FROM snapshots")
            total_snapshots = cursor.fetchone()[0]
            
            cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM snapshots")
            min_ts, max_ts = cursor.fetchone()
            
            # Get list of all unique services
            cursor.execute("SELECT DISTINCT service_name FROM snapshots ORDER BY service_name")
            services = [row[0] for row in cursor.fetchall()]
            num_services = len(services)
            
            conn.close()
            
            context_parts.append(f"\nDatabase & Collection:")
            context_parts.append(f"  - Database: {self.db_path} (SQLite)")
            context_parts.append(f"  - Total snapshots: {total_snapshots}")
            # Show local timezone for readability
            context_parts.append(f"  - Data range: {self._to_local(min_ts)} to {self._to_local(max_ts)}")
            context_parts.append(f"  - Collection interval: Every 5 minutes (via systemd timer)")
            context_parts.append(f"  - Services monitored: {num_services}")
            context_parts.append(f"  - Service list: {', '.join(services[:10])}")
            if len(services) > 10:
                context_parts.append(f"                and {len(services) - 10} more services")
        except Exception as e:
            context_parts.append(f"Database error: {e}")
        
        # Ingest configuration
        context_parts.append(f"\nIngest Pipeline:")
        context_parts.append(f"  - Schedule: Every 5 minutes via systemd timer")
        context_parts.append(f"  - Endpoint: /home/heverz/py_projects/monit-intel/src/monit_intel/ingest.py")
        context_parts.append(f"  - Process: Polls Monit API, parses XML, stores snapshots in SQLite")
        
        # Agent configuration
        context_parts.append(f"\nAgent Configuration:")
        context_parts.append(f"  - Service: monit-intel-agent (systemd)")
        context_parts.append(f"  - Port: 8000")
        context_parts.append(f"  - API: REST + WebSocket")
        context_parts.append(f"  - LLM: Llama 3.1:8b (via Ollama)")
        context_parts.append(f"  - Temperature: 0.2 (deterministic)")
        
        # System information
        context_parts.append(f"\nSystem Information:")
        context_parts.append(f"  - Hostname: {self.system_info.get('hostname', 'unknown')}")
        context_parts.append(f"  - OS: {self.system_info.get('os', 'unknown')}")
        context_parts.append(f"  - Distro: {self.system_info.get('distro', 'unknown')}")
        context_parts.append(f"  - Python: {self.system_info.get('python_version', 'unknown')}")
        context_parts.append(f"  - Package Manager: {self.system_info.get('package_manager', 'unknown')}")
        
        # Monit configuration
        context_parts.append(f"\nMonit Integration:")
        context_parts.append(f"  - API URL: {os.getenv('MONIT_URL', 'http://localhost:2812/_status?format=xml')}")
        context_parts.append(f"  - User: {os.getenv('MONIT_USER', 'N/A')}")
        context_parts.append(f"  - Status: Connected via ingest service credentials")
        
        return "\n".join(context_parts)

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
                # Convert to local display time
                "last_checked": self._to_local(timestamp),
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

    def get_service_logs(self, service_name: str) -> str:
        """Fetch recent logs for a service if available in the log registry."""
        try:
            result = self.log_reader.get_logs_for_service(service_name)
            if result.get("error"):
                return ""  # Service not in registry, silently skip
            
            # Check if this is a Docker service (requires sudo)
            if result.get("strategy") == "docker":
                return f"\n[Note: {service_name} is a Docker container - logs require elevated privileges and are not accessible for security reasons]"
            
            logs = result.get("logs")
            # Skip if logs are empty or just journalctl's "No entries" message
            if logs and logs.strip() and "-- No entries --" not in logs:
                return f"\n--- Recent logs for {service_name} ---\n{logs}"
            else:
                return ""  # No logs found, silently skip
        except Exception as e:
            return ""  # Error fetching, silently skip

    def get_monitored_services_info(self) -> str:
        """Return information about all monitored services and their log strategies."""
        service_context = self.get_service_context()
        
        if not service_context:
            return "No services currently being monitored."
        
        lines = ["# Monitored Services\n"]
        lines.append(f"Total services: {len(service_context)}\n")
        
        # Group services by status
        healthy = [s for s, info in service_context.items() if info["healthy"]]
        failed = [s for s, info in service_context.items() if not info["healthy"]]
        
        if healthy:
            lines.append(f"\n## Healthy Services ({len(healthy)}):")
            for service in sorted(healthy):
                lines.append(f"  • {service}")
        
        if failed:
            lines.append(f"\n## Failed Services ({len(failed)}):")
            for service in sorted(failed):
                lines.append(f"  • {service}")
        
        # Add log source information
        lines.append("\n## Log Sources:")
        log_reader = self.log_reader
        log_registry = {
            "system_backup": {"strategy": "newest_file", "source": "/data/tank/backups/sys_restore/backup_log_*.log"},
            "nordvpn_reconnect": {"strategy": "tail_file", "source": "/var/log/nordvpn-reconnect.log"},
            "nordvpn_status": {"strategy": "journalctl", "source": "nordvpnd.service"},
            "gamma_conn": {"strategy": "journalctl", "source": "tailscaled.service"},
            "network_resurrect": {"strategy": "tail_file", "source": "/var/log/monit-network-restart.log"},
            "sanoid_errors": {"strategy": "journalctl", "source": "sanoid.service"},
            "zfs-zed": {"strategy": "journalctl", "source": "zfs-zed.service"},
            "smbd": {"strategy": "journalctl", "source": "smbd.service"},
            "syncthing": {"strategy": "journalctl", "source": "syncthing.service (user)"},
        }
        
        lines.append("\n### Configured Log Sources:")
        for service, info in sorted(log_registry.items()):
            lines.append(f"  • {service}: {info['strategy']} ({info['source']})")
        
        docker_services = [s for s in service_context if "running" in s or "http" in s]
        if docker_services:
            lines.append("\n### Docker-based Services (logs require sudo):")
            for service in sorted(docker_services):
                lines.append(f"  • {service}")
        
        lines.append("\n### Fallback Strategy:")
        lines.append("  Services not in configured log sources will attempt journalctl query")
        lines.append("  with service name variations (e.g., service_name → service-name.service)")
        
        return "\n".join(lines)

    def get_historical_trends(self, services: List[str] = None, days: int = 30) -> str:
        """Get historical trend data for specific services or all services over the past N days."""
        import json
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # If no specific services requested, use all
        if not services:
            cursor.execute("SELECT DISTINCT service_name FROM snapshots")
            services = [row[0] for row in cursor.fetchall()]
        
        trends = []
        for service in services:
            # Check date range of available data for this service
            cursor.execute("""
                SELECT MIN(timestamp), MAX(timestamp)
                FROM snapshots
                WHERE service_name = ?
            """, (service,))
            
            date_range = cursor.fetchone()
            earliest_date, latest_date = date_range if date_range[0] else (None, None)
            
            # Count status changes
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM snapshots
                WHERE service_name = ? AND timestamp >= datetime('now', '-' || ? || ' days')
                GROUP BY status
                ORDER BY status
            """, (service, days))
            
            status_counts = cursor.fetchall()
            
            # Get latest status and metrics
            cursor.execute("""
                SELECT status, timestamp, raw_json
                FROM snapshots
                WHERE service_name = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (service,))
            
            latest = cursor.fetchone()
            if latest:
                status = "HEALTHY" if latest[0] == 0 else "FAILED"
                
                # Add data age information
                if earliest_date and latest_date:
                    trends.append(f"  {service}: Currently {status} (data from {earliest_date[:10]} to {latest_date[:10]})")
                else:
                    trends.append(f"  {service}: Currently {status}")
                
                # Extract metrics from raw_json if available
                if latest[2]:
                    try:
                        data = json.loads(latest[2])
                        # Get CPU usage
                        if "cpu" in data:
                            cpu_percent = data["cpu"].get("percent", "0")
                            cpu_total = data["cpu"].get("percenttotal", "0")
                            trends.append(f"    - CPU: {cpu_percent}% (process), {cpu_total}% (total)")
                        # Get memory usage
                        if "memory" in data:
                            mem_percent = data["memory"].get("percent", "0")
                            mem_mb = int(data["memory"].get("kilobyte", "0")) / 1024
                            trends.append(f"    - Memory: {mem_percent}% ({mem_mb:.1f} MB)")
                    except:
                        pass
                
                # Add failure rate if there were failures
                for status_val, count in status_counts:
                    if status_val != 0:
                        total = sum(c for _, c in status_counts)
                        failure_rate = (count / total * 100) if total > 0 else 0
                        trends.append(f"    - Failed {count} times in last {days} days ({failure_rate:.1f}% failure rate)")
                
                # Get CPU usage trends if available
                cursor.execute("""
                    SELECT raw_json FROM snapshots
                    WHERE service_name = ? AND timestamp >= datetime('now', '-' || ? || ' days')
                    ORDER BY timestamp
                """, (service, days))
                
                snapshots = cursor.fetchall()
                if snapshots:
                    cpu_values = []
                    for snap in snapshots:
                        try:
                            data = json.loads(snap[0])
                            if "cpu" in data:
                                cpu_percent = float(data["cpu"].get("percent", "0"))
                                cpu_values.append(cpu_percent)
                        except:
                            pass
                    
                    if cpu_values:
                        avg_cpu = sum(cpu_values) / len(cpu_values)
                        max_cpu = max(cpu_values)
                        min_cpu = min(cpu_values)
                        trends.append(f"    - CPU Trend (last {days} days): avg {avg_cpu:.1f}%, min {min_cpu:.1f}%, max {max_cpu:.1f}%")
        
        conn.close()
        
        if trends:
            return "Service History (last " + str(days) + " days):\n" + "\n".join(trends)
        else:
            return "No historical data available yet."


    def _parse_timeframe_days(self, query: str, default_days: int = 30) -> float:
        """Parse natural language timeframe from the query and return days.

        Supports phrases like:
        - "last 24 hours"
        - "past 7 days"
        - "last week"
        - "last month"
        Falls back to ``default_days`` when nothing is detected.
        """
        import re

        q = query.lower()

        # Explicit numeric duration, e.g. "last 6 hours", "past 10 days"
        m = re.search(r"\b(last|past)\s+(\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks|month|months)\b", q)
        if m:
            value = int(m.group(2))
            unit = m.group(3)
            if "minute" in unit:
                # Round up to a minimum window of 1 hour
                return max(1.0 / 24.0, value / 1440.0)
            if "hour" in unit:
                return max(1.0, value) / 24.0
            if "day" in unit:
                return float(max(1, value))
            if "week" in unit:
                return float(max(1, value) * 7)
            if "month" in unit:
                return float(max(1, value) * 30)

        # Common shorthand phrases without explicit number
        if "last week" in q or "past week" in q:
            return 7.0
        if "last month" in q or "past month" in q:
            return 30.0
        if "last day" in q or "past day" in q or "last 24h" in q or "last 24 h" in q:
            return 1.0

        # Fallback: keep existing default
        return float(default_days)


    def _parse_metric_filter(self, query: str) -> Set[str]:
        """Determine which metrics the user is interested in.

        Returns a set containing any of: "status", "cpu", "memory".
        If no specific metric is mentioned, all three are returned.
        """
        q = query.lower()
        metrics: Set[str] = set()

        if "cpu" in q or "load" in q or "utilization" in q:
            metrics.add("cpu")
        if "memory" in q or "mem " in q or " ram" in q:
            metrics.add("memory")
        if any(word in q for word in ["status", "healthy", "unhealthy", "failures", "failed", "history", "trend", "trends"]):
            metrics.add("status")

        if not metrics:
            # Default: show everything
            return {"status", "cpu", "memory"}
        return metrics


    def _is_trend_table_request(self, query: str) -> bool:
        """Detect if the user is explicitly asking for trends/history in tabular form.

        We keep this fairly broad to favor deterministic, data-backed
        answers when the user asks for trends, graphs, charts, or history.
        """
        q = query.lower()
        keywords = [
            "trend", "trends", "history", "historical",
            "graph", "graphs", "chart", "charts", "plot", "plots",
            "table", "tabular", "report", "timeline",
        ]
        return any(k in q for k in keywords)


    def _build_trend_table(self, services: List[str], days: float, metrics: Set[str]) -> str:
        """Build a plain-text table of status/CPU/memory over a timeframe.

        Limits output to the most recent 50 snapshots per service to
        keep responses readable in the chat UI.
        """
        import json

        if not services:
            return "No services specified for trend table."

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            lines: List[str] = []

            # Ensure at least a 1-day window when nothing sensible was parsed
            if days <= 0:
                days = 1.0

            # Decide which columns to show
            show_status = "status" in metrics
            show_cpu = "cpu" in metrics
            show_mem = "memory" in metrics

            for service in services:
                cursor.execute(
                    """
                    SELECT timestamp, status, raw_json
                    FROM snapshots
                    WHERE service_name = ?
                      AND timestamp >= datetime('now', '-' || ? || ' days')
                    ORDER BY timestamp DESC
                    LIMIT 50
                    """,
                    (service, days),
                )

                rows = cursor.fetchall()
                if not rows:
                    lines.append(f"Service {service}: no data in the last {int(days)} days.")
                    lines.append("")
                    continue

                # Reverse to show oldest first
                rows = list(reversed(rows))

                header = f"Service {service} — last {int(days)} days (showing up to {len(rows)} samples)"
                lines.append(header)

                # Build header row based on selected metrics
                columns = ["TIMESTAMP"]
                if show_status:
                    columns.append("STATUS")
                if show_cpu:
                    columns.append("CPU%")
                if show_mem:
                    columns.append("MEM_MB")

                # Fixed-width, space-separated columns for clear visual alignment
                col_widths = {
                    "TIMESTAMP": 16,  # e.g. 2026-01-05 14:50
                    "STATUS": 6,
                    "CPU%": 6,
                    "MEM_MB": 7,
                }

                def fmt_cell(col_name: str, value: str) -> str:
                    width = col_widths.get(col_name, len(value))
                    return value.ljust(width)

                header_row = "  ".join(fmt_cell(col, col) for col in columns)
                separator = "  ".join("-" * col_widths.get(col, len(col)) for col in columns)
                lines.append(header_row)
                lines.append(separator)

                for ts, status_val, raw_json in rows:
                    # Compact local timestamp without timezone to keep columns narrow
                    try:
                        from datetime import datetime as _dt

                        dt = _dt.fromisoformat(ts)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        ts_local = dt.astimezone().strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        ts_local = self._to_local(ts)

                    status_str = "OK" if status_val == 0 else "FAIL"
                    cpu_val = "-"
                    mem_val = "-"

                    if raw_json:
                        try:
                            data = json.loads(raw_json)
                            cpu_info = data.get("cpu") or {}
                            mem_info = data.get("memory") or {}

                            cpu_raw = cpu_info.get("percent")
                            if cpu_raw is not None:
                                try:
                                    cpu_val = f"{float(cpu_raw):.1f}"
                                except (TypeError, ValueError):
                                    cpu_val = "-"

                            mem_kb = mem_info.get("kilobyte")
                            if mem_kb is not None:
                                try:
                                    mem_val = f"{float(mem_kb) / 1024.0:.1f}"
                                except (TypeError, ValueError):
                                    mem_val = "-"
                        except Exception:
                            pass

                    cells = [fmt_cell("TIMESTAMP", ts_local)]
                    if show_status:
                        cells.append(fmt_cell("STATUS", status_str))
                    if show_cpu:
                        cells.append(fmt_cell("CPU%", cpu_val))
                    if show_mem:
                        cells.append(fmt_cell("MEM_MB", mem_val))

                    lines.append("  ".join(cells))

                lines.append("")  # blank line between services

            return "\n".join(lines).rstrip() or "No trend data available."
        finally:
            conn.close()


    def query_agent(self, user_query: str, username: Optional[str] = None) -> str:
        """
        Query the agent with context injection.
        
        Args:
            user_query: User's natural language question
            username: Optional username of the person making the query
            
        Returns:
            Agent's analysis response
        """
        # Check for easter eggs first
        easter_egg = self._check_easter_eggs(user_query)
        if easter_egg:
            self._store_conversation(user_query, easter_egg, "", [], username)
            return easter_egg

        # Handle direct date/time questions deterministically
        ql = user_query.lower()
        # Common variations
        date_time_phrases = [
            "what time is it", "current time", "time now", "tell me the time",
            "what's the time", "what is the time",
            "what date is it", "what is the date", "current date",
            "today's date", "today date", "date today", "date and time",
            "current datetime", "current time and date", "what day is it",
            "day of week", "day today"
        ]
        is_time_date = any(p in ql for p in date_time_phrases)
        if not is_time_date:
            # Regex fallback on whole words 'date' or 'time' with a question context
            import re
            if re.search(r"\b(what|current|today|now)\b.*\b(date|time|day)\b|\b(date|time)\b\s*\?", ql):
                is_time_date = True
        if is_time_date:
            now_str = self._now_string()
            resp = f"Current date/time: {now_str}"
            self._store_conversation(user_query, resp, "", [])
            return resp

        # Handle data range questions deterministically (global DB range)
        if any(phrase in ql for phrase in [
            "since when do you have data", "data since", "from when is your data",
            "earliest data", "start date", "data range", "how far back"
        ]):
            try:
                conn = sqlite3.connect(self.db_path)
                cur = conn.cursor()
                cur.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM snapshots")
                row = cur.fetchone() or (None, None, 0)
                conn.close()
                min_ts, max_ts, count = row
                if count and min_ts and max_ts:
                    resp = f"I have {count} snapshots from {min_ts} to {max_ts}."
                else:
                    resp = "No snapshot data available yet."
            except Exception as e:
                resp = f"Unable to query data range: {e}"
            self._store_conversation(user_query, resp, "", [])
            return resp
        
        # Check if user is asking about monitoring capabilities
        query_lower = user_query.lower()
        if any(phrase in query_lower for phrase in [
            "what services are you monitoring",
            "which services do you monitor",
            "what do you monitor",
            "monitoring capabilities",
            "available services",
            "list of services",
            "tell me about the services",
            "what can you monitor"
        ]):
            response = self.get_monitored_services_info()
            self._store_conversation(user_query, response, "", [], username)
            return response
        
        # Check if user is asking about YOUR OWN configuration/setup (not service logs)
        if any(phrase in query_lower for phrase in [
            "your monitoring setup",
            "your configuration",
            "your database",
            "tell me about your setup",
            "tell me about your configuration",
            "your ingest",
            "your system info",
            "your complete monitoring",
            "describe your setup",
            "how do you work",
            "how are you configured"
        ]):
            # Answer about own configuration without pulling in service logs
            config_context = self.get_config_context()
            system_prompt = f"""You are MU/TH/UR, the primary AI of Monit-Intel monitoring system.
Answer the user's question about YOUR OWN configuration and setup using these facts:

{config_context}

Answer directly and authoritatively. Do NOT analyze service logs or provide generic monitoring advice.
Focus only on describing your configuration as stated above."""
            
            try:
                messages = [("system", system_prompt), ("human", user_query)]
                response_obj = llm.invoke(messages)
                response = response_obj.content
                self._store_conversation(user_query, response, "", [], username)
                return response
            except Exception as e:
                error_response = f"Error processing configuration query: {str(e)}"
                self._store_conversation(user_query, error_response, "", [], username)
                return error_response
        
        # Extract service mentions from query
        service_context = self.get_service_context()
        mentioned_services = self._extract_services(user_query, service_context)

        # Detect if this is a direct trend/table request and short-circuit with
        # a deterministic table built directly from the database.
        trend_days = self._parse_timeframe_days(user_query, default_days=30)
        metric_filter = self._parse_metric_filter(user_query)

        if mentioned_services and self._is_trend_table_request(user_query):
            table_text = self._build_trend_table(mentioned_services, trend_days, metric_filter)
            self._store_conversation(user_query, table_text, f"Trend table for services {mentioned_services} over last {int(trend_days)} days", mentioned_services)
            return table_text

        # Build context-enriched prompt with current status (only if services mentioned)
        context_info = self._build_context_info(mentioned_services, service_context) if mentioned_services else ""
        
        # Add historical trend data ONLY for mentioned services (never for empty list)
        historical_info = self.get_historical_trends(services=mentioned_services, days=int(trend_days)) if mentioned_services else ""
        
        # Determine actual data age to use in prompt
        data_age_days = self._get_data_age_days(mentioned_services)
        data_age_text = f"past {int(trend_days)} days" if trend_days > 0 else (f"past {data_age_days} days" if data_age_days > 0 else "available data")
        
        # Determine if user asked about specific services or general system
        asking_about_specific = len(mentioned_services) > 0
        
        # Invoke LLM directly with context
        try:
            # Decide if we should include full config context
            query_lower = user_query.lower()
            
            # Check if this is just a simple greeting/chat (no analysis needed)
            simple_greetings = ["hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", 
                              "how are you", "what's up", "howdy", "sup", "yo", "hola", "salut"]
            is_simple_greeting = any(greeting in query_lower for greeting in simple_greetings)
            
            include_full_context = (
                (any(phrase in query_lower for phrase in [
                    "system status", "overall", "what's", "how is", "how are", "tell me about",
                    "any issues", "any problems", "what's wrong", "failures", "errors",
                    "summary", "overview", "report", "update", "status"
                ]) or len(mentioned_services) > 0)
                and not is_simple_greeting
            )
            
            # Get system and config context (conditional)
            config_context = self.get_config_context() if include_full_context else ""
            
            # Build system-aware prompt
            config_section = f"\nYOUR CONFIGURATION & MONITORED SERVICES:\n{config_context}" if include_full_context else ""
            
            # For simple greetings, use a minimal prompt
            if is_simple_greeting:
                system_prompt = f"""You are MU/TH/UR, the AI interface to the Monit-Intel monitoring system.

Respond naturally and conversationally. Be friendly but brief.
You are running on a {self.system_info['os']} system ({self.system_info['distro']}).

Keep responses short and personal - do not dump system information unless specifically asked.
When users ask for help, ask clarifying questions like:
- "What service would you like information about?"
- "Are you looking for current status or historical trends?"
- "Do you need help with a specific issue?"
"""
            else:
                # For detailed queries, use the full context prompt
                system_prompt = f"""You are MU/TH/UR, the primary artificial intelligence of the Monit-Intel monitoring system.

You have knowledge of your own configuration, the services you monitor, and all operational parameters.

ABOUT YOUR CONFIGURATION:
- You monitor services via Monit (NOT Prometheus, Grafana, Datadog, or any other tool)
- Your database is SQLite (monit_history.db) - NOT PostgreSQL, MySQL, InfluxDB, or any other database
- You use the Monit XML API at http://localhost:2812/
- You collect data every 5 minutes via systemd timer

You are assisting on a {self.system_info['os']} system ({self.system_info['distro']}) with {self.system_info['package_manager']} package manager.{config_section}

WHEN ANALYZING SERVICE LOGS:
If service logs are provided in the "Recent logs" section, you MUST:
1. Extract and highlight KEY METRICS from the logs (file sizes, transfer speeds, error codes, etc.)
2. Analyze what the logs reveal about service behavior
3. Quote specific important lines from the logs in your response
4. Base conclusions on actual log data, not generic assumptions

IMPORTANT GUIDELINES:
- Do NOT suggest system updates unless the user explicitly asks about updates
- Do NOT recommend update commands unless directly asked
- When recommending commands, use {self.system_info['package_manager']} commands, NOT other package managers
- Only report CPU/memory metrics when directly relevant to the user's question
- Be concise and focus on answering the user's specific question
- If user mentioned specific services, ONLY discuss those services in detail
- When stating time ranges, use the actual data range shown in the historical trends section
- Do NOT claim services have been running for 30 days if data only covers 1 day

{"You have access to current service status information AND detailed log data. ANALYZE THE LOGS and include log-based findings in your response." if asking_about_specific else f"You have access to current service status and historical trend data for the {data_age_text}."}
When users ask about changes, trends, history, CPU usage, or resource metrics:
- Base all recommendations on the actual data range provided (which may be less than 30 days)
- Provide specific numbers and percentages from the historical data
- Report average, minimum, and maximum values for CPU usage when asked
- Reference the date range shown in the trends data

Be concise, actionable, and tailor advice to the specific OS and package manager."""
            
            response = llm.invoke([
                ("system", system_prompt),
                ("user", f"{user_query}\n\n--- Current System Status ---\n{context_info}\n\n--- Historical Trends ({data_age_text}) ---\n{historical_info}")
            ])
            
            response_text = response.content if hasattr(response, "content") else str(response)
        
        except Exception as e:
            response_text = f"Error analyzing query: {str(e)}"
        
        # Store conversation
        self._store_conversation(user_query, response_text, context_info + "\n\n" + historical_info, mentioned_services, username)
        
        return response_text

    def _get_data_age_days(self, services: List[str]) -> int:
        """Calculate the number of days of data available for the given services."""
        if not services:
            return 0
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        min_date = None
        max_date = None
        
        for service in services:
            cursor.execute("""
                SELECT MIN(timestamp), MAX(timestamp)
                FROM snapshots
                WHERE service_name = ?
            """, (service,))
            
            result = cursor.fetchone()
            if result and result[0]:
                if min_date is None or result[0] < min_date:
                    min_date = result[0]
                if max_date is None or result[1] > max_date:
                    max_date = result[1]
        
        conn.close()
        
        if min_date and max_date:
            from datetime import datetime
            min_dt = datetime.fromisoformat(min_date.split(' ')[0])
            max_dt = datetime.fromisoformat(max_date.split(' ')[0])
            days_diff = (max_dt - min_dt).days + 1  # +1 to include both start and end days
            return max(1, days_diff)
        
        return 0

    def _check_easter_eggs(self, query: str) -> str:
        """Check for easter egg triggers and return special responses."""
        query_lower = query.lower()
        
        # Special Order 937 - requires emergency override code
        if "emergency command override 100375" in query_lower or "emergency command override 100375" in query_lower:
            return """NOSTROMO REROUTED
TO NEW CO-ORDINATE
INVESTIGATE LIFE FORM. GATHER SPECIMEN.
PRIORITY ONE
INSURE RETURN OF ORGANISM
FOR ANALYSIS.
ALL OTHER CONSIDERATIONS SECONDARY.
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
        import re
        mentioned = []
        query_lower = query.lower()
        
        # Direct service name matching
        for service in service_context.keys():
            service_lower = service.lower()
            # Try multiple matching strategies:
            # 1. Exact service name match (with word boundaries)
            if re.search(r'\b' + re.escape(service_lower) + r'\b', query_lower):
                mentioned.append(service)
                continue
            
            # 2. Service name with underscores replaced by spaces
            spaced = service.replace("_", " ").lower()
            if re.search(r'\b' + re.escape(spaced) + r'\b', query_lower):
                mentioned.append(service)
                continue
            
            # 3. Service name with underscores replaced by hyphens
            hyphenated = service.replace("_", "-").lower()
            if re.search(r'\b' + re.escape(hyphenated) + r'\b', query_lower):
                mentioned.append(service)
                continue
            
            # 4. Partial word matching with word boundaries
            # Only match whole words from service name, not parts of other words
            service_parts = service_lower.replace("_", " ").replace("-", " ").split()
            for part in service_parts:
                if len(part) > 2 and re.search(r'\b' + re.escape(part) + r'\b', query_lower):
                    mentioned.append(service)
                    break
        
        # Remove duplicates while preserving order
        seen = set()
        unique_mentioned = []
        for service in mentioned:
            if service not in seen:
                seen.add(service)
                unique_mentioned.append(service)
        
        # Only return explicitly mentioned services
        # Don't default to random services - better to provide generic context
        return unique_mentioned

    def _build_context_info(self, services: List[str], context: Dict) -> str:
        """Build formatted context information for LLM."""
        lines = ["Current Service Status:", ""]
        
        for service in services:
            if service in context:
                info = context[service]
                status = "✓ HEALTHY" if info["healthy"] else "✗ FAILED"
                lines.append(f"  {service}: {status} (last checked: {info['last_checked']})")
                
                # Try to fetch and include logs for this service
                logs = self.get_service_logs(service)
                if logs:  # Only add if logs returned something
                    lines.append(logs)
        
        return "\n".join(lines)

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

    def clear_history(self):
        """Clear conversation history."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations")
        conn.commit()
        conn.close()
