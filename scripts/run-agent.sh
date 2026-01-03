#!/bin/bash
set -e
export PATH="/home/heverz/.pixi/bin:$PATH"
export PYTHONPATH="/home/heverz/py_projects/monit-intel/src:$PYTHONPATH"
cd /home/heverz/py_projects/monit-intel
exec pixi run python -m monit_intel.main --api 5 8000
