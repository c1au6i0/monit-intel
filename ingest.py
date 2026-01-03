import os
import sqlite3
import requests
import xmltodict
import json
import schedule
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def cleanup_old_snapshots(days_to_keep: int = 30):
    """
    Delete snapshots older than N days to prevent unbounded database growth.
    """
    try:
        conn = sqlite3.connect("monit_history.db")
        cursor = conn.cursor()
        
        cursor.execute(
            "DELETE FROM snapshots WHERE timestamp < datetime('now', '-' || ? || ' days')",
            (days_to_keep,)
        )
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            print(f"Cleaned {deleted_count} snapshots older than {days_to_keep} days")
    except Exception as e:
        print(f"Cleanup failed: {e}")

def run_ingestion():
    url = os.getenv("MONIT_URL")
    auth = (os.getenv("MONIT_USER"), os.getenv("MONIT_PASS"))
    
    try:
        r = requests.get(url, auth=auth, timeout=10)
        r.raise_for_status()
        data = xmltodict.parse(r.content)
        
        # Monit structure: monit -> service (list)
        services = data.get('monit', {}).get('service', [])
        if isinstance(services, dict): services = [services]
        
        conn = sqlite3.connect("monit_history.db")
        cursor = conn.cursor()
        
        # Create snapshots table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                service_name TEXT,
                status INTEGER,
                raw_json TEXT
            )
        """)
        
        # Create failure_history table for state tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS failure_history (
                service_name TEXT PRIMARY KEY,
                last_status INTEGER,
                last_checked DATETIME DEFAULT CURRENT_TIMESTAMP,
                times_failed INTEGER DEFAULT 0
            )
        """)

        for s in services:
            status = int(s.get('status', 0))
            cursor.execute(
                "INSERT INTO snapshots (service_name, status, raw_json) VALUES (?, ?, ?)",
                (s['name'], status, json.dumps(s))
            )
            
            # Update failure history
            cursor.execute(
                """INSERT OR REPLACE INTO failure_history 
                   (service_name, last_status, last_checked, times_failed) 
                   VALUES (?, ?, CURRENT_TIMESTAMP, 
                   COALESCE((SELECT times_failed FROM failure_history WHERE service_name = ?), 0) + CASE WHEN ? != 0 THEN 1 ELSE 0 END)""",
                (s['name'], status, s['name'], status)
            )
        
        conn.commit()
        conn.close()
        
        print(f"Ingested {len(services)} services at {datetime.now().strftime('%H:%M:%S')}")
        
        # Cleanup old snapshots (30 day retention)
        cleanup_old_snapshots(days_to_keep=30)
        
    except Exception as e:
        print(f"Ingestion failed: {e}")

def schedule_ingestion(interval_minutes: int = 5):
    """
    Schedule ingestion to run every N minutes.
    """
    schedule.every(interval_minutes).minutes.do(run_ingestion)
    
    print(f"📅 Ingestion scheduled every {interval_minutes} minutes")
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--schedule":
        # Run in scheduled mode (e.g., for systemd service)
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        schedule_ingestion(interval)
    else:
        # Run once and exit
        run_ingestion()
