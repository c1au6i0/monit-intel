# 🤖 Monit-Intel Agent

A **LangGraph + Llama 3.1** powered agent that monitors server health via Monit, analyzes logs intelligently, and performs automated root-cause analysis.

## 🚀 Quick Start

### Prerequisites
- Pixi (lightweight Conda alternative)
- Monit running on `localhost:2812` with XML API enabled
- Ollama running Llama 3.1:8b on GPU

### Environment Setup

**Option 1: Development (local .env file)**
```bash
# Create .env for local development
cat > .env << EOF
MONIT_USER=admin
MONIT_PASS=your_password
MONIT_URL=http://localhost:2812/_status?format=xml
EOF

# Install dependencies
pixi install
```

**Option 3: Production (systemd EnvironmentFile - RECOMMENDED)**

Credentials are stored securely in systemd drop-in files (not in git):

```bash
# Create systemd environment files (run once during setup)
sudo mkdir -p /etc/systemd/system/monit-intel-{agent,ingest}.service.d/

sudo tee /etc/systemd/system/monit-intel-agent.service.d/env.conf > /dev/null << EOF
[Service]
Environment="MONIT_USER=admin"
Environment="MONIT_PASS=your_password"
Environment="MONIT_URL=http://localhost:2812/_status?format=xml"
EOF

sudo tee /etc/systemd/system/monit-intel-ingest.service.d/env.conf > /dev/null << EOF
[Service]
Environment="MONIT_USER=admin"
Environment="MONIT_PASS=your_password"
Environment="MONIT_URL=http://localhost:2812/_status?format=xml"
EOF

# Restrict to root only
sudo chmod 600 /etc/systemd/system/monit-intel-*/service.d/env.conf

# Reload and restart services
sudo systemctl daemon-reload
sudo systemctl restart monit-intel-agent.service
```

**Benefits of Option 3:**
- ✅ Credentials NOT in project folder
- ✅ Credentials NOT in git history
- ✅ Only systemd process can read (chmod 600)
- ✅ Easy to rotate without redeploying code

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

**Prerequisites:**
- Set up systemd environment files with credentials (see "Environment Setup" above)

**Install services:**
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
- ✅ Credentials loaded from secure drop-in EnvironmentFile

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

## 👩‍💻 Mother: Interactive Chat Interface (Phase 6)

**Mother** is an interactive chat interface that lets you query the agent in natural language. It automatically injects service context and failure history into the LLM prompt.

### Mother REST API Endpoints

| Method | Endpoint | Purpose | Example |
|--------|----------|---------|---------|
| `POST` | `/mother/chat` | Chat with agent | `curl -X POST http://localhost:8000/mother/chat -H "Content-Type: application/json" -d '{"query": "Why is system_backup failing?"}'` |
| `GET` | `/mother/history` | View conversations | `curl http://localhost:8000/mother/history?limit=10` |
| `DELETE` | `/mother/clear` | Clear chat history | `curl -X DELETE http://localhost:8000/mother/clear` |

### Mother CLI

Use the interactive Mother CLI for a better UX:

```bash
# Chat with the agent
pixi run python mother-cli.py chat "Why is nordvpn_status failing?"

# View conversation history
pixi run python mother-cli.py history --limit 20

# Clear all conversations
pixi run python mother-cli.py clear

# Interactive mode (type 'help' for commands)
pixi run python mother-cli.py interactive
```

### How Mother Works

1. **Context Injection**: Extracts mentioned services from your query
2. **Status Lookup**: Fetches current service status and failure history
3. **Log Retrieval**: Uses LogReader to fetch relevant logs
4. **LLM Analysis**: Passes enriched context to Llama 3.1 for analysis
5. **Conversation Persistence**: Stores all chats in SQLite for history

**Example conversation:**
```
You: "Why is system_backup failing?"

Agent: [Analyzes current system_backup status, fetches last 150 lines of logs, 
        queries failure history over last 7 days, and provides root cause analysis]

Agent Response: "system_backup has failed 3 times in the last 7 days. The most 
recent failure shows disk space exhaustion in /data/tank. The backup_log 
indicates the backup process timed out after 4 hours when trying to sync 
2.5TB of data. Recommendation: Expand storage or increase timeout threshold."
```

---

## 🛠️ Actions: Safe Command Execution (Phase 7)

**Actions** allow the agent to suggest AND execute safe system commands for remediation. All actions are whitelisted, require user approval, and logged for audit.

### Safe Actions Whitelist

| Action | Command | Use Case |
|--------|---------|----------|
| `systemctl_restart` | `systemctl restart <service>` | Recover from transient failures |
| `systemctl_stop` | `systemctl stop <service>` | Prevent cascading failures |
| `systemctl_start` | `systemctl start <service>` | Bring service online |
| `systemctl_status` | `systemctl status <service>` | Get detailed systemd state |
| `monit_monitor` | `sudo monit monitor <service>` | Force Monit re-check |
| `monit_start` | `sudo monit start <service>` | Tell Monit to bring online |
| `monit_stop` | `sudo monit stop <service>` | Tell Monit to stop watching |
| `journalctl_view` | `journalctl -u <service> -n 50` | View service logs |

### Actions REST API Endpoints

| Method | Endpoint | Purpose | Example |
|--------|----------|---------|---------|
| `POST` | `/mother/actions/suggest` | Preview action without executing | `curl -X POST http://localhost:8000/mother/actions/suggest -d '{"action": "systemctl_restart", "service": "nordvpnd"}'` |
| `POST` | `/mother/actions/execute` | Execute action with approval | `curl -X POST http://localhost:8000/mother/actions/execute -d '{"action": "systemctl_status", "service": "nordvpnd", "approve": true}'` |
| `GET` | `/mother/actions/audit` | View action audit log | `curl http://localhost:8000/mother/actions/audit?limit=50` |

### Actions CLI

```bash
# Suggest an action (preview only, doesn't execute)
pixi run python mother-cli.py actions suggest systemctl_restart nordvpnd

# Execute with approval
pixi run python mother-cli.py actions execute systemctl_restart nordvpnd --approve

# View audit log (all executed actions)
pixi run python mother-cli.py actions audit --limit 50
```

### Execution Flow

```
1. Agent detects failure
2. Agent suggests action: "Consider restarting nordvpnd"
3. User confirms via CLI: --approve flag
4. Action is whitelisted and approved
5. Command executes (e.g., systemctl restart nordvpnd)
6. Result logged to audit_audit_log table in SQLite
7. User sees output + confirmation
```

### Blocked Commands

Never allowed, even with approval:
- `rm`, `kill`, `reboot`, `shutdown`
- Writing to `/etc/`, `/root/`, config files
- `apt`, `pip`, `npm` (package managers)
- `ifconfig`, `ip route` (network changes)
- `passwd`, `useradd`, `userdel` (user management)

---

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
