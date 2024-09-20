#!/bin/bash
set -e

REMOTE_DIR="$1"
IMAGE_REGISTRY="$2"
CRI_SOCK="/var/run/crio/crio.sock"

echo "Using REMOTE_DIR: $REMOTE_DIR"
echo "Using IMAGE_REGISTRY: $IMAGE_REGISTRY"

# Ensure necessary tools are installed
for cmd in crictl jq; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Error: $cmd is not installed on the destination node."
        exit 1
    fi
done

# Parse PodSandboxConfig from pod_inspect.json
echo "=== Parsing PodSandboxConfig ==="
POD_SANDBOX_CONFIG=$(jq '.status' "$REMOTE_DIR/pod_inspect.json")
echo "PodSandboxConfig extracted."

# RunPodSandbox via crictl
echo "=== Running New PodSandbox ==="

# Define the pod config JSON file path
POD_CONFIG_FILE="$REMOTE_DIR/pod-config.json"

# Extract relevant metadata and check for null values
POD_NAME=$(echo "$POD_SANDBOX_CONFIG" | jq -r '.metadata.name // empty')
POD_NAMESPACE=$(echo "$POD_SANDBOX_CONFIG" | jq -r '.metadata.namespace // empty')
POD_UID=$(echo "$POD_SANDBOX_CONFIG" | jq -r '.metadata.uid // empty')

echo "Pod name: $POD_NAME"
echo "Pod namespace: $POD_NAMESPACE"
echo "Pod UID: $POD_UID"

if [ -z "$POD_NAME" ] || [ -z "$POD_NAMESPACE" ] || [ -z "$POD_UID" ]; then
    echo "Error: Missing required PodSandbox metadata (name, namespace, or uid)"
    exit 1
fi

# Generate the PodSandbox config file
cat <<EOF > "$POD_CONFIG_FILE"
{
    "metadata": {
        "name": "$POD_NAME",
        "namespace": "$POD_NAMESPACE",
        "attempt": 1,
        "uid": "$POD_UID"
    },
    "log_directory": "/tmp",
    "linux": {}
}
EOF

echo "PodSandbox configuration saved to $POD_CONFIG_FILE"

# Use crictl to run the PodSandbox
POD_SANDBOX_ID=$(crictl runp "$POD_CONFIG_FILE")
echo "New PodSandbox ID: $POD_SANDBOX_ID"

LIST_PODS=$(crictl pods -q)
echo "List of Pods: $LIST_PODS"

echo "=== Restoring Containers ==="