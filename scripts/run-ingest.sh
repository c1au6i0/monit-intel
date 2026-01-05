#!/usr/bin/env bash
set -euo pipefail

# Run Monit-Intel ingest once via pixi, with proper PYTHONPATH
cd /home/heverz/py_projects/monit-intel
export PYTHONPATH="/home/heverz/py_projects/monit-intel/src"

exec /home/heverz/.pixi/bin/pixi run python -m monit_intel.ingest
