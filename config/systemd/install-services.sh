#!/bin/bash
# Install Monit-Intel systemd services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Monit-Intel systemd services..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

# Copy service files
echo "Copying service files to /etc/systemd/system/..."
cp "$SCRIPT_DIR/monit-intel-ingest.service" /etc/systemd/system/
cp "$SCRIPT_DIR/monit-intel-ingest.timer" /etc/systemd/system/
cp "$SCRIPT_DIR/monit-intel-agent.service" /etc/systemd/system/

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable services
echo "Enabling services..."
systemctl enable monit-intel-ingest.timer
systemctl enable monit-intel-agent.service

# Start services
echo "Starting services..."
systemctl start monit-intel-ingest.timer
systemctl start monit-intel-agent.service

# Show status
echo ""
echo "Service status:"
systemctl status monit-intel-ingest.timer --no-pager
systemctl status monit-intel-agent.service --no-pager

echo ""
echo "Installation complete!"
echo ""
echo "Check logs with:"
echo "  journalctl -u monit-intel-ingest.service -f"
echo "  journalctl -u monit-intel-agent.service -f"
echo ""
echo "API available at: http://localhost:8000"
