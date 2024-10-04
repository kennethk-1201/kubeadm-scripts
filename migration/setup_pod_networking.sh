#!/bin/bash
#
# Setup pod networking using Macvlan and run a sample pod

set -euo pipefail

# Step 1: Create Macvlan CNI configuration
sudo tee /etc/cni/net.d/10-macvlan.conflist > /dev/null <<EOF
{
  "cniVersion": "0.3.1",
  "name": "macvlan-pod-network",
  "plugins": [
    {
      "type": "macvlan",
      "master": "eth0",
      "mode": "bridge",
      "ipam": {
        "type": "host-local",
        "subnet": "192.168.1.0/24",
        "rangeStart": "192.168.1.100",
        "rangeEnd": "192.168.1.200",
        "routes": [
          { "dst": "0.0.0.0/0" }
        ],
        "gateway": "192.168.1.1"
      }
    },
    {
      "type": "portmap",
      "capabilities": {
        "portMappings": true
      }
    }
  ]
}
EOF

# Step 2: Update /etc/containers/registries.conf to include Docker Hub
sudo tee /etc/containers/registries.conf > /dev/null <<EOF
unqualified-search-registries = ["docker.io"]

[[registry]]
prefix = "docker.io"
location = "registry-1.docker.io"
insecure = false
blocked = false
EOF

# Step 3: Pull the Nginx image manually using crictl
sudo crictl pull docker.io/library/nginx:latest

# Step 4: Create a sample pod configuration file
cat <<EOF > pod-config.json
{
  "metadata": {
    "name": "nginx-pod",
    "namespace": "default",
    "uid": "unique-id-12345"
  },
  "log_directory": "/var/log/pods",
  "linux": {}
}
EOF

# Step 5: Create a sample container configuration file
cat <<EOF > container-config.json
{
  "metadata": {
    "name": "nginx-container"
  },
  "image": {
    "image": "docker.io/library/nginx:latest"
  },
  "command": [
    "nginx",
    "-g",
    "daemon off;"
  ],
  "log_path": "nginx-container.log",
  "linux": {},
  "annotations": {},
  "envs": [
    {
      "key": "NGINX_PORT",
      "value": "80"
    }
  ]
}
EOF

# Step 6: Run the pod using crictl
POD_ID=$(sudo crictl runp pod-config.json)

# Step 7: Create the container within the pod
CONTAINER_ID=$(sudo crictl create "$POD_ID" container-config.json pod-config.json)

# Step 8: Start the container
sudo crictl start "$CONTAINER_ID"

# Step 9: Check the status
sudo crictl ps -a
