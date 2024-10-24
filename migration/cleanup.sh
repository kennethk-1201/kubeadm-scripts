#!/bin/bash

set -euxo pipefail

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

# Clear the /tmp/pod_checkpoint directory
if [ -d "/tmp/pod_checkpoint" ]; then
    echo "Clearing /tmp/pod_checkpoint directory..."
    sudo rm -rf /tmp/pod_checkpoint
fi

echo "Cleanup complete."
