"""
Hybrid log reader tool for the Monit-Intel agent.
Supports:
- Tailing append logs
- Finding the newest file in a directory
- Querying journalctl for systemd services
"""

import os
import subprocess
import glob
from pathlib import Path
from typing import Optional

class LogReader:
    """
    Flexible log reader supporting multiple strategies.
    Each service can have configurable max_lines for context depth.
    """
    
    def __init__(self, max_lines: int = 100):
        """Initialize with default max line limit (can be overridden per-service)."""
        self.max_lines = max_lines
    
    def tail_file(self, filepath: str) -> Optional[str]:
        """
        Tail the last N lines of a flat log file.
        
        Args:
            filepath: Absolute path to the log file
            
        Returns:
            Last N lines of the file, or None if file doesn't exist
        """
        if not os.path.exists(filepath):
            return None
        
        try:
            result = subprocess.run(
                ["tail", "-n", str(self.max_lines), filepath],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout
        except Exception as e:
            return f"Error reading {filepath}: {e}"
    
    def find_newest_file(self, directory_pattern: str) -> Optional[str]:
        """
        Find the newest file matching a glob pattern and return its contents.
        
        Args:
            directory_pattern: Glob pattern (e.g., '/data/tank/backups/sys_restore/backup_log_*.log')
            
        Returns:
            Contents of the newest matching file, or None
        """
        files = glob.glob(directory_pattern)
        if not files:
            return None
        
        # Sort by modification time, get the newest
        newest = max(files, key=lambda f: os.path.getmtime(f))
        
        try:
            with open(newest, 'r') as f:
                lines = f.readlines()
                # Return the last N lines
                return "".join(lines[-self.max_lines:])
        except Exception as e:
            return f"Error reading {newest}: {e}"
    
    def query_journalctl(self, unit: str, user_service: bool = False) -> Optional[str]:
        """
        Query systemd journal for a specific service.
        
        Args:
            unit: Service name (e.g., 'nordvpnd.service')
            user_service: If True, query user journal instead of system journal
            
        Returns:
            Recent journal entries for the service
        """
        try:
            cmd = ["journalctl"]
            if user_service:
                cmd.append("--user")
            cmd.extend(["-u", unit, "-n", str(self.max_lines), "--no-pager"])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout
            else:
                return f"Error querying {unit}: {result.stderr}"
        except Exception as e:
            return f"Error querying journalctl: {e}"
    
    def get_logs_for_service(self, service_name: str) -> dict:
        """
        Smart router: Given a Monit service name, return relevant logs.
        Uses the Log Registry from the plan.
        Each service has configurable max_lines for context depth.
        
        Args:
            service_name: Name of the Monit service that failed
            
        Returns:
            Dictionary with log content and metadata
        """
        log_registry = {
            "system_backup": {
                "strategy": "newest_file",
                "pattern": "/data/tank/backups/sys_restore/backup_log_*.log",
                "max_lines": 150  # Verbose service, needs more context
            },
            "nordvpn_reconnect": {
                "strategy": "tail_file",
                "path": "/var/log/nordvpn-reconnect.log",
                "max_lines": 75   # Medium verbosity
            },
            "nordvpn_connected": {
                "strategy": "tail_file",
                "path": "/var/log/nordvpn-reconnect.log",
                "max_lines": 75   # Same as nordvpn_reconnect (actual Monit service name)
            },
            "nordvpn_status": {
                "strategy": "journalctl",
                "unit": "nordvpnd.service",
                "max_lines": 50   # Terse service
            },
            "nordvpnd": {
                "strategy": "journalctl",
                "unit": "nordvpnd.service",
                "max_lines": 50   # Same as nordvpn_status (actual Monit service name)
            },
            "gamma_conn": {
                "strategy": "journalctl",
                "unit": "tailscaled.service",
                "max_lines": 75   # Medium verbosity
            },
            "tailscaled": {
                "strategy": "journalctl",
                "unit": "tailscaled.service",
                "max_lines": 75   # Same as gamma_conn (actual Monit service name)
            },
            "network_resurrect": {
                "strategy": "tail_file",
                "path": "/var/log/monit-network-restart.log",
                "max_lines": 100  # Network logs can be verbose
            },
            "sanoid_errors": {
                "strategy": "journalctl",
                "unit": "sanoid.service",
                "max_lines": 100  # Storage operations can be detailed
            },
            "zfs-zed": {
                "strategy": "journalctl",
                "unit": "zfs-zed.service",
                "max_lines": 100  # ZFS event daemon logs
            },
            "smbd": {
                "strategy": "journalctl",
                "unit": "smbd.service",
                "max_lines": 75  # Samba file sharing daemon
            },
            "syncthing": {
                "strategy": "journalctl",
                "unit": "syncthing.service",
                "user_service": True,
                "max_lines": 75  # File synchronization service (user service)
            },
            # Docker-based services - logs require docker exec with sudo
            # These are explicitly marked to skip journalctl fallback
            "immich_server_running": {
                "strategy": "docker",
                "container": "immich-server",
                "max_lines": 100,
                "note": "Docker container - logs require docker access"
            },
            "immich_ml_running": {
                "strategy": "docker",
                "container": "immich-machine-learning",
                "max_lines": 100,
                "note": "Docker container - logs require docker access"
            },
            "immich_pg_running": {
                "strategy": "docker",
                "container": "immich-postgres",
                "max_lines": 100,
                "note": "Docker container - logs require docker access"
            },
            "immich_redis_running": {
                "strategy": "docker",
                "container": "immich-redis",
                "max_lines": 100,
                "note": "Docker container - logs require docker access"
            },
            "jellyfin_running": {
                "strategy": "docker",
                "container": "jellyfin",
                "max_lines": 100,
                "note": "Docker container - logs require docker access"
            },
            "miniflux_running": {
                "strategy": "docker",
                "container": "miniflux",
                "max_lines": 100,
                "note": "Docker container - logs require docker access"
            },
            "postgres_running": {
                "strategy": "docker",
                "container": "postgres",
                "max_lines": 100,
                "note": "Docker container - logs require docker access"
            }
        }
        
        # Try to find service in registry, otherwise use smart fallback
        if service_name not in log_registry:
            # Fallback: Try journalctl with service name as unit
            # Convert Monit service names to likely systemd unit names
            unit_names = [
                f"{service_name}.service",      # Direct match
                f"{service_name.replace('_', '-')}.service",  # Replace underscores
                service_name,                    # Raw service name (for custom units)
            ]
            
            # Try each unit name
            for unit in unit_names:
                logs = self.query_journalctl(unit)
                if logs and "Error querying" not in logs:
                    return {
                        "service": service_name,
                        "strategy": "journalctl_fallback",
                        "logs": logs
                    }
            
            # If no journalctl logs found, return empty (will be silently skipped)
            return {
                "service": service_name,
                "strategy": None,
                "logs": None
            }
        
        config = log_registry[service_name]
        strategy = config["strategy"]
        
        # Skip docker-based services (require sudo access)
        if strategy == "docker":
            return {
                "service": service_name,
                "strategy": "docker",
                "logs": None,
                "note": config.get("note", "Docker container logs require sudo access")
            }
        
        max_lines = config.get("max_lines", self.max_lines)
        
        # Temporarily set instance max_lines for this fetch
        original_max = self.max_lines
        self.max_lines = max_lines
        
        if strategy == "tail_file":
            logs = self.tail_file(config["path"])
        elif strategy == "newest_file":
            logs = self.find_newest_file(config["pattern"])
        elif strategy == "journalctl":
            user_service = config.get("user_service", False)
            logs = self.query_journalctl(config["unit"], user_service=user_service)
        else:
            logs = None
        
        # Restore original max_lines
        self.max_lines = original_max
        
        return {
            "service": service_name,
            "strategy": strategy,
            "logs": logs
        }


# Singleton instance for use in agent nodes
log_reader = LogReader(max_lines=100)


def get_service_logs(service_name: str) -> str:
    """
    Convenience function for LangGraph nodes to fetch logs.
    
    Args:
        service_name: Monit service name
        
    Returns:
        Formatted log string or error message
    """
    result = log_reader.get_logs_for_service(service_name)
    
    if result.get("error"):
        return f"Error: {result['error']}"
    
    logs = result.get("logs")
    if not logs:
        return f"No logs found for {service_name}"
    
    return f"\n=== Logs for {service_name} ({result['strategy']}) ===\n{logs}"
