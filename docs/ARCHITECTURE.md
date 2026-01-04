# 🏗️ Monit-Intel Architecture

Comprehensive technical documentation of the Monit-Intel agent system, including component design, data flow, and implementation details.

---

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [Components](#components)
3. [Two Parallel Systems](#two-parallel-systems)
4. [Data Flow](#data-flow)
5. [Historical Data & Snapshots](#historical-data--snapshots)
6. [System Context Injection](#system-context-injection)
7. [Per-Service Log Configuration](#per-service-log-configuration)
8. [Database Schema](#database-schema)
9. [WebSocket Protocol](#websocket-protocol)

---

## System Overview

**Monit-Intel** is a dual-workflow system that monitors server health and analyzes failures using LLM-powered reasoning:

| Aspect | Details |
|--------|---------|
| **LLM Engine** | Llama 3.1:8b via Ollama (port 11434) |
| **API Framework** | FastAPI with REST + WebSocket support |
| **Port** | 8000 (development), systemd service (production) |
| **Database** | SQLite (`monit_history.db`) with 30-day rolling retention |
| **Monitoring Interval** | 5 minutes (configurable) |
| **Session Timeout** | 30 minutes with activity reset |

---

## Components

### Core Modules

| Module | Purpose | Key Function |
|--------|---------|---------------|
| `src/monit_intel/ingest.py` | Data ingestion daemon | Polls Monit XML API every 5 min, stores snapshots, deletes old records |
| `src/monit_intel/main.py` | Failure detection daemon | Runs LangGraph workflow every 5 min |
| `src/monit_intel/hello_mother.py` | Interactive CLI interface | REPL for direct agent queries |
| `src/monit_intel/agent/api.py` | REST + WebSocket server | FastAPI server with HTTP Basic Auth and WebSocket endpoints |
| `src/monit_intel/agent/graph.py` | Workflow orchestration | LangGraph DAG with 3-node workflow |
| `src/monit_intel/agent/state.py` | Workflow state schema | TypedDict for workflow state management |
| `src/monit_intel/agent/nodes.py` | Workflow nodes | Individual node implementations (detect, fetch, analyze) |
| `src/monit_intel/agent/mother.py` | Chat manager | Context injection, historical trends, LLM interface |
| `src/monit_intel/agent/actions.py` | Safe command executor | Whitelisted actions with audit logging |
| `src/monit_intel/tools/log_reader.py` | Log aggregator | Hybrid reader (tail, glob, journalctl) with per-service limits |
| `src/monit_intel/chat_auth.py` | Authentication system | PBKDF2-SHA256 password hashing, SQLite storage |

### Frontend

| File | Purpose |
|------|---------|
| `src/monit_intel/agent/static/chat.html` | Web UI with Alien aesthetic, WebSocket client, login overlay, 30-min timeout |

---

## Two Parallel Systems

The Monit-Intel system operates two independent workflows simultaneously:

### System 1: Background Agent (Automated Failure Detection)

**Trigger:** Every 5 minutes automatically

**Workflow (LangGraph DAG):**

```
┌─────────────────────────────────────┐
│ START (5-min timer interval)        │
└────────────┬────────────────────────┘
             ▼
┌─────────────────────────────────────────────────┐
│ [1] detect_failures()                           │
│ ├─ Query snapshots table: WHERE status != 0    │
│ ├─ Check failure_history: is it NEW/CHANGED?   │
│ ├─ Set is_critical=True only for NEW/CHANGED   │
│ └─ Result: state.failures, state.is_critical   │
└────────────┬────────────────────────────────────┘
             │
             ▼ (if is_critical=True)
┌─────────────────────────────────────────────────┐
│ [2] fetch_logs_and_context()                    │
│ ├─ For each failed service:                     │
│ │  ├─ Look up in log_registry                  │
│ │  ├─ tail_file: read last N lines            │
│ │  ├─ newest_file: glob pattern → tail        │
│ │  └─ journalctl: systemd journal query       │
│ ├─ Apply max_lines per service (50-150)       │
│ └─ Result: state.logs, state.service_context  │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ [3] analyze_with_llm()                          │
│ ├─ Build prompt with logs + service context    │
│ ├─ Send to Llama 3.1:8b (Ollama)              │
│ ├─ LLM analyzes root cause                     │
│ └─ Result: state.analysis, recommendations    │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ END (output to console logs)                    │
│ Print: Root cause analysis + recommendations   │
└─────────────────────────────────────────────────┘
```

**Smart Logic: is_critical Flag**

```
failure_history state    → is_critical   → Action
─────────────────────────────────────────────────
Service NEW: healthy→failed    True        Analyze
Service ONGOING: failed→failed  False       Skip (save GPU)
Service CHANGED: status change  True        Analyze
Service RECOVERED: failed→healthy False     Done
```

This flag prevents re-analyzing the same failure repeatedly, saving GPU compute.

**Console Output Example:**
```
[2026-01-03 20:53:38] detect_failures: Found 1 NEW failure (nordvpnd)
[2026-01-03 20:53:40] fetch_logs_and_context: Fetching logs for nordvpnd
[2026-01-03 20:53:45] analyze_with_llm: Llama 3.1 analysis complete
  → Root cause: Connection timeout to NordVPN API
  → Recent action: System restarted at 20:45, nordvpnd may be slow to reconnect
  → Recommendation: If disconnected >5 min, run: sudo systemctl restart nordvpnd
```

---

### System 2: Interactive Chat (Mother / MU/TH/UR)

**Trigger:** User sends message via WebSocket

**Flow:**

```
User Types in Browser
     ▼
Browser sends JSON via WebSocket (/ws/chat)
     ▼
FastAPI receives on /ws/chat endpoint
     ▼
Mother.query_agent(user_query)
     ├─ Extract service names from query
     ├─ get_historical_trends():
     │  ├─ Query snapshots (last 30 days)
     │  ├─ Calculate CPU/memory min/avg/max per service
     │  ├─ Compute failure rates
     │  └─ Format into human-readable text
     ├─ Fetch current service statuses
     ├─ Get recent logs (last 5-10 min per service)
     ├─ Detect OS: Ubuntu? Fedora? Arch?
     ├─ Build system prompt with context
     │  └─ "You are MU/TH/UR on Ubuntu 24.04 (apt)"
     └─ Send enriched prompt to Llama 3.1
           │
           ▼
Llama 3.1:8b processes enriched context
     ├─ Understands OS-specific commands
     ├─ Uses historical trend data in analysis
     ├─ References actual logs when appropriate
     └─ Generates conversational response
           │
           ▼
Response streamed back via WebSocket
     ▼
Browser displays in chat UI (Alien aesthetic)
```

**Example Conversation:**

```
User: "What about CPU usage in the last 30 days?"

Mother gathers:
- docker: avg 0.0%, min 0.0%, max 0.5%
- nordvpnd: avg 0.2%, min 0.1%, max 0.4%
- tailscaled: avg 0.1%, min 0.0%, max 0.2%
- Memory: docker 101MB (0.1%), nordvpnd 119MB (0.1%)

Llama Response:
"Based on historical trend data, CPU usage is minimal and stable across all services.
Docker averages 0.0% with peaks at 0.5%, while nordvpnd consistently uses about 0.2%.
All services show healthy resource utilization with stable trends. No concerning patterns."
```

---

### Key Differences

| Aspect | Background Agent | Mother Chat |
|--------|---|---|
| **Trigger** | Every 5 min automatically | User sends message |
| **Purpose** | Proactive failure detection | Answer user questions |
| **Workflow** | Multi-node LangGraph DAG | Single LLM call |
| **Output** | Console logs | Conversational response |
| **Context** | Current failure data | 30-day historical + current |
| **GPU Usage** | Only when is_critical=True | On every message |

---

## Data Flow

### Complete System Diagram

```
┌───────────────────────────────────────────────────────────┐
│                   MONIT SERVER                            │
│              (localhost:2812)                             │
│  Monitors 30+ services                                    │
│  Exposes: /_status?format=xml                            │
└─────────────────────┬─────────────────────────────────────┘
                      │ GET /_status?format=xml
                      │ (every 5 min)
                      ▼
        ┌─────────────────────────┐
        │   ingest.py daemon      │
        │ ├─ Parse Monit XML      │
        │ ├─ Extract metrics      │
        │ └─ Store snapshots      │
        └────────────┬────────────┘
                     │ INSERT/UPDATE/DELETE
                     ▼
    ┌────────────────────────────────────────┐
    │   SQLite: monit_history.db             │
    │                                        │
    │  ├─ snapshots (30-day rolling)        │
    │  ├─ failure_history (state tracking)  │
    │  ├─ conversations (chat history)      │
    │  ├─ action_audit_log (actions taken)  │
    │  └─ chat_credentials (hashed passwords)
    └────────────┬───────────────────────────┘
                 │
        ┌────────┴─────────────┐
        │                      │
        ▼ (every 5 min)        ▼ (on user message)
   ┌─────────────┐        ┌──────────────┐
   │Background   │        │Mother Chat   │
   │Agent        │        │              │
   │(main.py)    │        │(mother.py)   │
   └──────┬──────┘        └──────┬───────┘
          │                      │
          ▼                      ▼
  ┌──────────────────┐  ┌────────────────────┐
  │detect_failures() │  │get_historical_     │
  │                  │  │trends()            │
  │fetch_logs_and_   │  │                    │
  │context()         │  │Detect OS context   │
  │                  │  │Fetch service info  │
  │analyze_with_llm()│  │                    │
  └────────┬─────────┘  └────────┬───────────┘
           │                     │
           ▼                     ▼
   ┌──────────────────────────────────────┐
   │   Ollama (port 11434)                │
   │   Llama 3.1:8b                       │
   │   (2-5 sec inference)                │
   └────────────┬─────────────────────────┘
                │
                ▼
   ┌──────────────────────────────────────┐
   │   FastAPI Server (port 8000)         │
   │   ├─ REST endpoints                  │
   │   ├─ WebSocket /ws/chat              │
   │   └─ HTTP Basic Auth                 │
   └────────────┬─────────────────────────┘
                │
        ┌───────┴──────────┐
        │                  │
        ▼                  ▼
  Console output      Browser (chat.html)
  (root cause)        (Alien UI)
```

### Database Lifecycle

1. **Ingest (every 5 min):**
   - Fetch Monit XML
   - Parse service data: status, CPU%, memory, uptime, threads, etc.
   - INSERT into snapshots with full raw_json
   - UPDATE failure_history (track state changes)
   - DELETE snapshots older than 30 days

2. **Background Agent (every 5 min):**
   - SELECT from snapshots WHERE status != 0
   - Check failure_history for NEW/CHANGED
   - If is_critical=True: fetch logs and analyze
   - Console output logs analysis

3. **Mother Chat (on user message):**
   - SELECT from snapshots (last 30 days)
   - Calculate trends (min/max/avg per service)
   - SELECT from conversations (chat history)
   - Send enriched prompt to LLM
   - INSERT new conversation record
   - Stream response via WebSocket

---

## Historical Data & Snapshots

### Snapshot Structure

Every 5 minutes, `ingest.py` stores complete service metadata:

```json
{
  "id": 12345,
  "timestamp": "2026-01-03T20:53:38",
  "service_name": "docker",
  "status": 0,
  "raw_json": {
    "name": "docker",
    "status": "ok",
    "statuschanged": 1704222600,
    "monitstatus": "active",
    "pendingaction": "none",
    "timeout": false,
    "uptime": 517935,
    "threads": 33,
    "uid": 0,
    "gid": 0,
    "uptime_percent": 100,
    "cpu": {
      "percent": "0.5",
      "percenttotal": "0.5",
      "percentchange": "1"
    },
    "memory": {
      "percent": "0.1",
      "percenttotal": "0.1",
      "kilobyte": "103752",
      "kilobytetotal": "103752",
      "percentchange": "0"
    },
    "request": {
      "count": 512,
      "errors": 0
    }
  }
}
```

### Historical Trend Extraction

The `get_historical_trends()` function in `mother.py` processes raw snapshots:

```python
def get_historical_trends(self, days=30):
    """
    Extract CPU, memory, failure metrics from last N days of snapshots
    Returns formatted string for LLM context
    """
    # Query: SELECT * FROM snapshots WHERE timestamp > NOW() - days
    # Group by service
    # Calculate: min/max/avg CPU%, min/max/avg Memory MB, failure_rate
    # Format into human-readable summary
```

**Example Output:**
```
Historical Trends (30 days):
- docker: CPU avg 0.0% (min 0.0%, max 0.5%), Memory 101.3 MB (0.1%)
- nordvpnd: CPU avg 0.2% (min 0.1%, max 0.4%), Memory 119.0 MB (0.1%)
- tailscaled: CPU avg 0.1% (min 0.0%, max 0.2%), Memory 45.2 MB (0.05%)
- system_backup: Failed 2 times in 30 days (last failure 2 days ago)
- alpha: Failed 5 times in 30 days (100% failure rate, currently down)
```

### Retention Policy

- **Default:** Keep 30 days of snapshots
- **Deletion:** Run after each ingest (DELETE WHERE timestamp < NOW() - 30 days)
- **Database Size:** ~20-25MB for 30 days × ~30 services × 12 checks/day = ~10K snapshots

---

## System Context Injection

The Mother chat system automatically detects and injects OS context into LLM prompts:

### OS Detection

```python
def detect_system_info():
    """Detect OS, distro, package manager"""
    return {
        "os": "Linux",
        "distro": "Ubuntu",
        "distro_version": "24.04",
        "package_manager": "apt",  # not dnf, zypper, pacman
        "hostname": "beta-boy",
        "kernel_version": "6.8.0",
        "python_version": "3.11"
    }
```

### Injected Prompt

```
You are MU/TH/UR, an expert system administrator.

SYSTEM INFORMATION:
- OS: Linux (Ubuntu 24.04 - Noble Numbat)
- Package Manager: apt (not dnf, zypper, or pacman)
- Hostname: beta-boy
- Python: 3.11

GUIDELINES:
1. All package installs use: sudo apt install <package>
2. All service management uses: systemctl {start|stop|restart|status}
3. All service logs use: journalctl -u <service>.service
4. Reference actual data from service histories
5. Provide OS-specific commands only
6. Be concise and actionable
```

**Result:** LLM naturally provides correct commands without manual hints

---

## Per-Service Log Configuration

The log registry (`tools/log_reader.py`) tells LogReader where to find logs for each service:

### Registry Structure

```python
log_registry = {
    "system_backup": {
        "strategy": "newest_file",
        "pattern": "/data/tank/backups/sys_restore/backup_log_*.log",
        "max_lines": 150  # Verbose backups need more context
    },
    "nordvpn_reconnect": {
        "strategy": "tail_file",
        "path": "/var/log/nordvpn-reconnect.log",
        "max_lines": 75
    },
    "nordvpn_status": {
        "strategy": "journalctl",
        "unit": "nordvpnd.service",
        "max_lines": 50  # Terse service logs
    },
    "docker": {
        "strategy": "journalctl",
        "unit": "docker.service",
        "max_lines": 100
    }
}
```

### Strategies

| Strategy | Use Case | Example |
|----------|----------|---------|
| `tail_file` | Single log file | `/var/log/monit.log` - read last 50 lines |
| `newest_file` | Multiple files with date pattern | `/logs/backup_*.log` - find newest, read last 150 lines |
| `journalctl` | Systemd service logs | `docker.service` - query systemd journal, last 100 lines |

### Max Lines Logic

Per-service limits prevent VRAM overflow and keep inference fast:

- **Verbose logs** (backup, network): 100-150 lines
- **Medium logs** (service status): 50-75 lines
- **Terse logs** (application events): 30-50 lines

Total context = number of failed services × average max_lines = usually <1000 lines

---

## Database Schema

### snapshots (30-day rolling window)

```sql
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    service_name TEXT NOT NULL,
    status INTEGER NOT NULL,      -- 0=OK, 1=failed, 2=disabled
    raw_json TEXT NOT NULL,       -- Full Monit service data as JSON
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(service_name) REFERENCES failure_history(service_name)
);

-- Indices for fast queries
CREATE INDEX idx_snapshots_service_timestamp ON snapshots(service_name, timestamp DESC);
CREATE INDEX idx_snapshots_status ON snapshots(status);
```

**Query Example:**
```sql
-- Get all services that failed in last 30 days
SELECT DISTINCT service_name 
FROM snapshots 
WHERE status != 0 AND timestamp > datetime('now', '-30 days');

-- Get CPU trends for one service
SELECT 
    MIN(CAST(json_extract(raw_json, '$.cpu.percent') AS REAL)) as min_cpu,
    AVG(CAST(json_extract(raw_json, '$.cpu.percent') AS REAL)) as avg_cpu,
    MAX(CAST(json_extract(raw_json, '$.cpu.percent') AS REAL)) as max_cpu
FROM snapshots 
WHERE service_name = 'docker' AND timestamp > datetime('now', '-30 days');
```

### failure_history (state tracking)

```sql
CREATE TABLE failure_history (
    service_name TEXT PRIMARY KEY,
    last_status INTEGER NOT NULL,
    last_checked DATETIME NOT NULL,
    times_failed INTEGER DEFAULT 0,
    first_failure_time DATETIME,
    last_failure_time DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Logic:**
- NEW FAILURE: status changes from 0→1 → set `is_critical=True`
- ONGOING: status stays 1→1 → set `is_critical=False` (skip LLM re-analysis)
- CHANGED: status changes (any way) → set `is_critical=True`
- RECOVERED: status changes from 1→0 → set `is_critical=False`

### conversations (chat history)

```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_message TEXT NOT NULL,
    agent_response TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    response_time_ms INTEGER,
    tokens_used INTEGER
);
```

### action_audit_log (executed commands)

```sql
CREATE TABLE action_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    service TEXT,
    command TEXT NOT NULL,
    executed_by TEXT,
    approved_by TEXT,
    exit_code INTEGER,
    output TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### chat_credentials (authentication)

```sql
CREATE TABLE chat_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,      -- PBKDF2-SHA256 hex
    salt TEXT NOT NULL,                -- Random hex salt
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## WebSocket Protocol

### Message Types

The `/ws/chat` endpoint uses JSON message protocol:

#### User → Agent

```json
{
  "type": "message",
  "content": "Why is docker failing?"
}
```

#### Agent → User (Thinking)

```json
{
  "type": "thinking",
  "message": "Processing your query..."
}
```

#### Agent → User (Response)

```json
{
  "type": "response",
  "content": "Based on the system history and current status...",
  "timestamp": "2026-01-03T12:00:00",
  "tokens_generated": 256
}
```

#### Action Suggestion

```json
{
  "type": "action_suggestion",
  "action": "systemctl_restart",
  "service": "docker",
  "command": "systemctl restart docker",
  "description": "Restart the docker service to resolve connection issues",
  "approval_required": true
}
```

#### Action Result

```json
{
  "type": "action_result",
  "success": true,
  "exit_code": 0,
  "output": "Service restarted successfully",
  "timestamp": "2026-01-03T12:00:05"
}
```

#### Authentication (First Message)

```json
{
  "type": "message",
  "content": "initial_auth",
  "username": "admin",
  "password_hash": "<hash>"
}
```

### Connection Lifecycle

1. **Browser connects** to `ws://localhost:8000/ws/chat`
2. **First message** contains authentication (username, password)
3. **Server validates** against chat_credentials table
4. **Connection established** - normal message flow begins
5. **Timeout** - if no activity for 30 min, connection closes and user logs out
6. **Activity resets** timeout (user doesn't need to re-login while active)

---

## Performance Characteristics

### LLM Inference Time

- **Background Agent:** 2-5 seconds per failure (depends on log size)
- **Mother Chat:** 3-8 seconds per query (depends on context size)
- **GPU:** RTX 4000 (8GB VRAM) handles ~1000 token context window comfortably

### Database Operations

- **Ingest write:** ~100ms (30 services → 30 INSERT + 30 UPDATE + 1 DELETE)
- **Historical query:** ~50ms (SELECT 10K snapshots and calculate trends)
- **Snapshot storage:** ~20-25MB for 30 days of data

### Memory Usage

- **Agent process:** ~200-300MB base + 2-4GB GPU VRAM for Llama model
- **Database:** ~25MB on disk (SQLite)
- **Browser:** ~50MB for chat UI with 30-min message history

---

## Failure Detection Logic

### is_critical Flag Decision Tree

```
Check failure_history for service:
├─ Does service exist?
│  ├─ No: NEW FAILURE
│  │     Set is_critical = True
│  │     Save to failure_history
│  │     ACTION: ANALYZE
│  │
│  └─ Yes: Check status change
│     ├─ Old status: 0 (healthy), New status: non-0 (failed)
│     │  NEW/CHANGED FAILURE
│     │  Set is_critical = True
│     │  ACTION: ANALYZE
│     │
│     ├─ Old status: non-0, New status: 0 (recovered)
│     │  RECOVERED
│     │  Set is_critical = False
│     │  ACTION: DONE (mark healthy in history)
│     │
│     ├─ Old status: non-0, New status: non-0 (still failing)
│     │  ONGOING FAILURE
│     │  Set is_critical = False
│     │  ACTION: SKIP (save GPU, don't re-analyze)
│     │
│     └─ Old status: non-0, New status: different non-0
│        STATUS CHANGED
│        Set is_critical = True
│        ACTION: ANALYZE
```

### Why Skip Ongoing Failures?

- **Scenario:** Docker fails at 20:00, we analyze it. At 20:05, still failing, still same error.
- **Without skip:** Re-analyze same failure every 5 min = waste GPU compute
- **With skip:** Mark as ONGOING, skip LLM analysis, save 3-5 seconds and GPU VRAM
- **Result:** More responsive for NEW failures, faster overall system

---

## Configuration & Customization

See [README.md → Configuration](README.md#-configuration) for:
- Adjusting log registry
- Customizing LLM prompts
- Changing monitoring intervals
- Modifying session timeouts
- Adjusting database retention

---

## Security Architecture

For detailed security information including password hashing, API auth, and threat model, see [SECURITY.md](SECURITY.md).

**Quick Summary:**
- ✅ Chat passwords hashed with PBKDF2-SHA256 (100,000 iterations)
- ✅ HTTP Basic Auth on all REST endpoints
- ✅ WebSocket requires auth before first message
- ✅ 30-min session timeout with activity reset
- ✅ All actions logged to audit_audit_log
- ✅ Read-only by default (no destructive operations without approval)

