#!/usr/bin/env python3
import sqlite3
import sys

if len(sys.argv) < 2:
    print("Usage: check_service_history.py <service_name>")
    sys.exit(1)

service = sys.argv[1]
conn = sqlite3.connect('monit_history.db')
cursor = conn.cursor()
cursor.execute(
    "SELECT timestamp, status FROM snapshots WHERE service_name = ? ORDER BY timestamp LIMIT 5",
    (service,)
)

records = cursor.fetchall()
print(f"First 5 records for {service}:")
for ts, status in records:
    print(f"  {ts} - Status: {status}")

cursor.execute(
    "SELECT timestamp, status FROM snapshots WHERE service_name = ? ORDER BY timestamp DESC LIMIT 5",
    (service,)
)

records = cursor.fetchall()
print(f"\nLast 5 records for {service}:")
for ts, status in records:
    print(f"  {ts} - Status: {status}")

cursor.execute(
    "SELECT COUNT(*) FROM snapshots WHERE service_name = ?",
    (service,)
)
count = cursor.fetchone()[0]
print(f"\nTotal records: {count}")
