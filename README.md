# 🤖 Monit-Intel Agent

A **LangGraph + Llama 3.1** powered agent that monitors server health via Monit, analyzes logs intelligently, and performs automated root-cause analysis. Features an interactive MU/TH/UR chat interface for querying system health and executing safe remediation actions.

**Quick links:**
- 📖 [Install & Setup](#-install--setup)
- 🚀 [Quick Start](#-quick-start)
- 💬 [Usage](#-usage)
- 🏗️ [Architecture](#-architecture)
- ⚙️ [Configuration](#-configuration)

---

## 📖 Install & Setup

### Prerequisites

- **Pixi** (lightweight Conda alternative) - [Install here](https://pixi.sh)
- **Monit** running on `localhost:2812` with XML API enabled
- **Ollama** running Llama 3.1:8b on GPU (RTX 4000 or similar)
- **Linux system** (tested on Ubuntu 24.04)

### Step 1: Clone & Install Dependencies

```bash
cd monit-intel
pixi install
```

### Step 2: Configure Credentials

**Option A: Development (Local .env - Easy)**
```bash
cat > .env << EOF
MONIT_USER=admin
MONIT_PASS=your_monit_password
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
cd monit-intel

# Set your chat UI username and password
PYTHONPATH=./src pixi run python -m monit_intel.chat_auth your_username your_secure_password

# Check status
PYTHONPATH=./src pixi run python << 'EOF'
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
PYTHONPATH=./src pixi run python << 'EOF'
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
cd monit-intel

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
cd monit-intel
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
sudo bash ./config/systemd/install-services.sh

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
cd monit-intel
PYTHONPATH=./src pixi run hello-mother
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

## 📊 Example Queries & Responses

Mother analyzes logs from **7 services with detailed logging** and provides immediate insights:

### Query 1: Backup Analysis (system_backup)
```
You: "What about the system backup status?"

Mother:
The system backup completed successfully today with these metrics:
- Transferred: 101,748,887 bytes
- Speed: 10,713,592.95 bytes/sec
- Speedup (compression): 153.08x
- Time: 9.5 seconds

No errors detected in the log. The backup is operating efficiently.
```

### Query 2: VPN Connection Status (nordvpn_connected)
```
You: "What VPN servers has nordvpn been using?"

Mother:
The VPN has connected to 19 different servers across multiple countries:
- US locations (Dallas, Seattle, Kansas City)
- New Zealand locations (Auckland, Wellington)
- Other regions

There are 3 failed connection attempts in the log, suggesting occasional
connection stability issues. Current connection appears healthy.
```

### Query 3: Docker Service Issue (docker)
```
You: "Is there any issue with docker?"

Mother:
Yes, the Docker service is reporting DNS resolution failures:

Recent logs show containers timing out trying to reach:
- api.themoviedb.org (Jellyfin metadata service)
- sync-v2.brave.com (Brave browser container)
- www.omdbapi.com (OMDB API for media)

Error pattern: "read udp 127.0.0.1:*->127.0.0.53:53: i/o timeout"
This indicates DNS resolver (127.0.0.53:53) is unreachable or overloaded.

Recommendation: Check systemd-resolved service or container DNS config.
```

### Query 4: Docker Service (Limited Log Access)
```
You: "What about the Jellyfin container status?"

Mother:
Jellyfin is a Docker container service. Here's what I know:
- Status: healthy (last check 5 minutes ago)
- CPU: 2.4%
- Memory: 245 MB
- Uptime: 14 days

Note: Docker container logs require sudo/docker exec access which I cannot
perform for security reasons. I report database metrics instead. For detailed
Jellyfin logs, run: docker logs jellyfin
```

### Query 5: Disk/ZFS Status
```
You: "Check the sanoid errors service"

Mother:
ZFS snapshots are working correctly. Recent activity:
- 12 snapshots created in the last 3 days
- Pool status: all datasets healthy
- No error messages in the service logs

The sanoid service manages automated ZFS snapshots and cleanup.
```

---

## 🏗️ Architecture

**Monit-Intel** uses a dual-workflow architecture:

1. **Background Agent** - Runs every 5 minutes, detects failures, and analyzes root causes using LangGraph + Llama 3.1
2. **Interactive Chat** - User-facing WebSocket interface for querying system health with 30-day historical context

**Quick Example:**
```bash
# Query via chat UI
User: "What about CPU usage in the last 30 days?"
Mother: "Based on historical trends, docker averages 0.0% CPU, 
         nordvpn 0.2%. All services show minimal consumption..."

# Or via REST API
curl -X POST http://localhost:8000/mother/chat \
  -u your_username:your_password \
  -d '{"query": "Why is docker failing?"}'
```

**For detailed architecture information** including component design, data flow, workflow nodes, database schema, WebSocket protocol, and performance characteristics, see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

Key highlights:
- **3-node LangGraph DAG** for failure detection and analysis
- **30-day rolling snapshots** with CPU/memory/failure metrics
- **OS-aware context injection** (Ubuntu = apt, Fedora = dnf, etc.)
- **Per-service log limits** (50-150 lines) to optimize GPU usage
- **Smart is_critical flag** to skip re-analyzing unchanged failures
- **SQLite persistence** (~20-25MB for 30 days of history)

## 🌐 REST API

Once the agent is running (via systemd or manually with `--api`), the REST API is available on `localhost:8000`.

### Core Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/health` | Check agent status & database connectivity |
| `GET` | `/status` | List all services and their status |
| `POST` | `/mother/chat` | Query agent about system health |
| `GET` | `/mother/history` | View conversation history |

**Quick Examples:**

```bash
# Check agent health
curl -u your_username:your_password http://localhost:8000/health

# Chat with the agent
curl -X POST http://localhost:8000/mother/chat \
  -u your_username:your_password \
  -d '{"query": "Why is docker failing?"}'

# View all services
curl -u your_username:your_password http://localhost:8000/status | jq
```

For all API endpoints and examples, see [ARCHITECTURE.md → WebSocket Protocol](docs/ARCHITECTURE.md#websocket-protocol).

## �️ Mother: AI Analysis & Recommendations

**Mother** (MU/TH/UR) is the conversational AI interface to the agent. It automatically:

1. **Gathers context** from 30 days of historical snapshots
2. **Detects your OS** (Ubuntu, Fedora, Arch, etc.)
3. **Analyzes root causes** of failures using LLM analysis
4. **Provides remediation advice** and troubleshooting steps
5. **Streams responses** via WebSocket in real-time

**⚠️ Read-Only by Design:** Mother analyzes and advises only. All system commands are provided as suggestions for you to execute manually - never executed automatically. This ensures safety and keeps you in control.

**Examples:**
```
User: "Why is nordvpn failing?"
Mother: "The nordvpn service crashed due to authentication timeout. 
         You can restart it with: sudo systemctl restart nordvpnd"

User: "What about CPU usage?"
Mother: "CPU is stable at 0.1% average. nordvpn uses 0.2% max, 
         tailscaled uses 0.1%. All normal."

User: "How do I fix the alpha failures?"
Mother: "The alpha service failed 5 times in 30 days due to timeout.
         Try: sudo systemctl restart alpha
         If that doesn't work, check logs with: journalctl -u alpha -n 50"
```

For detailed Mother architecture, see [ARCHITECTURE.md → Two Parallel Systems](docs/ARCHITECTURE.md#two-parallel-systems).

## ⚙️ Configuration

### Quick Customization

**Adjust monitoring interval:**
```python
# Edit: src/monit_intel/main.py
MONITOR_INTERVAL = 300  # 5 minutes (in seconds)
```

**Customize session timeout:**
```javascript
// Edit: src/monit_intel/agent/static/chat.html
const SESSION_TIMEOUT = 1800000; // 30 minutes (milliseconds)
```

**Change database retention:**
```python
# Edit: src/monit_intel/ingest.py
RETENTION_DAYS = 30  # Keep 30 days of snapshots
```

### Adding New Services to Log Registry

Edit `src/monit_intel/tools/log_reader.py`:

```python
log_registry = {
    "my_service": {
        "strategy": "tail_file",              # or "newest_file", "journalctl"
        "path": "/var/log/my_service.log",   # for tail_file
        "max_lines": 100
    }
}
```

**Strategies:**
- `tail_file` - Read last N lines from single file
- `newest_file` - Find newest file matching glob pattern, then tail
- `journalctl` - Query systemd journal for service unit

For all configuration options, see [ARCHITECTURE.md → Configuration & Customization](docs/ARCHITECTURE.md#configuration--customization).



## 🔐 Security

- ✅ **Chat passwords:** Hashed with PBKDF2-SHA256 (stored in SQLite, never plain text)
- ✅ **Monit credentials:** Stored in systemd env files (production, chmod 600) or .env (development, not in git)
- ✅ **HTTP Basic Auth:** All REST endpoints require valid chat credentials
- ✅ **WebSocket Auth:** Chat UI requires login with 30-minute session timeout
- ✅ **Read-only by design:** Mother analyzes and advises only - never executes commands
- ✅ **Audit logs:** All analysis and recommendations logged for transparency
- ✅ **Scoped logs:** Only reads paths specified in Log Registry
- ⚠️ **No HTTPS:** Run behind reverse proxy (nginx) for production TLS

For detailed security architecture, see [SECURITY.md](docs/SECURITY.md).

---

## � Service Log Accessibility

### 7 Services with Direct Log Access

Mother extracts and quotes specific metrics from logs:

- **system_backup** - File sizes, transfer speeds, compression ratios
- **nordvpn_connected** - VPN server connections and failures
- **nordvpnd** - Service status via journalctl
- **tailscaled** - DERP node info via journalctl
- **network_resurrect** - Network restart logs
- **sanoid_errors** - ZFS snapshot activity via journalctl
- **zfs-zed** - ZFS events via journalctl

### 8 Docker Services (Database Only)

Logs require sudo access. Mother provides database metrics instead:

- immich_server_running, immich_ml_running, immich_pg_running, immich_redis_running
- jellyfin_running, jellyfin_http
- miniflux_running, postgres_running

Mother explains this limitation gracefully in responses.

### 15+ Other Services (Journalctl Fallback)

Automatically queried from systemd journal with smart unit name matching. Mother reports status, CPU, memory, and failure history.

---

## 📝 Next Steps & Future Enhancements

- [ ] Multi-host monitoring (extend to monitor multiple servers)
- [ ] Slack/Email alert escalation
- [ ] Grafana dashboard for historical trends
- [ ] Fine-tune Llama 3.1 model on server logs
- [ ] Predictive failure detection
- [ ] User role-based access control
- [ ] Integration with PagerDuty / Jira
