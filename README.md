# 🤖 Monit-Intel Agent

A **LangGraph + Llama 3.1** powered agent that monitors server health via Monit, analyzes logs intelligently, and performs automated root-cause analysis. Features an interactive MU/TH/UR chat interface for querying system health and executing safe remediation actions.

**Quick links:**
- 📖 [Install & Setup](#-install--setup)
- 🚀 [Quick Start](#-quick-start)
- 💬 [Usage](#-usage)
- 🏗️ [Architecture](#-architecture)
- ⚙️ [Configuration](#-configuration)
- 🐛 [Troubleshooting](#-troubleshooting)

---

## 📖 Install & Setup

### Prerequisites

- **Pixi** (lightweight Conda alternative) - [Install here](https://pixi.sh)
- **Monit** running on `localhost:2812` with XML API enabled
- **Ollama** running Llama 3.1:8b on GPU (RTX 4000 or similar)
- **Linux system** (tested on Ubuntu 24.04)

### Step 1: Clone & Install Dependencies

```bash
cd /home/heverz/py_projects/monit-intel
pixi install
```

### Step 2: Configure Credentials

**Option A: Development (Local .env - Easy)**
```bash
cat > .env << EOF
MONIT_USER=admin
MONIT_PASS=monit
MONIT_URL=http://localhost:2812/_status?format=xml
EOF
```

**Option B: Production (Systemd - Secure & Recommended)**

Credentials stored securely in systemd drop-in files (not in git, not in project folder):

```bash
# Create environment files
sudo mkdir -p /etc/systemd/system/monit-intel-{agent,ingest}.service.d/

# Agent environment
sudo tee /etc/systemd/system/monit-intel-agent.service.d/env.conf > /dev/null << EOF
[Service]
Environment="MONIT_USER=admin"
Environment="MONIT_PASS=your_monit_password"
Environment="MONIT_URL=http://localhost:2812/_status?format=xml"
EOF

# Ingest environment
sudo tee /etc/systemd/system/monit-intel-ingest.service.d/env.conf > /dev/null << EOF
[Service]
Environment="MONIT_USER=admin"
Environment="MONIT_PASS=your_monit_password"
Environment="MONIT_URL=http://localhost:2812/_status?format=xml"
EOF

# Lock down permissions
sudo chmod 600 /etc/systemd/system/monit-intel-*/service.d/env.conf

# Reload systemd
sudo systemctl daemon-reload
```

**Benefits of Option B:**
- ✅ Credentials NOT in git repo
- ✅ Credentials NOT in project folder
- ✅ Only readable by root (chmod 600)
- ✅ Easy rotation without code redeploy

### Step 3: Set Up Chat Credentials

Chat authentication is **separate from Monit credentials**. Initialize the chat UI login credentials:

```bash
cd /home/heverz/py_projects/monit-intel

# Set your chat UI username and password
pixi run python -m monit_intel.chat_auth your_username your_secure_password

# Example:
pixi run python -m monit_intel.chat_auth admin MySecurePassword123

# Check status
pixi run python << 'EOF'
from monit_intel.chat_auth import get_chat_credentials_status
status = get_chat_credentials_status()
print(f"Chat credentials configured: {status['configured']}")
print(f"Credentials count: {status['count']}")
EOF
```

**Note:** You can have different passwords for:
- **Monit API** (in systemd env files or .env)
- **Chat UI** (stored securely in SQLite with password hashing)

### Step 4: Verify Setup

```bash
# Test Monit connection (using Monit credentials from systemd env)
curl -u $(echo $MONIT_USER:$MONIT_PASS) http://localhost:2812/_status?format=xml | head -20

# Test Ollama (should return model info)
curl http://localhost:11434/api/tags | jq .

# Test database (should show >0 snapshots)
pixi run python << 'EOF'
import sqlite3
conn = sqlite3.connect("monit_history.db")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM snapshots")
print(f"✓ Database ready: {cursor.fetchone()[0]} snapshots")
cursor.execute("SELECT COUNT(*) FROM chat_credentials")
print(f"✓ Chat credentials: {cursor.fetchone()[0]} user(s) configured")
conn.close()
EOF
```

---

## 🚀 Quick Start

### Start the Services (Development)

**Terminal 1: Start the agent with API**
```bash
cd /home/heverz/py_projects/monit-intel

# Use your Monit credentials from systemd env or .env
MONIT_USER=admin MONIT_PASS=your_monit_password pixi run agent
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

**Terminal 2: Start the ingestion (optional - runs automatically every 5 min in production)**
```bash
cd /home/heverz/py_projects/monit-intel
pixi run ingest
```

### Access the Chat UI

Open your browser:
```
http://localhost:8000/chat
```

Login with the **chat credentials** you set up in Step 3:
- **Username:** Your chosen username
- **Password:** Your chosen password

**Note:** These are **different from your Monit service password**. If you set them up as:
```bash
pixi run python -m monit_intel.chat_auth admin your_secure_password
```

Then login with:
- Username: `admin`
- Password: `your_secure_password`

### Start the Services (Production with Systemd)

```bash
# Install systemd services (one-time setup)
sudo bash /home/heverz/py_projects/monit-intel/config/systemd/install-services.sh

# Start agent
sudo systemctl start monit-intel-agent.service
sudo systemctl status monit-intel-agent.service

# Start ingest timer
sudo systemctl start monit-intel-ingest.timer
systemctl list-timers monit-intel-ingest.timer

# View logs
journalctl -u monit-intel-agent.service -f
```

---

## 💬 Usage

### 1. Web Chat UI (Interactive & Easiest)

**Start the agent first:**
```bash
MONIT_USER=admin MONIT_PASS=your_monit_password pixi run agent
```

**Open in browser:**
```
http://localhost:8000/chat
```

**Login with your chat credentials** (the ones you configured in setup step 3):
- Username: your_username
- Password: your_password

**Features:**
- Real-time bidirectional WebSocket chat
- Login with your configured chat credentials
- 30-minute session timeout with auto-logout
- Logout button in top-right corner
- Alien aesthetic (phosphor green, scanlines)
- Historical trend analysis (CPU, memory, failures)

**Example queries:**
```
You:  "What's the overall system health?"
Bot:  "All services are healthy. Docker at 0.5% CPU, nordvpn at 0.2%..."

You:  "Why is system_backup failing?"
Bot:  "Analyzing logs... The backup process timed out due to disk space..."

You:  "What about CPU usage in the last 30 days?"
Bot:  "CPU trends are stable. Nordvpn averages 0.2%, docker 0.0%..."

You:  "Restart docker"
Bot:  "I can help with that. Execute: systemctl restart docker (y/n)?"
```

### 2. Interactive CLI Chat

**Start the interactive CLI:**
```bash
cd /home/heverz/py_projects/monit-intel
pixi run hello-mother
```

**Usage:**
```bash
> What is the current system status?
Agent: All services are currently healthy...

> Why is nordvpn_reconnect failing?
Agent: The service appears to have connection issues...

> Show me the failure history
Agent: Based on the past 30 days...

> exit
Goodbye!
```

**This CLI:**
- Connects directly to the agent
- Maintains conversation history
- Auto-detects OS for OS-specific commands
- Supports multi-line queries
- No browser needed

### 3. REST API (Programmatic)

**Test the API (use your configured chat credentials):**
```bash
# Check agent health
curl -u your_username:your_password http://localhost:8000/health
# → {"status": "healthy", "database": "connected", "snapshots": 150}

# Get all service statuses
curl -u your_username:your_password http://localhost:8000/status | jq
# → [{"service": "docker", "status": 0}, ...]

# Query via REST endpoint
curl -X POST http://localhost:8000/mother/chat \
  -u your_username:your_password \
  -H "Content-Type: application/json" \
  -d '{"query": "What about CPU usage?"}'
# → {"response": "CPU usage is stable...", "timestamp": "..."}

# View conversation history
curl -u your_username:your_password "http://localhost:8000/mother/history?limit=10" | jq
```

**Available Endpoints:**
| Method | Endpoint | Purpose | Auth |
|--------|----------|---------|------|
| `GET` | `/health` | Agent status | Basic |
| `GET` | `/status` | All services | Basic |
| `POST` | `/mother/chat` | Chat query | Basic |
| `GET` | `/mother/history` | Chat history | Basic |
| `POST` | `/mother/actions/suggest` | Preview action | Basic |
| `POST` | `/mother/actions/execute` | Execute action | Basic |
| `GET` | `/mother/actions/audit` | Action audit log | Basic |

### 4. Manual Background Monitoring

**One-time ingestion run:**
```bash
pixi run ingest
```

**Continuous daemon (polls every 5 min):**
```bash
MONIT_USER=admin MONIT_PASS=your_monit_password pixi run agent &
```

**View console output:**
```bash
# Logs appear as:
[2026-01-03 20:53:38] detect_failures: Found 1 NEW failure
[2026-01-03 20:53:40] fetch_logs: Retrieving logs for system_backup
[2026-01-03 20:53:45] analyze_with_llm: Llama 3.1 analysis complete
  → Root cause: Disk space exhausted (/data/tank at 98%)
  → Recommendation: Expand storage or delete old backups
```

### Restart the Agent

**Development:**
```bash
# Kill old process
pkill -f "pixi run agent"

# Start new one
MONIT_USER=admin MONIT_PASS=your_monit_password pixi run agent
```

**Production (Systemd):**
```bash
sudo systemctl restart monit-intel-agent.service
sudo systemctl status monit-intel-agent.service
```

### Stop the Agent

**Development:**
```bash
pkill -f "pixi run agent"
```

**Production:**
```bash
sudo systemctl stop monit-intel-agent.service
sudo systemctl disable monit-intel-agent.service  # Don't auto-start
```

---

## 🏗️ Architecture

**Service Health Query (REST API):**
```bash
curl -X POST http://localhost:8000/mother/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Are there any service failures right now?"}'

# Response:
# {
#   "query": "Are there any service failures right now?",
#   "response": "No, all services are currently healthy. There are no service failures reported at this time...",
#   "timestamp": "2026-01-03T13:32:13.347162"
# }
```

**Historical Trend Query (30-day analysis with CPU/Memory metrics):**
```bash
curl -X POST http://localhost:8000/mother/chat \
  -u your_username:your_password \
  -H "Content-Type: application/json" \
  -d '{"query": "What about CPU usage in the last 30 days?"}'

# Response:
# {
#   "query": "What about CPU usage in the last 30 days?",
#   "response": "Based on the historical trend data, here are CPU usage observations:
#   - docker: avg 0.0%, min 0.0%, max 0.0%
#   - nordvpnd: avg 0.2%, min 0.2%, max 0.2%
#   - tailscaled: avg 0.1%, min 0.0%, max 0.1%
#   - Memory usage: docker 101.3 MB (0.1%), nordvpnd 119.0 MB (0.1%)
#   All services show minimal CPU/Memory consumption with stable trends.",
#   "timestamp": "2026-01-03T13:45:22.123456"
# }
```

**Via Web UI (WebSocket):**
```
User: "Why is docker unhealthy?"
Mother: "Based on the current system context, there are no immediate concerns about Docker's health. 
However, I'd like to highlight a few potential future issues: [Outdated Docker version], 
[Insufficient disk space], [Resource constraints]..."

User: "What should I monitor for sshd?"
Mother: "For SSH security and stability, monitor: Failed login attempts, Connection rate limits, 
Resource usage, Configuration changes, Certificate/key validity..."

User: "Did we have failures recently?"
Mother: "Yes. Based on the 30-day historical data, the alpha service has failed 5 times (100% failure rate). 
All other services remain healthy. I recommend investigating the root cause..."

User: "What's the overall system health?"
Mother: "All services are currently healthy: docker ✓, sshd ✓, zfs-zed ✓. 
The system shows no critical issues at this moment. Continue routine monitoring..."
```

### WebSocket Message Format

The chat UI communicates with the agent via WebSocket at `/ws/chat`. Message types:

**User Messages:**
```json
{
  "type": "message",
  "content": "user query here"
}

{
  "type": "action",
  "action": "restart",
  "service": "docker"
}

{
  "type": "action_confirm",
  "action": "restart",
  "service": "docker"
}
```

**Agent Responses:**
```json
{
  "type": "thinking",
  "message": "Processing your query..."
}

{
  "type": "response",
  "content": "analysis or answer",
  "timestamp": "2026-01-03T12:00:00"
}

{
  "type": "action_suggestion",
  "action": "restart",
  "service": "docker",
  "command": "systemctl restart docker",
  "description": "Restart the docker service"
}

{
  "type": "action_result",
  "success": true,
  "exit_code": 0,
  "output": "command output here",
  "timestamp": "2026-01-03T12:00:00"
}
```

## 🏗️ Architecture

### Components Overview

| Module | Purpose |
|--------|---------|
| `src/monit_intel/ingest.py` | Polls Monit XML API every 5 min, stores snapshots, cleans old data |
| `src/monit_intel/main.py` | Daemon runner - checks for failures every 5 min |
| `src/monit_intel/hello_mother.py` | Interactive CLI chat interface |
| `src/monit_intel/agent/api.py` | FastAPI REST + WebSocket server |
| `src/monit_intel/agent/graph.py` | LangGraph workflow definition (DAG compilation) |
| `src/monit_intel/agent/state.py` | LangGraph state definition |
| `src/monit_intel/agent/nodes.py` | Individual workflow nodes (database, log fetching, LLM) |
| `src/monit_intel/agent/mother.py` | Interactive chat manager with context injection |
| `src/monit_intel/agent/actions.py` | Safe command executor with whitelist and audit logging |
| `src/monit_intel/agent/static/chat.html` | Web chat UI (HTML/CSS/JavaScript) |
| `src/monit_intel/tools/log_reader.py` | Hybrid log reader (files, journalctl, glob patterns) |

### How It Works: Two Parallel Systems

The system has **two distinct workflows** running simultaneously:

#### **System 1: Background Agent (LangGraph Daemon)**

Runs automatically every 5 minutes in the background, detecting and analyzing failures.

```
START
  ↓
detect_failures() [Node 1]
  ├─ Query SQLite snapshots for failures (status != 0)
  ├─ Check failure_history: Is this NEW or CHANGED?
  ├─ Set is_critical=True only for NEW/CHANGED failures
  └─ Skip unchanged failures (save GPU compute)
  ↓
fetch_logs_and_context() [Node 2]
  ├─ Extract failed service names
  ├─ Use LogReader to fetch logs from:
  │  ├─ Log files (tail strategy: /var/log/service.log)
  │  ├─ Glob patterns (newest_file: /path/logs_*.log)
  │  └─ Journalctl (journalctl -u service.service)
  ├─ Apply per-service max_lines limits (50-150 lines)
  └─ Append logs to context
  ↓
analyze_with_llm() [Node 3]
  ├─ Check: is_critical == True?
  ├─ If False: Skip LLM (unchanged failure)
  ├─ If True: Send to Llama 3.1 with context
  ├─ Llama analyzes logs + service status
  └─ Return root cause analysis
  ↓
END (sleep 5 min, repeat)
```

**Smart Logic: is_critical Flag**
- **NEW Failure:** Service was healthy, now failed → `is_critical=True` → **Analyze**
- **ONGOING:** Service still failing, same status → `is_critical=False` → **Skip** (don't re-analyze)
- **CHANGED:** Service status changed → `is_critical=True` → **Analyze**
- **RECOVERED:** Service back to healthy → `is_critical=False` → **Done**

This saves significant GPU compute by not re-analyzing the same failure repeatedly.

#### **System 2: Interactive Chat (Mother / MU/TH/UR)**

A user-facing chat interface that queries the LLM on-demand when you ask questions.

```
User Types Message in Browser
  ↓
WebSocket → FastAPI /ws/chat endpoint
  ↓
Mother.query_agent() [agent/mother.py]
  ├─ Extract mentioned services from user query
  ├─ Gather context:
  │  ├─ Current service statuses
  │  ├─ Historical trends (30-day data with CPU/memory metrics)
  │  ├─ Recent logs for relevant services
  │  └─ System info (OS, package manager, hostname)
  ├─ Detect system: Ubuntu? Fedora? macOS?
  └─ Inject context into LLM prompt
  ↓
Llama 3.1 Processes Query + Context
  ├─ Understands OS-specific commands
  ├─ Answers with service history
  └─ Provides actionable recommendations
  ↓
Response Streamed Back via WebSocket
  ↓
Browser Displays in Chat UI
```

**Key Differences:**

| Aspect | Background Agent | Mother Chat |
|--------|---|---|
| **Trigger** | Runs every 5 min automatically | User sends message |
| **Purpose** | Detect failures proactively | Answer user questions |
| **Process** | Multi-node workflow (Graph) | Single LLM call |
| **Output** | Console logs | Conversational response |
| **Context** | Current failure data | Historical + current data |

### Historical Data: 30-Day Snapshots

Every 5 minutes, `ingest.py` stores a complete service snapshot in SQLite:

```json
{
  "timestamp": "2026-01-03T20:53:38",
  "service_name": "docker",
  "status": 0,  // 0=healthy, other=failed
  "raw_json": {
    "cpu": { "percent": "0.5", "percenttotal": "0.5" },
    "memory": { "percent": "0.1", "kilobyte": "103752" },
    "uptime": "517935",
    "threads": "33",
    ...full Monit data...
  }
}
```

The `get_historical_trends()` function extracts this data:
- **CPU metrics:** Min/max/average over 30 days per service
- **Memory usage:** Current and historical percentages
- **Failure rates:** How often did this service fail?
- **Status trends:** Service health over time

When you ask "What about CPU usage?", the Mother chat:
1. Queries the snapshots table for 30 days of data
2. Extracts CPU percentages for each service
3. Calculates trends (nordvpnd avg 0.2%, docker avg 0.0%, etc.)
4. Passes to LLM with actual numbers
5. Returns analysis: "CPU usage is stable. Nordvpnd is the top consumer..."

### System Context Injection

When you chat with Mother, the system automatically:

1. **Detects your OS:**
   ```python
   if "Ubuntu" in lsb_release:
       package_manager = "apt"
   elif "Fedora" in lsb_release:
       package_manager = "dnf"
   # etc.
   ```

2. **Injects into LLM prompt:**
   ```
   "You are MU/TH/UR running on Ubuntu 24.04 (beta-boy)
    Package manager: apt (not dnf, zypper, or pacman)
    When suggesting package installs, use: sudo apt install <package>
    For service management, use: systemctl ...
    Current hostname: beta-boy"
   ```

3. **Result:** LLM gives OS-specific advice automatically
   - Ask on Ubuntu → get `apt` commands
   - Ask on Fedora → get `dnf` commands
   - No manual context needed!

### Per-Service Log Configuration

The log registry tells LogReader where to find logs:

```python
log_registry = {
    "system_backup": {
        "strategy": "newest_file",           # Pick latest file matching pattern
        "pattern": "/data/tank/backups/sys_restore/backup_log_*.log",
        "max_lines": 150                     # Verbose backup logs
    },
    "nordvpn_reconnect": {
        "strategy": "tail_file",             # Tail single log file
        "path": "/var/log/nordvpn-reconnect.log",
        "max_lines": 75
    },
    "nordvpn_status": {
        "strategy": "journalctl",            # Query systemd journal
        "unit": "nordvpnd.service",
        "max_lines": 50                      # Terse service logs
    }
}
```

**Why per-service limits?**
- Backup logs are verbose (need 150 lines to see full context)
- Service status is terse (50 lines usually sufficient)
- Prevents VRAM overflow on GPU with long contexts
- Keeps LLM inference fast (2-5 seconds per analysis)

### Data Flow Diagram

```
Monit XML API (every 5 min)
     ↓
[ingest.py] 
     ├→ INSERT snapshots with full raw_json
     ├→ UPDATE failure_history (track NEW/ONGOING/CHANGED)
     └→ DELETE snapshots >30 days old
     ↓
[SQLite: snapshots + failure_history + conversations]
     ├─ 30 days × ~30 services × 12 checks/day = ~10K snapshots
     └─ Size: ~20-25MB
     ↓
     ├─ BRANCH 1: Background Agent (every 5 min)
     │  ├→ detect_failures: Query snapshots, check failure_history
     │  ├→ is_critical? If No → Skip. If Yes → Continue.
     │  ├→ fetch_logs_and_context: Use LogReader + registry
     │  └→ analyze_with_llm: Send to Llama 3.1 (GPU inference)
     │     └→ Console output: Root cause analysis
     │
     └─ BRANCH 2: Interactive Chat (on user message)
        ├→ Mother receives query via WebSocket
        ├→ get_historical_trends(): Extract CPU/memory/failure data
        ├→ detect OS, inject system context
        ├→ Send to Llama 3.1 with enriched context
        └→ Stream response back to browser
```

### Full System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                    MONIT-INTEL AGENT SYSTEM                          │
└──────────────────────────────────────────────────────────────────────┘

╔════════════════════════════════════════════════════════════════════╗
║                        BACKEND (Server)                            ║
║                                                                    ║
║  ┌──────────────────┐                                             ║
║  │  Monit Server    │  Runs on localhost:2812                     ║
║  │  (beta-boy)      │  Monitors 30+ services                      ║
║  │  Port 2812       │  Exposes XML status API                     ║
║  └────────┬─────────┘                                             ║
║           │ GET /_status?format=xml                               ║
║           ▼                                                        ║
║  ┌──────────────────────────────────────────┐                    ║
║  │   ingest.py (Scheduler via systemd)      │                    ║
║  │   - Runs every 5 minutes                 │                    ║
║  │   - Polls Monit XML                      │                    ║
║  │   - Parses service status + metrics      │                    ║
║  │   - Stores complete snapshot raw_json    │                    ║
║  └────────────┬─────────────────────────────┘                    ║
║               │ INSERT snapshots, UPDATE failure_history          ║
║               ▼                                                    ║
║  ┌──────────────────────────────────────────┐                    ║
║  │   SQLite: monit_history.db               │                    ║
║  │   - snapshots (30-day rolling)           │                    ║
║  │   - failure_history (state tracking)     │                    ║
║  │   - conversations (chat history)         │                    ║
║  │   - action_audit_log (executed commands) │                    ║
║  └────────────┬────────────────────────────┘                     ║
║               │                                                    ║
║     ┌─────────┴────────────┐                                      ║
║     │                      │                                      ║
║     ▼ (every 5 min)        ▼ (on user message)                   ║
║                                                                    ║
║  ┌────────────────────┐  ┌──────────────────────┐                ║
║  │  BACKGROUND AGENT  │  │   MOTHER (Chat)      │                ║
║  │  (main.py daemon)  │  │   (agent/mother.py)  │                ║
║  └────────────────────┘  └──────────────────────┘                ║
║           │                        │                              ║
║           ▼                        ▼                              ║
║  ┌──────────────────────────────────────────────────┐             ║
║  │   LangGraph Workflow (agent/graph.py)            │             ║
║  │                                                  │             ║
║  │   [1] detect_failures()                          │             ║
║  │       └─ Query: status != 0                      │             ║
║  │       └─ Check: NEW or CHANGED?                  │             ║
║  │       └─ Set is_critical flag                    │             ║
║  │           ▼                                      │             ║
║  │   [2] fetch_logs_and_context()                   │             ║
║  │       └─ Use LogReader + registry               │             ║
║  │       └─ tail_file: /var/log/service.log        │             ║
║  │       └─ newest_file: glob patterns             │             ║
║  │       └─ journalctl: systemd units              │             ║
║  │       └─ Apply max_lines per service            │             ║
║  │           ▼                                      │             ║
║  │   [3] analyze_with_llm()                         │             ║
║  │       └─ if NOT is_critical: SKIP               │             ║
║  │       └─ if is_critical:                         │             ║
║  │           ├─ Send logs + context to Llama 3.1   │             ║
║  │           └─ Return root cause analysis         │             ║
║  └──────────────────────────────────────────────────┘             ║
║           │                        │                              ║
║           ▼                        ▼                              ║
║  Console output              Stream response                      ║
║  (root cause analysis)       via WebSocket                        ║
║                                                                    ║
║  ┌──────────────────────────────────────────────────┐             ║
║  │   System Context Injection                       │             ║
║  │   - Detect OS (Ubuntu, Fedora, Arch, etc.)     │             ║
║  │   - Find package manager (apt, dnf, zypper)   │             ║
║  │   - Get hostname, distro version               │             ║
║  │   - Build system-aware LLM prompt              │             ║
║  └──────────────────────────────────────────────────┘             ║
║           │                                                       ║
║           ▼                                                       ║
║  ┌──────────────────────────────────────────────────┐             ║
║  │   Ollama (GPU - RTX 4000)                        │             ║
║  │   Llama 3.1:8b                                   │             ║
║  │   - Inference time: 2-5 seconds                 │             ║
║  │   - Understands OS-specific context             │             ║
║  │   - Returns intelligent analysis                │             ║
║  └──────────────────────────────────────────────────┘             ║
║           │                                                       ║
║           ▼                                                       ║
║  ┌──────────────────────────────────────────────────┐             ║
║  │   FastAPI Server (agent/api.py)                 │             ║
║  │   - Port 8000                                    │             ║
║  │   - HTTP Basic Auth (Monit credentials)         │             ║
║  │   - WebSocket: /ws/chat                         │             ║
║  │   - REST endpoints: /health, /status, etc.     │             ║
║  │   - Message-based WebSocket auth               │             ║
║  └──────────────────────────────────────────────────┘             ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝

╔════════════════════════════════════════════════════════════════════╗
║                      FRONTEND (Browser)                            ║
║                                                                    ║
║  ┌──────────────────────────────────────────────────┐             ║
║  │   MU/TH/UR Chat UI (http://localhost:8000/chat)│             ║
║  │                                                  │             ║
║  │   [Login Overlay]                                │             ║
║  │   ├─ Username: admin                             │             ║
║  │   └─ Password: monit                             │             ║
║  │       │ (localStorage cached for 30 min)        │             ║
║  │       ▼                                          │             ║
║  │   [Main Chat Interface]                          │             ║
║  │   ├─ Alien aesthetic (phosphor green)           │             ║
║  │   ├─ CRT scanlines effect                       │             ║
║  │   ├─ Message history display                    │             ║
║  │   ├─ Input field for user queries               │             ║
║  │   └─ LOGOUT button (top-right)                  │             ║
║  │       └─ 30-min timeout triggers auto-logout    │             ║
║  │       └─ Activity resets timeout                │             ║
║  │                                                  │             ║
║  │   [WebSocket Connection]                         │             ║
║  │   ├─ Initial: First message contains auth       │             ║
║  │   ├─ Ongoing: "type": "message", "content": ... │             ║
║  │   └─ Auto-reconnect on disconnect               │             ║
║  └──────────────────────────────────────────────────┘             ║
║                                                                    ║
║  User Query Flow:                                                  ║
║  ┌─ User: "What about CPU usage?"                  ║             ║
║  │  ▼                                               ║             ║
║  │  Browser sends JSON via WebSocket               ║             ║
║  │  ▼                                               ║             ║
║  │  Mother class receives query                    ║             ║
║  │  ▼                                               ║             ║
║  │  get_historical_trends() fetches 30 days data  ║             ║
║  │  ├─ CPU metrics: min/avg/max per service       ║             ║
║  │  ├─ Memory usage: docker 101MB, nordvpn 119MB  ║             ║
║  │  └─ Status: "docker HEALTHY", "alpha FAILED"   ║             ║
║  │  ▼                                               ║             ║
║  │  LLM gets enriched prompt with actual data     ║             ║
║  │  ▼                                               ║             ║
║  │  Llama 3.1: "CPU is stable. nordvpnd at 0.2%"│             ║
║  │  ▼                                               ║             ║
║  │  Response streams via WebSocket                 ║             ║
║  │  ▼                                               ║             ║
║  │  Browser displays: "CPU usage analysis..."     ║             ║
║  └─ Done                                            ║             ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
```
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

---

## ⚙️ Configuration

### Customize Service Log Registry

Edit `src/monit_intel/tools/log_reader.py` to add or modify how logs are fetched:

```python
log_registry = {
    "my_new_service": {
        "strategy": "tail_file",              # Options: tail_file, newest_file, journalctl
        "path": "/var/log/my_service.log",   # For tail_file
        "pattern": "/var/log/my_service_*.log",  # For newest_file (glob)
        "unit": "my-service.service",         # For journalctl
        "max_lines": 100                      # Context window size
    }
}
```

**Strategies:**
- `tail_file`: Read last N lines from a single file
- `newest_file`: Find newest file matching glob pattern, then tail
- `journalctl`: Query systemd journal for a specific unit

### Customize LLM System Prompt

Edit `src/monit_intel/agent/mother.py` in the `query_agent()` method:

```python
system_prompt = f"""You are MU/TH/UR, an expert system administrator.
You are running on {self.system_info['distro']} ({self.system_info['os']}).
Package manager: {self.system_info['package_manager']}
Hostname: {self.system_info['hostname']}

GUIDELINES:
- Provide OS-specific commands only
- Analyze failures with real data
- Never suggest destructive operations without explicit approval
- Include relevant logs in analysis
- Be concise and actionable
"""
```

### Adjust Monitoring Intervals

Edit `src/monit_intel/main.py`:

```python
# Change from 5 minutes to custom interval (in seconds)
MONITOR_INTERVAL = 300  # 5 minutes
```

Edit systemd timer for ingest (production):
```bash
sudo systemctl edit monit-intel-ingest.timer
# Modify: OnBootSec=5min, OnUnitActiveSec=5min
```

### Session Timeout Configuration

Edit `src/monit_intel/agent/static/chat.html`:

```javascript
// Current: 30 minutes
const SESSION_TIMEOUT = 1800000; // milliseconds

// Change to 1 hour:
const SESSION_TIMEOUT = 3600000;

// Change to 15 minutes:
const SESSION_TIMEOUT = 900000;
```

### Database Retention Policy

Edit `src/monit_intel/ingest.py`:

```python
# Current: Keep 30 days of snapshots
RETENTION_DAYS = 30

# Change to 14 days:
RETENTION_DAYS = 14

# Change to 60 days:
RETENTION_DAYS = 60
```

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

## 🔐 Security

- ✅ **Chat passwords:** Hashed with PBKDF2-SHA256 (stored in SQLite, never plain text)
- ✅ **Monit credentials:** Stored in systemd env files (production, chmod 600) or .env (development, not in git)
- ✅ **HTTP Basic Auth:** All REST endpoints require valid chat credentials
- ✅ **WebSocket Auth:** Chat UI requires login with 30-minute session timeout
- ✅ **Read-only agent:** Cannot execute destructive commands (`rm`, `kill`)
- ✅ **Scoped logs:** Only reads paths specified in Log Registry
- ⚠️ **No HTTPS:** Run behind reverse proxy (nginx) for production TLS

For detailed security architecture, see [SECURITY.md](SECURITY.md).

---

## 🐛 Troubleshooting

### Monit Connection Fails

```bash
# Test connection (using Monit service password)
curl -u admin:your_monit_password http://localhost:2812/_status?format=xml | head -10

# Check Monit is running
sudo systemctl status monit

# Check Monit XML API is enabled
grep "set httpd" /etc/monit/monitrc
```

### Ollama Model Not Found

```bash
# List available models
ollama list

# Download Llama 3.1:8b
ollama pull llama3.1:8b

# Test Ollama is running
curl http://localhost:11434/api/tags
```

### Journal Access Denied

```bash
# Add your user to systemd-journal group
sudo usermod -aG systemd-journal $(whoami)

# Apply group changes
newgrp systemd-journal

# Verify access
journalctl -n 1
```

### Check Database State

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

### Systemd Service Won't Start

```bash
# Check detailed error
journalctl -u monit-intel-agent.service -n 50

# Verify service file syntax
systemd-analyze verify /etc/systemd/system/monit-intel-agent.service

# Check environment variables
cat /etc/systemd/system/monit-intel-agent.service.d/env.conf
```

### API Port 8000 Already in Use

```bash
# Find what's using the port
sudo lsof -i :8000

# Kill the old process
sudo kill -9 <PID>

# Or use pkill
pkill -f "pixi run agent"

# Restart service
sudo systemctl restart monit-intel-agent.service
```

### WebSocket Connection Fails

```bash
# Check agent is running (using chat credentials)
curl -u your_username:your_password http://localhost:8000/health

# Check WebSocket endpoint
# Open browser console and test:
# const ws = new WebSocket('ws://localhost:8000/ws/chat');
# ws.onopen = () => console.log('Connected!');
# ws.onerror = (e) => console.log('Error:', e);
```

### Agent Crashes Frequently

```bash
# Check logs for errors
journalctl -u monit-intel-agent.service -f

# Check available memory
free -h

# Check GPU VRAM
nvidia-smi

# If VRAM exhausted, reduce context window in log_reader.py
```

---

## 📝 Next Steps & Future Enhancements

- [ ] Multi-host monitoring (extend to monitor multiple servers)
- [ ] Slack/Email alert escalation
- [ ] Grafana dashboard for historical trends
- [ ] Fine-tune Llama 3.1 model on server logs
- [ ] Predictive failure detection
- [ ] User role-based access control
- [ ] Integration with PagerDuty / Jira
