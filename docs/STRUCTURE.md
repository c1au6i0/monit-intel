# Project Structure

Monit-Intel has been reorganized into a professional Python package structure for better maintainability and distribution.

## Directory Layout

```
monit-intel/
├── src/monit_intel/           # Main package (installable)
│   ├── __init__.py
│   ├── __main__.py            # Entry point for `python -m monit_intel`
│   ├── main.py                # Agent daemon with REST API
│   ├── ingest.py              # Monit data ingestion
│   ├── hello_mother.py        # Interactive CLI
│   ├── agent/                 # Agent components
│   │   ├── __init__.py
│   │   ├── api.py             # FastAPI REST server
│   │   ├── graph.py           # LangGraph workflow
│   │   ├── state.py           # Agent state definition
│   │   ├── nodes.py           # Workflow nodes
│   │   ├── mother.py          # Interactive chat manager
│   │   └── actions.py         # Safe command executor
│   └── tools/                 # Utility modules
│       ├── __init__.py
│       └── log_reader.py      # Service log reader
│
├── config/systemd/            # Systemd configuration
│   ├── install-services.sh    # Installation script
│   ├── monit-intel-agent.service
│   ├── monit-intel-ingest.service
│   └── monit-intel-ingest.timer
│
├── scripts/                   # Helper scripts
│   └── run-agent.sh           # Agent startup script
│
├── tests/                     # Test suite
│   └── test_agent.py
│
├── pyproject.toml            # Python package metadata
├── pixi.toml                 # Pixi project config
├── pixi.lock                 # Pixi lock file
├── .github/                  # GitHub config
├── monit-intel               # Wrapper script (convenience)
├── monit_history.db          # SQLite database
└── README.md
```

## Running the Application

### Using PYTHONPATH (development)
```bash
cd /home/heverz/py_projects/monit-intel

# Run agent daemon with API
PYTHONPATH=./src pixi run python -m monit_intel.main --api 5 8000

# Run interactive chat
PYTHONPATH=./src pixi run python -m monit_intel.hello_mother

# Run data ingestion
PYTHONPATH=./src pixi run python -m monit_intel.ingest
```

### Using pixi tasks
```bash
# From pixi.toml [tasks]
pixi run agent            # Runs: python -m monit_intel.main
pixi run hello-mother     # Runs: python -m monit_intel.hello_mother
pixi run ingest           # Runs: python -m monit_intel.ingest
```

### Using systemd services
```bash
# Install services
sudo bash /path/to/config/systemd/install-services.sh

# Start services
sudo systemctl start monit-intel-agent.service
sudo systemctl start monit-intel-ingest.timer

# View logs
journalctl -u monit-intel-agent.service -f
journalctl -u monit-intel-ingest.service -f
```

## Module Imports

Within the package, use relative imports:

```python
# In src/monit_intel/main.py
from .agent.api import app
from .agent.graph import build_graph

# In src/monit_intel/agent/api.py
from .graph import build_graph
from ..tools.log_reader import LogReader
```

## Environment Configuration

Set `PYTHONPATH` when running:
```bash
export PYTHONPATH="/home/heverz/py_projects/monit-intel/src:$PYTHONPATH"
```

Systemd services automatically set this via `Environment` directive in `.service` files.

## Installation (Future)

Once ready for distribution:
```bash
pip install -e .
# Then commands become available globally:
monit-intel --help
hello-mother --help
```
