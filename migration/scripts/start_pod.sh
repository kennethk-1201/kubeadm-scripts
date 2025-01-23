#!/bin/bash

set -euo pipefail

function usage() {
    echo "Usage: $0 [counter|http] [name] [options]"
    echo ""
    echo "Start a pod with the specified type and name"
    echo ""
    echo "Types:"
    echo "  counter    Start a counter pod that increments a number"
    echo "  http       Start an HTTP server pod"
    echo ""
    echo "Options:"
    echo "  --port     Port number for HTTP server (default: 8080)"
    echo ""
    echo "Examples:"
    echo "  $0 counter pod1"
    echo "  $0 http web1 --port 8080"
    exit 1
}

if [ "$#" -lt 2 ]; then
    usage
fi

# Ensure we're in the project root directory
cd "$(dirname "$0")/.."

POD_TYPE=$1
POD_NAME=$2
PORT=8080

# Parse additional options
shift 2
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done

# Activate virtual environment
source /home/vagrant/migration/venv/bin/activate

# Set PYTHONPATH explicitly
export PYTHONPATH="/home/vagrant"

# Create a temporary Python script
TMP_SCRIPT=$(mktemp)
trap "rm -f $TMP_SCRIPT" EXIT

if [ "$POD_TYPE" = "counter" ]; then
    cat > "$TMP_SCRIPT" << EOF
from migration.pods import CounterPod
from migration.core.manager import PodManager

pod = CounterPod(name="$POD_NAME", namespace="default")
manager = PodManager()
pod_id, container_ids = manager.create_pod_from_config(pod)
print(f"Created counter pod:")
print(f"Pod ID: {pod_id}")
print(f"Container IDs: {container_ids}")
EOF
elif [ "$POD_TYPE" = "http" ]; then
    cat > "$TMP_SCRIPT" << EOF
from migration.pods import HttpServerPod
from migration.core.manager import PodManager

pod = HttpServerPod(name="$POD_NAME", http_port=$PORT)
manager = PodManager()
pod_id, container_ids = manager.create_pod_from_config(pod)
print(f"Created HTTP server pod:")
print(f"Pod ID: {pod_id}")
print(f"Container IDs: {container_ids}")
print(f"Server running on http://localhost:$PORT")
EOF
else
    echo "Error: Invalid pod type. Must be 'counter' or 'http'"
    usage
fi

# Run the script
python3 "$TMP_SCRIPT"

# Show running pods
echo -e "\nRunning pods:"
sudo crictl pods

echo -e "\nRunning containers:"
sudo crictl ps
