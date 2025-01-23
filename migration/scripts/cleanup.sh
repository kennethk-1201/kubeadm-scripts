#!/bin/bash

set -euo pipefail

echo "Cleaning up pods, containers, log directories, and shared logs..."

# Stop and remove all containers
echo "Stopping all containers..."
sudo crictl stopp $(sudo crictl ps -aq) >/dev/null 2>&1 || true
echo "Removing all containers..."
sudo crictl rmp $(sudo crictl ps -aq) >/dev/null 2>&1 || true

# Stop and remove all pods
echo "Stopping all pods..."
sudo crictl stopp $(sudo crictl pods -q) >/dev/null 2>&1 || true
echo "Removing all pods..."
sudo crictl rmp $(sudo crictl pods -q) >/dev/null 2>&1 || true

# Clear the checkpoint directory
if [ -d "/tmp/pod_checkpoint" ]; then
    echo "Clearing /tmp/pod_checkpoint directory..."
    sudo rm -rf /tmp/pod_checkpoint
fi

# Remove all .log directories from /home/vagrant
echo "Removing all .log directories in /home/vagrant..."
sudo find /home/vagrant -type d -name "*.log" -exec rm -rf {} +

# Clear the shared logs directory
if [ -d "/tmp/shared-logs" ]; then
    echo "Clearing /tmp/shared-logs directory..."
    sudo rm -rf /tmp/shared-logs
fi

echo "Cleanup complete."

# Show current state
echo -e "\nCurrent pods:"
sudo crictl pods

echo -e "\nCurrent containers:"
sudo crictl ps
