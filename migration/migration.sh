#!/bin/bash

# =============================================================================
# Pod Migration Script Using CRI-O and Buildah
# =============================================================================
# This script automates the migration of a Kubernetes Pod from a source node
# to a destination node using CRI-O and Buildah. It captures the images used
# by the containers in the pod, transfers them to the destination node, and
# recreates the pod there.
#
# Usage:
#   ./migration.sh <pod_name> <pod_namespace> <destination_node> <ssh_user>
#
# Example:
#   ./migration.sh webserver default 10.0.0.10 vagrant
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
    local deps=("crictl" "buildah" "jq" "rsync" "scp" "ssh")
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
# Function: Select Pod to Migrate
# ---------------------------
select_pod_to_migrate() {
    local POD_NAME="$1"
    local POD_NAMESPACE="$2"

    echo "=== Selecting PodSandbox ID for Pod '$POD_NAME' in namespace '$POD_NAMESPACE' ==="

    # Fetch all Pod IDs with the given name and namespace
    POD_IDS=$(sudo crictl pods --name "$POD_NAME" --namespace "$POD_NAMESPACE" -q)

    if [ -z "$POD_IDS" ]; then
        echo "Error: No pods found with name '$POD_NAME' in namespace '$POD_NAMESPACE'."
        exit 1
    fi

    # If there's only one pod, select it
    if [ $(echo "$POD_IDS" | wc -l) -eq 1 ]; then
        POD_ID="$POD_IDS"
        echo "Single PodSandbox ID found: $POD_ID"
    else
        echo "Multiple pods found with name '$POD_NAME' in namespace '$POD_NAMESPACE'. Selecting the most recent one."

        # Get the creation times of the pods and sort them
        POD_ID=$(sudo crictl pods --name "$POD_NAME" --namespace "$POD_NAMESPACE" -o json | \
            jq -r '.items[] | "\(.metadata.createdAt) \(.id)"' | \
            sort -r | head -n1 | awk '{print $2}')

        echo "Selected PodSandbox ID: $POD_ID"
    fi
}

# ---------------------------
# Function: Source Node - Capture Images and Metadata
# ---------------------------
capture_images_and_metadata() {
    local POD_ID="$1"
    local CHECKPOINT_DIR="$2"

    echo "=== Capturing PodSandbox Configuration ==="
    mkdir -p "$CHECKPOINT_DIR"
    sudo crictl inspectp "$POD_ID" > "$CHECKPOINT_DIR/pod_inspect.json"
    echo "PodSandbox configuration saved to $CHECKPOINT_DIR/pod_inspect.json"

    echo "=== Listing Containers in PodSandbox ==="
    CONTAINER_IDS=$(sudo crictl ps --pod "$POD_ID" -q)
    if [ -z "$CONTAINER_IDS" ]; then
        echo "No containers found in PodSandbox."
        exit 1
    fi
    echo "Found containers: $CONTAINER_IDS"

    echo "=== Processing Containers ==="
    for CONTAINER_ID in $CONTAINER_IDS; do
        echo "Processing container: $CONTAINER_ID"

        # Capture container metadata
        echo "Capturing container metadata for $CONTAINER_ID"
        sudo crictl inspect "$CONTAINER_ID" > "$CHECKPOINT_DIR/${CONTAINER_ID}_metadata.json"
        echo "Container metadata saved to $CHECKPOINT_DIR/${CONTAINER_ID}_metadata.json"

        # Get the image name from the container metadata
        IMAGE_NAME=$(jq -r '.status.image.image' "$CHECKPOINT_DIR/${CONTAINER_ID}_metadata.json")
        echo "Image name for container $CONTAINER_ID: $IMAGE_NAME"

        # Pull the image to ensure it's available locally
        echo "Pulling image $IMAGE_NAME"
        sudo buildah pull "$IMAGE_NAME"

        # Save the image to a tar file using buildah push with docker-archive
        IMAGE_TAR_FILE="$CHECKPOINT_DIR/${CONTAINER_ID}_image.tar"

        # Remove existing tar file if it exists
        if [ -f "$IMAGE_TAR_FILE" ]; then
            echo "Removing existing image tar file $IMAGE_TAR_FILE"
            rm -f "$IMAGE_TAR_FILE"
        fi

        echo "Saving image $IMAGE_NAME to $IMAGE_TAR_FILE"
        sudo buildah push "$IMAGE_NAME" "docker-archive:$IMAGE_TAR_FILE"
        echo "Saved image $IMAGE_NAME to $IMAGE_TAR_FILE"
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
    local SSH_KEY="/vagrant/.vagrant/machines/master/parallels/private_key"  # Update this path as necessary

    echo "=== Transferring Images and Pod Metadata to Destination Node ==="

    # Rsync command to transfer image tar files, metadata, and pod inspect file with sudo on the remote
    rsync -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" -avz "$CHECKPOINT_DIR/" "$SSH_USER@$DESTINATION_NODE:$REMOTE_DIR/" --rsync-path="sudo rsync"

    echo "Images and Pod metadata transferred."
}

# ---------------------------
# Function: Destination Node - Restore Pod
# ---------------------------
restore_pod() {
    local DESTINATION_NODE="$1"
    local SSH_USER="$2"
    local REMOTE_DIR="$3"
    local SSH_KEY="/vagrant/.vagrant/machines/master/parallels/private_key"  # Ensure this path points to the correct private key

    echo "=== Restoring Pod on Destination Node ==="

    # Transfer the remote script to the destination node
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no restore_pod_remote.sh "$SSH_USER@$DESTINATION_NODE:/tmp/restore_pod_remote.sh"

    # Make sure the script is executable
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$DESTINATION_NODE" "chmod +x /tmp/restore_pod_remote.sh"

    # Execute the remote restore script on the destination node
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$DESTINATION_NODE" sudo /tmp/restore_pod_remote.sh "$REMOTE_DIR"
}

# ---------------------------
# Function: Verify Pod on Destination Node
# ---------------------------
verify_pod_on_destination() {
    local POD_NAME="$1"
    local POD_NAMESPACE="$2"
    local DESTINATION_NODE="$3"
    local SSH_USER="$4"
    local SSH_KEY="/vagrant/.vagrant/machines/master/parallels/private_key"
    local MAX_RETRIES=10  # Maximum number of retries
    local RETRY_INTERVAL=10  # Interval between retries in seconds

    echo "=== Verifying Pod '$POD_NAME' is running on Destination Node '$DESTINATION_NODE' ==="

    for ((i=1; i<=MAX_RETRIES; i++)); do
        # Fetch Pod IDs with the given name and namespace
        POD_IDS=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$DESTINATION_NODE" \
            "sudo crictl pods --name '$POD_NAME' --namespace '$POD_NAMESPACE' -q")

        if [ -z "$POD_IDS" ]; then
            echo "Attempt $i/$MAX_RETRIES: No pods found with name '$POD_NAME' in namespace '$POD_NAMESPACE' on '$DESTINATION_NODE'. Retrying in $RETRY_INTERVAL seconds..."
            sleep "$RETRY_INTERVAL"
            continue
        fi

        # Select the most recent pod
        POD_ID=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$DESTINATION_NODE" \
            "sudo crictl pods --name '$POD_NAME' --namespace '$POD_NAMESPACE' -o json" | \
            jq -r '.items[] | "\(.metadata.createdAt) \(.id)"' | \
            sort -r | head -n1 | awk '{print $2}')

        # Fetch the Pod status
        POD_STATUS=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$DESTINATION_NODE" \
            "sudo crictl inspectp '$POD_ID' | jq -r '.status.state'")

        if [ "$POD_STATUS" == "SANDBOX_READY" ]; then
            echo "Pod '$POD_NAME' with ID '$POD_ID' is running successfully on '$DESTINATION_NODE'."
            return 0
        else
            echo "Pod '$POD_NAME' with ID '$POD_ID' is not running yet (status: $POD_STATUS)."
        fi

        echo "Attempt $i/$MAX_RETRIES: Pod is not running. Retrying in $RETRY_INTERVAL seconds..."
        sleep "$RETRY_INTERVAL"
    done

    echo "Error: Pod '$POD_NAME' failed to reach the running state on '$DESTINATION_NODE' after $MAX_RETRIES attempts."
    exit 1
}

# ---------------------------
# Function: Delete Source Pod
# ---------------------------
delete_source_pod() {
    local POD_NAME="$1"
    local POD_NAMESPACE="$2"

    echo "=== Deleting Pod '$POD_NAME' from namespace '$POD_NAMESPACE' on the source node ==="

    # Fetch all Pod IDs with the given name and namespace
    POD_IDS=$(sudo crictl pods --name "$POD_NAME" --namespace "$POD_NAMESPACE" -q)

    if [ -z "$POD_IDS" ]; then
        echo "Error: No pods found with name '$POD_NAME' in namespace '$POD_NAMESPACE' on source."
        exit 1
    fi

    # Select the pod to delete (the one we migrated)
    if [ $(echo "$POD_IDS" | wc -l) -eq 1 ]; then
        POD_ID="$POD_IDS"
    else
        echo "Multiple pods found with name '$POD_NAME' in namespace '$POD_NAMESPACE'. Selecting the most recent one to delete."

        # Get the creation times of the pods and sort them
        POD_ID=$(sudo crictl pods --name "$POD_NAME" --namespace "$POD_NAMESPACE" -o json | \
            jq -r '.items[] | "\(.metadata.createdAt) \(.id)"' | \
            sort -r | head -n1 | awk '{print $2}')
    fi

    sudo crictl stopp "$POD_ID"
    sudo crictl rmp "$POD_ID"
    echo "Pod '$POD_NAME' with ID '$POD_ID' successfully deleted from namespace '$POD_NAMESPACE'."
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

# Define local and remote directories for images and metadata
CHECKPOINT_DIR="/var/lib/crio/checkpoints"
REMOTE_DIR="/var/lib/crio/restore"

# Check for required dependencies
check_dependencies

# Step 1: Select the Pod to Migrate
select_pod_to_migrate "$POD_NAME" "$POD_NAMESPACE"

# Step 2: Capture Images and Metadata on Source Node
capture_images_and_metadata "$POD_ID" "$CHECKPOINT_DIR"

# Step 3: Transfer Images and Pod Metadata to Destination Node
transfer_data "$CHECKPOINT_DIR" "$DESTINATION_NODE" "$SSH_USER" "$REMOTE_DIR"

# Step 4: Restore Pod on Destination Node
restore_pod "$DESTINATION_NODE" "$SSH_USER" "$REMOTE_DIR"

# Step 5: Verify Pod is running on Destination Node
verify_pod_on_destination "$POD_NAME" "$POD_NAMESPACE" "$DESTINATION_NODE" "$SSH_USER"

# Step 6: After verifying pod is running on destination, delete from source
delete_source_pod "$POD_NAME" "$POD_NAMESPACE"

echo "=== Pod Migration Completed Successfully ==="
