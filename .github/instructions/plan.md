# 🛠️ Project Plan: Monit-Intel Agent

**Objective:** Build a local AI agent (LangGraph + Llama 3.1) that monitors server health via Monit, stores history in SQLite, and performs automated root-cause analysis using system logs and custom script outputs.

---

## 🏗️ 1. System Architecture

* **Host:** `beta-boy`
* **Environment:** Pixi (Conda-compatible, optimized for RTX 4000).
* **Core Logic:** LangGraph (Python).
* **Intelligence:** Ollama running **Llama 3.1:8b** (VRAM allocated to RTX 4000).
* **Data Source:** Monit XML Status API (`http://localhost:2812/_status?format=xml`).
* **Storage:** SQLite (`monit_history.db`) for state snapshots.

---

## 📂 2. Components & File Structure

### 🛰️ Ingestion Layer (`ingest.py`)

* Polls Monit XML every 5 minutes.
* Parses `<service>` tags (CPU, Memory, Status, Exit Codes).
* Saves diffs to SQLite to track when a service changes from `OK` to `Failed`.

### 🧠 Logic Layer (`agent/`)

* **`state.py`**: Defines the LangGraph state (current alerts, logs found, final diagnosis).
* **`nodes.py`**:
* `check_db`: Fetches the latest failures from SQLite.
* `analyze_logs`: Decides which tool to call based on the service name.
* `reasoning`: Llama 3.1 processes log snippets to explain the "Why."


* **`graph.py`**: Connects the nodes into a workflow.

### 🛠️ Tooling Layer (`tools/`)

* **`log_reader.py`**: A hybrid tool capable of:
* **Tailing** flat files (e.g., `/var/log/nordvpn-reconnect.log`).
* **Finding the Newest** file in a directory (e.g., `/data/tank/backups/sys_restore/`).
* **Querying Journalctl** for system services (`systemd-networkd`, `docker`).



---

## 📜 3. Log Registry Map

The agent uses this map to know where to look when a specific Monit check fails.

| Monit Service | Script/Service Path | Log Strategy |
| --- | --- | --- |
| **system_backup** | `backup_sys.sh` | **Latest File:** `/data/tank/backups/sys_restore/backup_log_*.log` |
| **nordvpn_reconnect** | `nordvpn-reconnect-p2p.sh` | **Append Log:** `/var/log/nordvpn-reconnect.log` |
| **nordvpn_status** | `check-nordvpn-status.sh` | **Journalctl:** `journalctl -u nordvpnd.service` |
| **gamma_conn** | `check_gamma_connectivity.sh` | **Live CLI:** Run `tailscale ping` & check `tailscaled` journal |
| **network_resurrect** | `network-resurrect.sh` | **Append Log:** `/var/log/monit-network-restart.log` |
| **ZFS / Sanoid** | `sanoid.service` | **Journalctl:** `journalctl -u sanoid` |

---

## 🚀 4. Implementation Phases

### Phase 1: The Foundation (Current)

* [x] Define Monit XML ingestion logic.
* [x] Map all custom scripts and log locations.
* [x] Configure Pixi environment with `langgraph` and `ollama`.

### Phase 2: The Data Store

* [ ] Build the SQLite schema for `monit_history`.
* [ ] Write a script to convert Monit's "Status 0/1" into human-readable table entries.

### Phase 3: The Hybrid Log Tool

* [ ] Implement `tools/log_reader.py`.
* [ ] Ensure the Pixi user has `systemd-journal` group permissions.

### Phase 4: LangGraph Integration

* [ ] Create the "ReAct" loop: **Alert Detected** -> **Fetch Logs** -> **Analyze** -> **Respond**.
* [ ] Optimize Llama 3.1 system prompt for server administration.

---

## ⚠️ 5. Constraints & Boundaries

* **Privacy:** The AI only reads logs specified in the Registry. It does not scan the whole `/etc/` or `/home/` directories.
* **Context:** Max log tail is limited to 50 lines to keep the RTX 4000 context window clean and fast.
* **Read-Only:** The AI can read logs but **cannot** execute `rm`, `kill`, or write to config files unless explicitly prompted by the user.

