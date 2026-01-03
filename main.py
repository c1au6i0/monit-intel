"""
Monit-Intel Agent Daemon with REST API
Continuously monitors SQLite for service failures and runs analysis.
Also provides REST API for interactive querying.
"""

import time
import schedule
import threading
from agent.graph import build_graph
from agent.api import app
import uvicorn


def run_agent_once():
    """Execute one full analysis cycle."""
    workflow = build_graph()
    
    result = workflow.invoke({
        "messages": [],
        "context_data": "",
        "is_critical": False
    })
    
    return result


def run_background_agent(check_interval_minutes: int = 5):
    """
    Run the agent in background checking every N minutes.
    This function runs in a separate thread.
    """
    schedule.every(check_interval_minutes).minutes.do(run_agent_once)
    
    print(f"Background agent scheduled every {check_interval_minutes} minutes")
    
    # Keep the scheduler running
    while True:
        schedule.run_pending()
        time.sleep(1)


def run_api_server(host: str = "0.0.0.0", port: int = 8000):
    """
    Run the REST API server.
    This function runs in a separate thread.
    """
    print(f"Starting API server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_with_api(check_interval_minutes: int = 5, api_port: int = 8000):
    """
    Run agent daemon + REST API server in parallel.
    """
    print(f"🚀 Monit-Intel Agent Starting (with API on port {api_port})...")
    
    # Start background agent thread
    agent_thread = threading.Thread(
        target=run_background_agent,
        args=(check_interval_minutes,),
        daemon=True
    )
    agent_thread.start()
    
    # Start API server in main thread
    run_api_server(port=api_port)


def run_agent_daemon(check_interval_minutes: int = 5):
    """
    Run the agent as a continuous daemon (without REST API).
    Checks for failures every N minutes.
    """
    print(f"🚀 Monit-Intel Agent Starting (checking every {check_interval_minutes} min)...")
    
    # Schedule the task
    schedule.every(check_interval_minutes).minutes.do(run_agent_once)
    
    print(f"📅 Scheduled to check every {check_interval_minutes} minutes")
    print("Ctrl+C to stop\n")
    
    # Keep running
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Single run mode
        run_agent_once()
    elif len(sys.argv) > 1 and sys.argv[1] == "--api":
        # Daemon + API mode (recommended)
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        port = int(sys.argv[3]) if len(sys.argv) > 3 else 8000
        run_with_api(check_interval_minutes=interval, api_port=port)
    else:
        # Daemon mode only
        interval = int(sys.argv[1]) if len(sys.argv) > 1 else 5
        run_agent_daemon(interval)

