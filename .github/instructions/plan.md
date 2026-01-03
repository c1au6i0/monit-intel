# 🛠️ Project Plan: Monit-Intel Agent

**Objective:** Build a local AI agent (LangGraph + Llama 3.1) that monitors server health via Monit, stores history in SQLite, performs automated root-cause analysis, and provides an interactive "Mother" chat interface for querying and remediating issues.

---

## 📊 Project Status

✅ **Phase 1-4: COMPLETE**
- ✅ Monit XML ingestion with 30-day retention
- ✅ Hybrid state tracking (NEW vs ONGOING failures)
- ✅ Per-service configurable log limits
- ✅ LangGraph workflow (detect → fetch logs → analyze)
- ✅ REST API (6 endpoints, fully tested)
- ✅ Systemd deployment (auto-start, auto-restart)
- ✅ Secure credentials via systemd EnvironmentFile

🔄 **Phase 5-6: IN PROGRESS**
- 🆕 Mother: Interactive chat interface (feature request)
- 🆕 Agent actions: systemd/monit command execution (feature request)

---

## 🏗️ 1. System Architecture

* **Host:** `beta-boy`
* **Environment:** Pixi (Conda-compatible, optimized for RTX 4000).
* **Core Logic:** LangGraph (Python).
* **Intelligence:** Ollama running **Llama 3.1:8b** (VRAM allocated to RTX 4000).
* **Data Source:** Monit XML Status API (`http://localhost:2812/_status?format=xml`).
* **Storage:** SQLite (`monit_history.db`) for state snapshots + failure_history for state tracking.
* **Deployment:** Systemd services (agent daemon + ingest timer) for auto-startup on boot.
* **API:** FastAPI REST server (port 8000) for interactive access and automation.

---

## 📂 2. Components & File Structure

### 🛰️ Ingestion Layer (`ingest.py`)

* Polls Monit XML every 5 minutes via systemd timer.
* Parses `<service>` tags (CPU, Memory, Status, Exit Codes).
* **Snapshots Table:** Inserts all service snapshots for rolling 30-day history.
* **Failure History Table:** Tracks per-service state (last_status, times_failed) to detect NEW vs ONGOING failures.
* **Auto-Cleanup:** Deletes snapshots >30 days old after each ingestion run.
* **Credentials:** Loaded from systemd EnvironmentFile (not git-tracked).

### 🧠 Logic Layer (`agent/`)

* **`state.py`**: LangGraph state definition (messages, context_data, is_critical).
* **`graph.py`**: LangGraph workflow DAG with 3 nodes:
  - `detect_failures()`: Queries snapshots, filters to log-registry services, compares to failure_history to find NEW/CHANGED failures.
  - `fetch_logs_and_context()`: Uses LogReader with per-service max_lines configuration (system_backup: 150, others: 50-100).
  - `analyze_with_llm()`: Calls Llama 3.1:8b only for NEW/CHANGED failures (skips unchanged to save GPU).
* **`nodes.py`**: Individual node implementations.
* **`api.py`**: FastAPI REST server with 6 endpoints (status, health, analyze, history, logs, root).

### 🛠️ Tooling Layer (`tools/`)

* **`log_reader.py`**: Hybrid log fetcher with per-service configuration:
  - **Tailing** flat files (e.g., `/var/log/nordvpn-reconnect.log`).
  - **Glob patterns** for newest file (e.g., `/data/tank/backups/sys_restore/backup_log_*.log`).
  - **Journalctl** queries for systemd services (e.g., `journalctl -u nordvpnd.service`).
  - Per-service max_lines limits to control VRAM usage.

### ⚙️ Deployment Layer (`systemd/`)

* **`monit-intel-agent.service`**: Daemon that runs agent with REST API (Type=simple, Restart=on-failure).
* **`monit-intel-ingest.service`**: Service that runs ingest.py (triggered by timer).
* **`monit-intel-ingest.timer`**: Scheduler that triggers ingest every 5 minutes.
* **Drop-in configs:** `/etc/systemd/system/monit-intel-*.service.d/env.conf` stores credentials securely.
* **Install script:** `install-services.sh` sets up all systemd files and enables on boot.



---

## 📜 3. Log Registry Map

The agent uses this map to know where to look when a specific Monit check fails.

| Monit Service | Log Strategy | Path/Unit | Max Lines |
| --- | --- | --- | --- |
| **system_backup** | Newest File Glob | `/data/tank/backups/sys_restore/backup_log_*.log` | 150 |
| **nordvpn_reconnect** | Tail File | `/var/log/nordvpn-reconnect.log` | 75 |
| **nordvpn_status** | Journalctl | `nordvpnd.service` | 50 |
| **gamma_conn** | Journalctl | `tailscaled.service` | 75 |
| **network_resurrect** | Tail File | `/var/log/monit-network-restart.log` | 100 |
| **zfs_sanoid** | Journalctl | `sanoid.service` | 100 |

**Note:** `alpha` (host ping) excluded—no logs available, only connectivity check.

---

## 🚀 4. Implementation Phases

### Phase 1: The Foundation ✅ COMPLETE

* [x] Define Monit XML ingestion logic.
* [x] Map all custom scripts and log locations.
* [x] Configure Pixi environment with `langgraph`, `fastapi`, `uvicorn`, `ollama`.

### Phase 2: The Data Store ✅ COMPLETE

* [x] Build SQLite schema: `snapshots` (rolling 30-day) + `failure_history` (state tracking).
* [x] Implement 30-day auto-cleanup after each ingest run.
* [x] Track per-service state to detect NEW vs ONGOING failures.

### Phase 3: The Hybrid Log Tool ✅ COMPLETE

* [x] Implement `tools/log_reader.py` with 3 strategies (tail, glob, journalctl).
* [x] Per-service max_lines configuration to control context window.
* [x] Filter log registry to only monitored services.

### Phase 4: LangGraph Integration ✅ COMPLETE

* [x] Create ReAct loop: Detect Failures → Fetch Logs → Analyze with LLM.
* [x] Implement state tracking to skip LLM for unchanged failures.
* [x] Optimize Llama 3.1 system prompt for root-cause analysis.
* [x] Extract graph.py from main.py for modularity.

### Phase 5: REST API & Deployment ✅ COMPLETE

* [x] Build FastAPI REST server (6 endpoints: root, health, status, analyze, history, logs).
* [x] Implement systemd deployment (agent service + ingest timer).
* [x] Store credentials securely in systemd EnvironmentFile (Option 3).
* [x] Test all endpoints with curl.

### Phase 6: Interactive Chat ("Mother") 🆕 IN PROGRESS

* [ ] **Mother CLI**: Interactive chat interface that queries the agent over REST API.
* [ ] **Message history**: Store conversation context in SQLite (new table: `conversations`).
* [ ] **Agent context**: Mother can pull service status, failure history, and logs to inform prompts.
* [ ] **Implementation**: Python click CLI or web UI (TBD).

### Phase 7: Agent Actions 🆕 IN PROGRESS

* [ ] **Systemd commands**: Agent can restart services safely (e.g., `systemctl restart nordvpnd`).
* [ ] **Monit commands**: Agent can trigger Monit re-check (e.g., `monit monitor <service>`).
* [ ] **Read-only guardrails**: Actions whitelist (only safe operations, no destructive commands).
* [ ] **Audit logging**: Log all agent actions to SQLite for accountability.
* [ ] **Prompt engineering**: Teach Llama 3.1 when/how to suggest actions without executing.
* [ ] **Confirmation flow**: User approval before executing sensitive commands.

---

## ⚠️ 5. Constraints & Boundaries

### Read-Only by Default
* The agent reads logs but cannot execute destructive commands (`rm`, `kill`, rewrite config files).
* All actions require explicit user approval via Mother chat interface.

### Context Windows
* Per-service max_lines limits (50-150) keep Llama 3.1 context efficient.
* Snapshot retention: Rolling 30-day window prevents unbounded database growth.
* Conversation history: Stored in SQLite for Mother chat persistence.

### Security & Privacy
* Credentials stored securely in systemd EnvironmentFile (not in git, not in project folder).
* Agent only reads logs from Log Registry (scoped access, no `/etc/` or `/home/` scanning).
* Systemd service runs as unprivileged user (`heverz`).
* Action whitelist enforces safe operations only (no rm, kill, or config rewrites).

### Performance
* Ingest runs every 5 minutes → ~288 runs/day → ~1500-3000 new snapshots/day.
* Auto-cleanup deletes old snapshots daily to maintain ~20-25MB database size.
* Llama 3.1 inference takes 2-5 seconds per analysis (GPU bottleneck).
* LLM skipping for unchanged failures saves significant compute.

### Deployment
* Systemd auto-restart: Agent respawns within 10 seconds of crash.
* Boot-time startup: Both agent and ingest timer enabled with `systemctl enable`.
* Zero manual intervention needed after initial `install-services.sh`.

---

## 🤖 6. Phase 6: Mother - Interactive Chat Interface

### Overview
"Mother" is an interactive CLI/Web interface that allows humans to query the agent in natural language and get real-time analysis + remediation suggestions.

### Architecture

```
┌─────────────────────────────────────────┐
│   Mother CLI / Web UI                   │
│   (Python Click or FastAPI Frontend)    │
└────────────┬────────────────────────────┘
             │ (HTTP/WebSocket)
             ▼
┌─────────────────────────────────────────┐
│   REST API Server (FastAPI)             │
│   - POST /mother/chat                   │
│   - GET  /mother/history                │
│   - DELETE /mother/clear                │
└────────────┬────────────────────────────┘
             │ (SQLite queries + Agent inference)
             ▼
┌─────────────────────────────────────────┐
│   Agent Logic                           │
│   - Service status context              │
│   - Failure history lookup              │
│   - Log retrieval + LLM analysis        │
└─────────────────────────────────────────┘
```

### Features

| Feature | Description |
| --- | --- |
| **Natural Language Queries** | "Why is system_backup failing?" → Agent fetches logs, analyzes, responds. |
| **Contextual Memory** | Mother stores conversation history in SQLite (`conversations` table). |
| **Service Status Context** | Mother can query current service status before passing to LLM. |
| **Failure History** | "Show me the last 5 failures of nordvpn_status" → Pulls from failure_history table. |
| **Log Retrieval** | "Show logs for gamma_conn" → Uses LogReader to fetch latest logs. |
| **Action Suggestions** | Agent suggests remediations (e.g., "Consider restarting tailscaled"). |

### Database Schema (New)

```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    user_query TEXT,
    agent_response TEXT,
    service_context TEXT,  -- JSON: relevant service statuses at query time
    logs_provided TEXT     -- JSON: logs that were included in analysis
);
```

### Implementation Tasks

- [ ] Create `agent/mother.py` with Mother class (manages conversation state).
- [ ] Add `/mother/chat` endpoint to `agent/api.py`.
- [ ] Implement `conversations` SQLite table in database initialization.
- [ ] Build CLI (`mother-cli.py`) using Python `click` library.
- [ ] (Optional) Build simple web UI with Streamlit or React.
- [ ] Add "context injection" to LLM prompts (current service status + recent logs).

---

## 🛠️ 7. Phase 7: Agent Actions - Systemd & Monit Command Execution

### Overview
The agent can suggest AND execute safe remediation actions on your system. Examples:
- Restart a failing systemd service
- Trigger a Monit re-check
- Enable/disable a service
- View systemd service logs in real-time

### Architecture

```
┌──────────────────────────────────────────────┐
│   Mother Chat Interface                      │
│   "Restart nordvpnd, it keeps crashing"     │
└────────────┬─────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────┐
│   Agent Analyzes Query                       │
│   - Detects action intent (restart, monitor) │
│   - Checks whitelist (safe?)                 │
│   - Suggests action to user                  │
└────────────┬─────────────────────────────────┘
             │
    ┌────────┴────────┐
    │ Unsafe Action   │ Safe Action
    │ (blocked)       │ (ask user)
    │                 ▼
    │          ┌──────────────────────┐
    │          │ Confirmation Needed  │
    │          │ "Execute: systemctl  │
    │          │ restart nordvpnd?    │
    │          │ (y/n)"               │
    │          └────────┬─────────────┘
    │                   │ (user confirms)
    │                   ▼
    │          ┌──────────────────────┐
    │          │ Execute Action       │
    │          │ Run command, log it  │
    │          │ Report result        │
    │          └──────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────┐
│   Action Audit Log (SQLite)                  │
│   - What action? Who approved? When? Result? │
└──────────────────────────────────────────────┘
```

### Safe Actions Whitelist

| Action | Command | Purpose |
| --- | --- | --- |
| **Restart Service** | `systemctl restart <service>` | Recover from transient failures. |
| **Stop Service** | `systemctl stop <service>` | Prevent cascading failures. |
| **Start Service** | `systemctl start <service>` | Bring service online. |
| **Check Status** | `systemctl status <service>` | Get detailed systemd state. |
| **Monit Check** | `monit monitor <service>` | Force Monit re-check immediately. |
| **Monit Start** | `monit start <service>` | Tell Monit to bring service online. |
| **Monit Stop** | `monit stop <service>` | Tell Monit to stop watching. |
| **View Logs** | `journalctl -u <service>` | Retrieve full journal for service. |

### Blocked Actions

- `rm`, `kill -9`, `reboot`, `shutdown`
- Writing to `/etc/`, `/root/`, config files
- Installing packages (`apt install`, `pip install`)
- Network commands (`ifconfig`, `ip route`)

### Database Schema (New)

```sql
CREATE TABLE action_audit_log (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    action_type TEXT,            -- "restart_service", "monit_check", etc.
    service_name TEXT,
    command TEXT,                -- Actual command executed
    user_approved BOOLEAN,       -- Did user confirm?
    result TEXT,                 -- Exit code + output
    error_message TEXT           -- If failed
);
```

### Implementation Tasks

- [ ] Create `agent/actions.py` with ActionExecutor class.
  - Define `SAFE_ACTIONS` whitelist.
  - Implement `execute_safe_action(action, service)` function.
  - Sandbox subprocess calls (timeout, capture output).
- [ ] Update LLM system prompt to teach agent when to suggest actions.
- [ ] Add `/mother/actions/suggest` endpoint (agent proposes action).
- [ ] Add `/mother/actions/execute` endpoint (user confirms, agent executes).
- [ ] Create `action_audit_log` table in SQLite.
- [ ] Update Mother CLI to support action confirmation flow.
- [ ] Add `--dry-run` flag to preview commands without executing.

### Execution Safety Measures

1. **Whitelist-based:** Only SAFE_ACTIONS are allowed.
2. **Confirmation flow:** Require explicit user approval before executing.
3. **Timeout protection:** Commands must complete in <30 seconds.
4. **Output capture:** Store full command output (stdout + stderr) in audit log.
5. **Error handling:** Gracefully handle failures, report results to user.
6. **Permissions:** Systemd commands run as the Pixi user (`heverz`), elevated with sudo where needed.

---

## 🎯 Next Steps

### Immediate (Week 1)
1. Finalize Phase 6 & 7 specifications (this document).
2. Prototype Mother CLI with basic `/mother/chat` endpoint.
3. Implement `conversations` SQLite table.

### Short-term (Week 2-3)
1. Build out Mother CLI command structure.
2. Implement `ActionExecutor` with safe whitelist.
3. Add action suggestion prompts to Llama 3.1 system message.
4. Test action execution with curl + manual approval.

### Medium-term (Month 2)
1. Web UI for Mother (Streamlit or React).
2. Advanced LLM prompt tuning for action recommendations.
3. Audit log dashboard (view all executed actions).
4. Integration testing with real service failures.

### Long-term (Future)
1. Fine-tuned Llama 3.1 model on server admin logs.
2. Multi-host support (monitor multiple servers).
3. Slack/Email integration for alerts and action approvals.
4. Grafana dashboard pulling from SQLite history.

