# 🤖 Monit-Intel Agent

A **LangGraph + Llama 3.1** powered agent that monitors server health via Monit, analyzes logs intelligently, and performs automated root-cause analysis.

## 🚀 Quick Start

### Prerequisites
- Pixi (lightweight Conda alternative)
- Monit running on `localhost:2812` with XML API enabled
- Ollama running Llama 3.1:8b on GPU

### Environment Setup

```bash
# Configure credentials in .env
cat > .env << EOF
MONIT_USER=admin
MONIT_PASS=your_password
MONIT_URL=http://localhost:2812/_status?format=xml
EOF

# Install dependencies
pixi install
```

### Manual Run Commands

```bash
# Single ingestion run
pixi run python ingest.py

# Run agent analysis once
pixi run python main.py --once

# Start agent daemon (checks every 5 minutes)
pixi run python main.py

# Start daemon with REST API (port 8000)
pixi run python main.py --api 5 8000
```

### Production Deployment (Systemd)

```bash
# Install systemd services for auto-startup on boot
sudo bash /home/heverz/py_projects/monit-intel/install-services.sh

# Check service status
systemctl status monit-intel-agent.service
systemctl status monit-intel-ingest.timer

# View live logs
journalctl -u monit-intel-agent.service -f

# Check next scheduled ingest
systemctl list-timers monit-intel-ingest.timer
```

**What systemd provides:**
- ✅ Agent daemon runs on boot automatically
- ✅ Ingest timer triggers every 5 minutes
- ✅ Auto-restart on crash with 10-sec backoff
- ✅ REST API always available on `localhost:8000`

## 🏗️ Architecture

### Components

| Module | Purpose |
|--------|---------|
| `ingest.py` | Polls Monit XML API every 5 min, stores snapshots, cleans old data |
| `main.py` | Daemon runner - checks for failures every 5 min |
| `agent/graph.py` | LangGraph workflow definition (DAG compilation) |
| `agent/state.py` | LangGraph state definition |
| `agent/nodes.py` | Individual workflow nodes (database, log fetching, LLM) |
| `tools/log_reader.py` | Hybrid log reader (files, journalctl, glob patterns) |

### Data Flow

```
Monit XML API (every 5 min)
     ↓
[ingest.py] 
     ├→ INSERT snapshots
     ├→ UPDATE failure_history (track state)
     └→ DELETE old snapshots (30-day retention)
     ↓
[SQLite: snapshots + failure_history]
     ↓
[main.py daemon] (checks every 5 min)
     ├→ detect_failures: Query NEW/CHANGED failures
     ├→ fetch_logs: Pull relevant logs (per-service line limits)
     └→ analyze_llm: Llama 3.1 root-cause analysis
     ↓
Console output (skips LLM for unchanged failures)
```

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    MONIT-INTEL AGENT SYSTEM                     │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│  Monit Server    │
│  (beta-boy)      │
│  Port 2812       │
└────────┬─────────┘
         │ XML API
         │ GET /_status?format=xml
         ▼
    ┌─────────────────────────────────────────┐
    │   ingest.py (Scheduler Process)         │
    │   - Runs every 5 minutes                │
    │   - Polls Monit XML                     │
    │   - Stores snapshots                    │
    │   - Updates failure_history             │
    │   - Cleans old data (30-day policy)     │
    └────────────┬────────────────────────────┘
                 │ INSERT/UPDATE
                 ▼
    ┌─────────────────────────────────────────┐
    │   SQLite: monit_history.db              │
    │   - snapshots (rolling 30 days)         │
    │   - failure_history (state tracking)    │
    └────────────┬────────────────────────────┘
                 │
                 │ SELECT (poll every 5 min)
                 ▼
    ┌─────────────────────────────────────────┐
    │   main.py (Continuous Agent Daemon)     │
    │   └─ detect_failures()                  │
    │      Query for NEW/CHANGED failures     │
    │      (skips unchanged ones)             │
    └────────────┬────────────────────────────┘
                 │ If NEW/CHANGED
                 ▼
    ┌─────────────────────────────────────────┐
    │   agent/graph.py (LangGraph DAG)        │
    │   └─ fetch_logs_and_context()           │
    │      Use Log Registry                   │
    │      (per-service max_lines)            │
    └────────────┬────────────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
    ┌────────────┐   ┌──────────────┐
    │ Log Files  │   │ Journalctl   │
    │ (tail)     │   │ (systemd)    │
    │ (glob)     │   │              │
    └────────────┘   └──────────────┘
        │                 │
        └────────┬────────┘
                 │ Log content (per-service lines)
                 ▼
    ┌─────────────────────────────────────────┐
    │   agent/graph.py                        │
    │   └─ analyze_with_llm()                 │
    │      Llama 3.1:8b Analysis              │
    │      (2-5 sec inference)                │
    │      (Only runs for NEW/CHANGED)        │
    └────────────┬────────────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────────────────┐
    │   Console Output                        │
    │   - Root cause analysis                 │
    │   - Suggested remediation               │
    │   - State tracking (NEW vs ONGOING)     │
    └─────────────────────────────────────────┘
```

## 🌐 REST API

Once the agent is running (via systemd or manually with `--api`), the REST API is available on `localhost:8000`.

### Endpoints

| Method | Endpoint | Purpose | Example |
|--------|----------|---------|---------|
| `GET` | `/` | API info & endpoints | `curl http://localhost:8000/` |
| `GET` | `/health` | DB status & snapshot count | `curl http://localhost:8000/health` |
| `GET` | `/status` | All services + last_checked | `curl http://localhost:8000/status` |
| `POST` | `/analyze` | Trigger analysis | `curl -X POST http://localhost:8000/analyze` |
| `GET` | `/history?service=X&days=7` | Failure history for service | `curl "http://localhost:8000/history?service=system_backup&days=7"` |
| `GET` | `/logs/{service}` | Latest logs for service | `curl http://localhost:8000/logs/nordvpn_status` |

### Examples

```bash
# Check if agent is healthy
curl http://localhost:8000/health
# {"status": "healthy", "database": "connected", "snapshots": 150}

# Get all service statuses
curl http://localhost:8000/status | jq '.[] | {service: .service, status: .status}'

# Trigger analysis (returns LLM output if failures detected)
curl -X POST http://localhost:8000/analyze

# Query failure history for last 7 days
curl "http://localhost:8000/history?service=system_backup&days=7"

# Get latest logs for a service
curl http://localhost:8000/logs/nordvpn_status | jq '.logs' | head -20
```

## 🧠 Features

### ✅ Hybrid State Management
- Tracks per-service failure history in SQLite
- Detects NEW vs ONGOING failures
- Skips LLM analysis for unchanged failures (saves GPU compute)
- Example: Service fails → analyzed. Still failing 5 min later → skipped

### ✅ 30-Day Data Retention
- Automatic cleanup after each ingestion
- Keeps database size ~20-25MB max
- Suitable for 30 days of history at 30 services / 5 min interval

### ✅ Configurable Per-Service Log Limits
Each service gets optimized context window:
- `system_backup`: 150 lines (verbose backups)
- `network_resurrect`: 100 lines (network operations)
- `gamma_conn`, `nordvpn_reconnect`: 75 lines (medium verbosity)
- `zfs_sanoid`: 100 lines (storage operations)
- `nordvpn_status`: 50 lines (terse service)

### ✅ Read-Only Analysis
- Agent reads logs but cannot execute destructive commands
- Safe for automated monitoring

## 📜 Log Registry

The agent automatically knows which logs to fetch for each service:

| Service | Strategy | Path/Unit | Max Lines |
|---------|----------|-----------|-----------|
| `system_backup` | Latest file | `/data/tank/backups/sys_restore/backup_log_*.log` | 150 |
| `nordvpn_reconnect` | Tail file | `/var/log/nordvpn-reconnect.log` | 75 |
| `nordvpn_status` | Journalctl | `nordvpnd.service` | 50 |
| `gamma_conn` | Journalctl | `tailscaled.service` | 75 |
| `network_resurrect` | Tail file | `/var/log/monit-network-restart.log` | 100 |
| `zfs_sanoid` | Journalctl | `sanoid.service` | 100 |

## 🛠️ Configuration

### Extend the Log Registry

Edit `tools/log_reader.py`, function `get_logs_for_service()`:

```python
log_registry = {
    "my_service": {
        "strategy": "tail_file",           # or "newest_file", "journalctl"
        "path": "/path/to/logfile.log",   # for tail_file
        "pattern": "glob_pattern",         # for newest_file
        "unit": "service.service",         # for journalctl
        "max_lines": 75                    # customize per-service context
    }
}
```

### Customize Llama Prompt

Edit `agent/graph.py`, function `analyze_with_llm()`:

```python
system_prompt = """..."""  # Modify the system message here
```

## 📊 Database Schema

### snapshots (30-day rolling window)
```sql
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    service_name TEXT,
    status INTEGER,       -- 0 = OK, other = failed
    raw_json TEXT        -- Full Monit service data
);
```

### failure_history (state tracking)
```sql
CREATE TABLE failure_history (
    service_name TEXT PRIMARY KEY,
    last_status INTEGER,
    last_checked DATETIME,
    times_failed INTEGER   -- How many times this service has failed
);
```

## 🔐 Security Notes

- ✅ **Read-only:** Agent cannot execute destructive commands (`rm`, `kill`)
- ✅ **Scoped logs:** Only reads paths specified in Log Registry
- ✅ **Context limit:** Per-service max_lines prevents VRAM overflow
- ⚠️ **Permissions:** Ensure Pixi user has read access to all log locations

## 🐛 Troubleshooting

### Monit connection fails
```bash
curl -u admin:password http://localhost:2812/_status?format=xml
```

### Ollama model not found
```bash
ollama run llama3.1:8b
```

### Journal access denied
```bash
# Add Pixi user to systemd-journal group
sudo usermod -aG systemd-journal $(whoami)
```

### Check database state
```bash
/home/heverz/.pixi/bin/pixi run python << 'EOF'
import sqlite3
conn = sqlite3.connect("monit_history.db")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM snapshots")
print(f"Total snapshots: {cursor.fetchone()[0]}")
conn.close()
## 🐛 Troubleshooting

### Monit connection fails
```bash
curl -u admin:password http://localhost:2812/_status?format=xml
```

### Ollama model not found
```bash
ollama run llama3.1:8b
```

### Journal access denied
```bash
# Add your user to systemd-journal group
sudo usermod -aG systemd-journal $(whoami)
newgrp systemd-journal
```

### Check database state
```bash
pixi run python << 'EOF'
import sqlite3
conn = sqlite3.connect("monit_history.db")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM snapshots")
print(f"Total snapshots: {cursor.fetchone()[0]}")
conn.close()
EOF
```

### Systemd service won't start
```bash
# Check detailed error
journalctl -u monit-intel-agent.service -n 50

# Verify service file syntax
systemd-analyze verify /etc/systemd/system/monit-intel-agent.service
```

### API port 8000 already in use
```bash
# Kill the old process
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Restart service
sudo systemctl restart monit-intel-agent.service
```

## 📝 Next Steps

- [ ] Add Slack/email alert escalation
- [ ] Create safe remediation action nodes
- [ ] Build Grafana dashboard for history
- [ ] Fine-tune Llama model on server logs
- [ ] Extend to multi-host monitoring
