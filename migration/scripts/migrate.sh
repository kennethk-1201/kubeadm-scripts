#!/bin/bash

set -euo pipefail

function usage() {
    echo "Usage: $0 [pod_id]"
    echo ""
    echo "Migrate a pod to another node"
    echo ""
    echo "Arguments:"
    echo "  pod_id    Optional pod ID to migrate. If not provided, migrates first running pod"
    echo ""
    echo "Example:"
    echo "  $0"
    echo "  $0 pod_123abc"
    exit 1
}

# Activate virtual environment
source /home/vagrant/migration/venv/bin/activate

# Set PYTHONPATH explicitly
export PYTHONPATH="/home/vagrant"

# Run the migration script
if [ $# -eq 0 ]; then
    python3 -m migration.core.migrate
else
    python3 -m migration.core.migrate "$1"
fi

# Show running pods
echo -e "\nRunning pods:"
sudo crictl pods

echo -e "\nRunning containers:"
sudo crictl ps
