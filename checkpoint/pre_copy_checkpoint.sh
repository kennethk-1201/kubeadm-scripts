#!/bin/bash

set -euxo pipefail

if [ -z "$1" ]; then
    echo "Usage: $0 <container_id>"
    exit 1
fi

CONTAINER_ID=$1
CHECKPOINT_DIR="/tmp/runc-precopy-checkpoint-${CONTAINER_ID}"
RESTORED_CONTAINER_ID="${CONTAINER_ID}-precopy-restored"

# Clean up any previous runs
runc delete -f $RESTORED_CONTAINER_ID || true
rm -rf "$CHECKPOINT_DIR"

# Create checkpoint directory
mkdir -p "$CHECKPOINT_DIR"

# Record the start time of the checkpoint
START_TIME=$(date +%s)

# Checkpoint the container with precopy strategies
runc checkpoint --image-path "$CHECKPOINT_DIR" --pre-dump --track-mem --auto-dedup --leave-running $CONTAINER_ID

# Record the end time of the checkpoint
CHECKPOINT_END_TIME=$(date +%s)

# Start the restore process
RESTORE_START_TIME=$(date +%s)

# Restore the container with timing
runc restore --image-path "$CHECKPOINT_DIR" --bundle "/run/containerd/io.containerd.runtime.v2.task/k8s.io/$CONTAINER_ID" $RESTORED_CONTAINER_ID

# Record the end time of the restore
RESTORE_END_TIME=$(date +%s)

# Calculate total migration time and downtime
TOTAL_MIGRATION_TIME=$((RESTORE_END_TIME - START_TIME))
DOWNTIME=$((RESTORE_START_TIME - CHECKPOINT_END_TIME))

# Clean up
runc delete $RESTORED_CONTAINER_ID
rm -rf "$CHECKPOINT_DIR"

echo "Pre-Copy checkpoint and restore test completed successfully."
echo "Total Migration Time: ${TOTAL_MIGRATION_TIME} seconds"
echo "Downtime: ${DOWNTIME} seconds"
