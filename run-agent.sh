#!/bin/bash
# Start the Monit-Intel agent daemon

cd /home/heverz/py_projects/monit-intel

# Use pixi to run the agent with FastAPI on port 8000
# The --api flag enables the REST API with 5 worker processes
exec ~/.pixi/bin/pixi run agent --api 5 8000
