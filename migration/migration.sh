#!/bin/bash

# =============================================================================
# Pod Migration Script Using CRI-O
# =============================================================================
# This script automates the migration of a Kubernetes Pod from a source node
# to a destination node using CRI-O. It performs container
# checkpointing on the source node and restores them on the destination node.
#
# Usage:
#   ./pod_migration.sh <pod_name> <pod_namespace> <destination_node> <ssh_user>
#
# Example:
#   ./pod_migration.sh webserver default 10.0.0.10 vagrant
#
# =============================================================================

# Exit immediately if a command exits with a non-zero status
set -e

# ---------------------------
# Function: Usage
# ---------------------------
usage() {
    echo "Usage: $0 <pod_name> <pod_namespace> <destination_node> <ssh_user>"
    echo "Example: $0 webserver default 10.0.0.10 vagrant"
    exit 1
}

# ---------------------------
# Function: Check Dependencies
# ---------------------------
check_dependencies() {
    local deps=("crictl" "grpcurl" "jq" "rsync" "scp" "ssh")
    for cmd in "${deps[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            echo "Error: $cmd is not installed."
            exit 1
        fi
    done
}

# ---------------------------
# Function: Check Arguments
# ---------------------------
check_arguments() {
    if [ "$#" -ne 4 ]; then
        usage
    fi
}

# ---------------------------
# Function: Source Node - Checkpoint Containers and Capture Metadata
# ---------------------------
checkpoint_containers() {
    local POD_NAME="$1"
    local POD_NAMESPACE="$2"
    local CHECKPOINT_DIR="$3"

    echo "=== Identifying PodSandbox ID for Pod '$POD_NAME' in namespace '$POD_NAMESPACE' ==="
    POD_ID=$(crictl pods --name "$POD_NAME" --namespace "$POD_NAMESPACE" -q)
    if [ -z "$POD_ID" ]; then
        echo "Error: Pod '$POD_NAME' in namespace '$POD_NAMESPACE' not found."
        exit 1
    fi
    echo "PodSandbox ID: $POD_ID"

    echo "=== Inspecting PodSandbox ==="
    mkdir -p "$CHECKPOINT_DIR"
    crictl inspectp "$POD_ID" > "$CHECKPOINT_DIR/pod_inspect.json"
    echo "PodSandbox configuration saved to $CHECKPOINT_DIR/pod_inspect.json"

    echo "=== Listing Containers in PodSandbox ==="
    CONTAINER_IDS=$(crictl ps --pod "$POD_ID" -q)
    if [ -z "$CONTAINER_IDS" ]; then
        echo "No containers found in PodSandbox."
        exit 1
    fi
    echo "Found containers: $CONTAINER_IDS"

    echo "=== Performing Checkpointing and Capturing Metadata for Each Container ==="
    mkdir -p "$CHECKPOINT_DIR"
    for CONTAINER_ID in $CONTAINER_IDS; do
        echo "Checkpointing container: $CONTAINER_ID"
        TARGET_FILE="$CHECKPOINT_DIR/${CONTAINER_ID}.tar.gz"
        crictl checkpoint --export="$TARGET_FILE" "$CONTAINER_ID"
        echo "Checkpointed container $CONTAINER_ID to $TARGET_FILE"

        # Capture container metadata
        echo "Capturing container metadata for $CONTAINER_ID"
        crictl inspect "$CONTAINER_ID" > "$CHECKPOINT_DIR/${CONTAINER_ID}_metadata.json"
        echo "Container metadata saved to $CHECKPOINT_DIR/${CONTAINER_ID}_metadata.json"
    done
}


# ---------------------------
# Function: Transfer Data to Destination Node
# ---------------------------
transfer_data() {
    local CHECKPOINT_DIR="$1"
    local DESTINATION_NODE="$2"
    local SSH_USER="$3"
    local REMOTE_DIR="$4"
    local SSH_KEY="/vagrant/.vagrant/machines/master/parallels/private_key"  # Update this path as necessary otherwise the script will ask for password

    echo "=== Transferring Checkpoint Data and Pod Metadata to Destination Node ==="

    # Rsync command to transfer checkpoint data, metadata, and pod inspect file with sudo on the remote
    rsync -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" -avz "$CHECKPOINT_DIR/" "$SSH_USER@$DESTINATION_NODE:$REMOTE_DIR/" --rsync-path="sudo rsync"

    echo "Checkpoint data and Pod metadata transferred."
}


# ---------------------------
# Function: Destination Node - Restore Pod
# ---------------------------
restore_pod() {
    local DESTINATION_NODE="$1"
    local SSH_USER="$2"
    local REMOTE_DIR="$3"
    local IMAGE_REGISTRY="$4"
    local SSH_KEY="/vagrant/.vagrant/machines/master/parallels/private_key"  # Ensure this path points to the correct private key

    echo "=== Restoring Pod on Destination Node ==="

    # Transfer the remote script to the destination node
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no restore_pod_remote.sh "$SSH_USER@$DESTINATION_NODE:/tmp/restore_pod_remote.sh"

    # Make sure the script is executable
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$DESTINATION_NODE" "chmod +x /tmp/restore_pod_remote.sh"

    # Execute the remote restore script on the destination node
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$DESTINATION_NODE" sudo /tmp/restore_pod_remote.sh "$REMOTE_DIR" "$IMAGE_REGISTRY"
}


# ---------------------------
# Main Execution Flow
# ---------------------------

# Check if the correct number of arguments is provided
check_arguments "$@"

# Assign arguments to variables
POD_NAME="$1"
POD_NAMESPACE="$2"
DESTINATION_NODE="$3"
SSH_USER="$4"

# Define local and remote directories for checkpoints
CHECKPOINT_DIR="/var/lib/crio/checkpoints"
REMOTE_DIR="/var/lib/crio/restore"

# Define Image Registry
IMAGE_REGISTRY="docker.io/your-registry"

# Check for required dependencies
check_dependencies

# Step 1: Checkpoint Containers on Source Node
checkpoint_containers "$POD_NAME" "$POD_NAMESPACE" "$CHECKPOINT_DIR"

# Step 2: Transfer Checkpoint Data and Pod Metadata to Destination Node
transfer_data "$CHECKPOINT_DIR" "$DESTINATION_NODE" "$SSH_USER" "$REMOTE_DIR"

# Step 3: Restore Pod on Destination Node
restore_pod "$DESTINATION_NODE" "$SSH_USER" "$REMOTE_DIR" "$IMAGE_REGISTRY"

echo "=== Pod Migration Completed Successfully ==="
