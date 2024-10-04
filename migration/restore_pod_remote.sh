#!/bin/bash
set -e

REMOTE_DIR="$1"

echo "Using REMOTE_DIR: $REMOTE_DIR"

# Ensure necessary tools are installed
for cmd in crictl jq buildah; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Error: $cmd is not installed on the destination node."
        exit 1
    fi
done

# Parse PodSandboxConfig from pod_inspect.json
echo "=== Parsing PodSandboxConfig ==="
POD_SANDBOX_CONFIG=$(jq '.status' "$REMOTE_DIR/pod_inspect.json")
echo "PodSandboxConfig extracted."

# Extract relevant metadata and check for null values
POD_NAME=$(echo "$POD_SANDBOX_CONFIG" | jq -r '.metadata.name // empty')
POD_NAMESPACE=$(echo "$POD_SANDBOX_CONFIG" | jq -r '.metadata.namespace // empty')
ORIGINAL_POD_UID=$(echo "$POD_SANDBOX_CONFIG" | jq -r '.metadata.uid // empty')

# Generate a new unique UID for the pod
POD_UID=$(uuidgen)
echo "Generated Pod UID: $POD_UID"

if [ -z "$POD_NAME" ] || [ -z "$POD_NAMESPACE" ] || [ -z "$POD_UID" ]; then
    echo "Error: Missing required PodSandbox metadata (name, namespace, or uid)"
    exit 1
fi

# Define the pod config JSON file
POD_CONFIG_FILE="$REMOTE_DIR/pod-config.json"

# Generate the PodSandbox config file
cat <<EOF > "$POD_CONFIG_FILE"
{
    "metadata": {
        "name": "$POD_NAME",
        "namespace": "$POD_NAMESPACE",
        "uid": "$POD_UID",
        "attempt": 1
    },
    "log_directory": "/tmp",
    "linux": {}
}
EOF

echo "PodSandbox configuration saved to $POD_CONFIG_FILE"

# Use crictl to run the PodSandbox
echo "=== Running New PodSandbox on Destination Node ==="
POD_SANDBOX_ID=$(crictl runp "$POD_CONFIG_FILE")
if [ $? -eq 0 ]; then
    echo "PodSandbox creation successful. New PodSandbox ID: $POD_SANDBOX_ID"
else
    echo "Error: Failed to create PodSandbox."
    exit 1
fi

echo "=== Restoring Containers in the New PodSandbox ==="

# Loop over each container metadata file
for CONTAINER_METADATA_FILE in "$REMOTE_DIR"/*_metadata.json; do
    ORIGINAL_CONTAINER_ID=$(basename "$CONTAINER_METADATA_FILE" _metadata.json)
    echo "Restoring container: $ORIGINAL_CONTAINER_ID"

    # Extract container config from metadata
    CONTAINER_CONFIG=$(jq '.status.config' "$CONTAINER_METADATA_FILE")

    # Extract the container name from metadata
    CONTAINER_NAME=$(echo "$CONTAINER_CONFIG" | jq -r '.metadata.name // empty')

    # If container name is empty, generate one
    if [ -z "$CONTAINER_NAME" ]; then
        CONTAINER_NAME="container_${ORIGINAL_CONTAINER_ID}"
        echo "Generated container name: $CONTAINER_NAME"
    else
        echo "Container name: $CONTAINER_NAME"
    fi

    # Update the container config
    CONTAINER_CONFIG=$(echo "$CONTAINER_CONFIG" | jq \
        --arg name "$CONTAINER_NAME" \
        '.metadata.name=$name | .metadata.attempt=1')

    # Save container config to a file
    CONTAINER_CONFIG_FILE="$REMOTE_DIR/${ORIGINAL_CONTAINER_ID}_config.json"
    echo "$CONTAINER_CONFIG" > "$CONTAINER_CONFIG_FILE"

    # Load the image tar file using buildah pull
    IMAGE_TAR_FILE="$REMOTE_DIR/${ORIGINAL_CONTAINER_ID}_image.tar"
    if [ -f "$IMAGE_TAR_FILE" ]; then
        echo "Loading image from $IMAGE_TAR_FILE"
        buildah pull "docker-archive:$IMAGE_TAR_FILE"
        # Get the image name
        IMAGE_NAME=$(buildah images --format "{{.Name}}:{{.Tag}}" | head -n 1)
        echo "Loaded image name: $IMAGE_NAME"
    else
        echo "Error: Image tar file $IMAGE_TAR_FILE not found"
        exit 1
    fi

    # Update the image field in the container config
    CONTAINER_CONFIG=$(echo "$CONTAINER_CONFIG" | jq --arg img "$IMAGE_NAME" '.image.image=$img')
    echo "$CONTAINER_CONFIG" > "$CONTAINER_CONFIG_FILE"

    # Create the container
    echo "Creating container in PodSandbox: $POD_SANDBOX_ID"
    NEW_CONTAINER_ID=$(crictl create "$POD_SANDBOX_ID" "$CONTAINER_CONFIG_FILE" "$POD_CONFIG_FILE")
    if [ $? -eq 0 ]; then
        echo "Container creation successful. Container ID: $NEW_CONTAINER_ID"
    else
        echo "Error: Failed to create container."
        exit 1
    fi

    # Start the container
    echo "Starting container: $NEW_CONTAINER_ID"
    crictl start "$NEW_CONTAINER_ID"
    if [ $? -eq 0 ]; then
        echo "Container started successfully. Container ID: $NEW_CONTAINER_ID"
    else
        echo "Error: Failed to start container."
        exit 1
    fi
done

echo "=== All containers restored successfully ==="
