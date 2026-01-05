# Monit-Intel

**AI-powered system monitoring with LLM analysis of failures.** Query your system health via interactive chat, get root cause analysis, and receive remediation advice—all in an 8B LLM running locally on GPU.

## Quick Start (5 minutes)

### 1. Prerequisites

- **Monit** running on localhost:2812 with admin credentials
- **Ollama** with Llama 3.1:8b (`ollama run llama3.1:8b`)
- **Python 3.11+** via Pixi (see [Environment Setup](#environment-setup))
- **NVIDIA GPU** (optional, ~7GB VRAM for Llama 3.1)

### 2. Setup

```bash
# Clone and enter directory
git clone https://github.com/yourusername/monit-intel.git
cd monit-intel

# Set credentials
export MONIT_USER=admin
export MONIT_PASS=your_monit_password

# Create chat login credentials
pixi run python -m monit_intel.chat_auth your_username your_password
```

### 3. Start the Agent

```bash
# Development (runs agent + API)
pixi run agent

# Production (install systemd services)
sudo bash ./config/systemd/install-services.sh
sudo systemctl start monit-intel-agent.service
sudo systemctl start monit-intel-ingest.timer
```

### 4. Access the Chat UI

Open browser: `http://localhost:8000/chat`

Login with credentials from step 2, then chat:
```
You:   "What's the overall system health?"
Agent: "All services are healthy. Docker at 0.5% CPU, nordvpn at 0.2%..."

You:   "Why is system_backup failing?"
Agent: "Analyzing logs... The backup process timed out due to disk space..."
```

## How It Works

**Monit-Intel** runs two parallel workflows:

1. **Background Agent** (every 5 minutes via systemd timer)
   - Polls Monit service status (30+ services)
   - Detects new failures using LangGraph DAG
   - Stores snapshots in SQLite database (~20-25MB for 30 days)
   - Analyzes root causes with Llama 3.1 LLM

2. **Interactive Mother Chat** (on-demand via API/UI)
   - WebSocket interface for real-time conversation
   - Injects 30-day historical context and trends
   - Provides remediation advice (analysis only, no auto-execution)
   - Session-based auth with 30-minute timeout

**Key Detail:** When you ask "hello" or "how are you?" Mother responds naturally without dumping configuration. When you ask "why is service X failing?" Mother analyzes 30 days of failure history and provides root cause analysis.

## Features

| Feature | Details |
|---------|---------|
| **Real-time Chat UI** | WebSocket-based with responsive phosphor-green terminal theme |
| **Historical Analysis** | 30-day CPU/memory/failure trends with automated rollup |
| **Smart Log Aggregation** | Extracts metrics from system logs, journalctl, and Docker stats |
| **OS-Aware Context** | Detects Ubuntu/Fedora/Arch and provides distro-specific advice |
| **Safe Design** | Read-only analysis with suggested commands (no auto-execution) |
| **Conversation Memory** | Full chat history stored and injected into LLM context |
| **Production Ready** | Systemd services, logging, and audit trails included |

## Usage

### Web Chat UI (Easiest)

After running `pixi run agent`, open `http://localhost:8000/chat` and login.

**Example queries:**
- "What's the status of all services?"
- "Why is docker failing so much?"
- "Show me CPU usage trends"
- "What happened to the network yesterday?"
- "How do I restart the system_backup service?"

### Interactive CLI

```bash
pixi run hello-mother
```

Type queries interactively with multi-line input, `exit` to quit.

### REST API

```bash
# Query (use your chat credentials)
curl -X POST http://localhost:8000/mother/chat \
  -u your_username:your_password \
  -d '{"query": "What about CPU usage?"}'

# Get history
curl -u your_username:your_password http://localhost:8000/mother/history?limit=10

# Check health
curl -u your_username:your_password http://localhost:8000/health
```

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for complete REST API reference.

## Configuration

### Environment Variables

```bash
MONIT_USER=admin              # Monit service username
MONIT_PASS=password           # Monit service password
MONIT_URL=localhost:2812      # Monit server (optional)
OLLAMA_HOST=localhost:11434   # Ollama server (optional)
```

### Customization

| Setting | Location | Default |
|---------|----------|---------|
| Monitor interval | `src/monit_intel/main.py` | 5 minutes |
| Database retention | `src/monit_intel/ingest.py` | 30 days |
| Session timeout | `src/monit_intel/agent/static/chat.html` | 30 minutes |
| LLM model | `src/monit_intel/agent/mother.py` | llama3.1:8b |

## Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow, workflows, database schema, API reference |
| [SECURITY.md](docs/SECURITY.md) | Authentication, password storage, TLS, threat model |
| [STRUCTURE.md](docs/STRUCTURE.md) | Project layout, module organization, imports |

## Project Structure

```
monit-intel/
├── src/monit_intel/
│   ├── main.py              # Background agent daemon
│   ├── ingest.py            # Data ingestion (runs every 5 min)
│   ├── hello_mother.py      # CLI chat interface
│   ├── chat_auth.py         # Session authentication
│   ├── agent/
│   │   ├── graph.py         # LangGraph DAG workflow
│   │   ├── mother.py        # Chat interface + system context
│   │   ├── api.py           # FastAPI server
│   │   ├── nodes.py         # Workflow nodes (detect/fetch/analyze)
│   │   ├── state.py         # Workflow state management
│   │   ├── actions.py       # Safe command executor
│   │   └── static/          # Web UI (chat.html)
│   └── tools/
│       └── log_reader.py    # Service log aggregator
├── docs/                    # Detailed documentation
├── tests/                   # Test suite
├── scripts/                 # Helper scripts
├── config/systemd/          # Production systemd services
├── pixi.toml                # Environment definition (PRIMARY)
├── pyproject.toml           # Package metadata
└── monit_history.db         # SQLite database (auto-created)
```

**Note:** Use `pixi run` for all Python execution. See [Environment Setup](#environment-setup).

## Development

### Run Tests

```bash
pixi run pytest tests/
```

### Code Quality

```bash
pixi run black src/      # Format code
pixi run ruff check src/ # Lint
pixi run mypy src/       # Type check
```

### Environment Setup

**Pixi is the primary environment manager.** All dependencies, channels, and tasks are defined in `pixi.toml`.

Install Pixi: https://pixi.sh

Then:
```bash
pixi install           # Install dependencies
pixi run agent         # Run agent via defined task
pixi run hello-mother  # Run CLI
pixi run pytest        # Run tests
```

Never use `pip` directly or standard `python` commands—always use `pixi run`.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Agent won't start | Check MONIT_USER/MONIT_PASS, verify Monit at localhost:2812, check Ollama on 11434 |
| Chat UI won't load | Ensure `pixi run agent` is running, check http://localhost:8000 |
| Slow responses | Llama 3.1 inference = 2-5 sec on RTX 4000, 10-20 sec on CPU |
| Database locked | `rm monit_history.db` (auto-recreates on next run) |
| Service logs missing | Add entry to [src/monit_intel/tools/log_reader.py](src/monit_intel/tools/log_reader.py) |

### Ingest service keeps restarting

If `monit-intel-ingest.service` fails with environment or path errors, reinstall the systemd units from this repo (they set `PYTHONPATH` and correct `ExecStart`):

```bash
sudo cp config/systemd/monit-intel-ingest.service /etc/systemd/system/
sudo cp config/systemd/monit-intel-ingest.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now monit-intel-ingest.timer
sudo systemctl restart monit-intel-ingest.service
systemctl status monit-intel-ingest.service --no-pager
journalctl -u monit-intel-ingest.service -n 50 --no-pager
```

Notes:
- `EnvironmentFile=-/home/heverz/.env` is optional; missing file will not break the service.
- `ExecStart` runs `pixi run python -m monit_intel.ingest` and `PYTHONPATH` is set to `src`.
- Do not place `ProtectHome`/`ReadWritePaths` in the `[Install]` section; they belong in `[Service]` (already correct in this repo).

## License

MIT

## Support

- **System architecture & design:** See [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Security & authentication:** See [SECURITY.md](docs/SECURITY.md)
- **Module structure & imports:** See [STRUCTURE.md](docs/STRUCTURE.md)
