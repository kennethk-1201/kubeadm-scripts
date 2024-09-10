#!/bin/bash

set -euxo pipefail

if [ -z "$1" ]; then
    echo "Usage: $0 <container_id>"
    exit 1
fi

CONTAINER_ID=$1
CHECKPOINT_DIR="/tmp/runc-postcopy-checkpoint-${CONTAINER_ID}"
RESTORED_CONTAINER_ID="${CONTAINER_ID}-postcopy-restored"

# Clean up any previous runs
runc delete -f $RESTORED_CONTAINER_ID || true
rm -rf "$CHECKPOINT_DIR"

# Create checkpoint directory
mkdir -p "$CHECKPOINT_DIR"

# Checkpoint the container with postcopy strategies
time runc checkpoint --image-path "$CHECKPOINT_DIR" --lazy-pages --leave-running $CONTAINER_ID

# Restore the container with timing
time runc restore --image-path "$CHECKPOINT_DIR" --bundle "/run/containerd/io.containerd.runtime.v2.task/k8s.io/$CONTAINER_ID" $RESTORED_CONTAINER_ID

# Clean up
runc delete $RESTORED_CONTAINER_ID
rm -rf "$CHECKPOINT_DIR"

echo "Post-Copy checkpoint and restore test completed successfully."
