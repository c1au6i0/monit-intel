#!/bin/bash
set -e
export PATH="/home/heverz/.pixi/bin:$PATH"
cd /home/heverz/py_projects/monit-intel
exec pixi run python main.py --api 5 8000
