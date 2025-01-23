#!/bin/bash

set -euo pipefail

function usage() {
    echo "Usage: $0 <checkpoint_dir>"
    echo ""
    echo "Restore a pod from a checkpoint directory"
    echo ""
    echo "Arguments:"
    echo "  checkpoint_dir    Directory containing pod checkpoint data"
    echo ""
    echo "Example:"
    echo "  $0 /tmp/pod_checkpoint"
    exit 1
}

if [ "$#" -lt 1 ]; then
    usage
fi

CHECKPOINT_DIR=$1

# Activate virtual environment
source /home/vagrant/migration/venv/bin/activate

# Set PYTHONPATH explicitly
export PYTHONPATH="/home/vagrant"

# Run the restore script
python3 -m migration.core.restore "$CHECKPOINT_DIR"

# Show running pods
echo -e "\nRunning pods:"
sudo crictl pods

echo -e "\nRunning containers:"
sudo crictl ps
