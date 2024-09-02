#!/bin/bash
#
# Common setup for all servers (Control Plane and Nodes)

set -euxo pipefail

# Kuernetes Variable Declaration

ADVERTISE_ADDRESS="10.0.0.10"  # Replace with your actual IP address
KUBERNETES_VERSION="1.31.0-1.1"
CONFIG_FILE="/etc/crio/crio.conf.d/10-crio.conf"

# disable swap
sudo swapoff -a

# keeps the swaf off during reboot
(crontab -l 2>/dev/null; echo "@reboot /sbin/swapoff -a") | crontab - || true
sudo apt-get update -y

# Install CRI-O Runtime

OS="xUbuntu_22.04"

VERSION="1.30"

# Create the .conf file to load the modules at bootup
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

sudo modprobe overlay
sudo modprobe br_netfilter

# sysctl params required by setup, params persist across reboots
cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF

# Apply sysctl params without reboot
sudo sysctl --system

# Create the keyrings directory if it doesn't exist
if [ ! -d /etc/apt/keyrings ]; then
  sudo mkdir -p -m 755 /etc/apt/keyrings
fi

# Download and process the Kubernetes keyring, overwriting if necessary
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.31/deb/Release.key | sudo gpg --dearmor --batch --yes -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.31/deb/ /" | sudo tee /etc/apt/sources.list.d/kubernetes.list

# Download and process the CRI-O keyring, overwriting if necessary
curl -fsSL https://pkgs.k8s.io/addons:/cri-o:/stable:/v1.30/deb/Release.key | sudo gpg --dearmor --batch --yes -o /etc/apt/keyrings/cri-o-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/cri-o-apt-keyring.gpg] https://pkgs.k8s.io/addons:/cri-o:/stable:/v1.30/deb/ /" | sudo tee /etc/apt/sources.list.d/cri-o.list

# Install dependencies
sudo apt-get update -y
sudo apt-get install cri-o runc software-properties-common jq apt-transport-https ca-certificates curl gpg criu -y

# Get keys to install kubelet, kubectl and kubeadm.

sudo apt-get update -y
sudo apt-get install -y kubelet="$KUBERNETES_VERSION" kubectl="$KUBERNETES_VERSION" kubeadm="$KUBERNETES_VERSION"
# sudo apt-get install -y kubelet kubeadm kubectl
sudo apt-get update -y
sudo apt-mark hold cri-o kubelet kubeadm kubectl

# Configure CRI-O to use runc and enable CRIU support
cat <<EOF | sudo tee /etc/crio/crio.conf
[crio.runtime]
default_runtime = "runc"
enable_criu_support = true
drop_infra_ctr = false
EOF

# Check if the file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Configuration file not found: $CONFIG_FILE"
    exit 1
fi

# Update the default_runtime from "crun" to "runc"
sed -i 's/default_runtime = "crun"/default_runtime = "runc"/' "$CONFIG_FILE"
# Add the enable_criu_support option under the [crio.runtime] section
# If it already exists, it will be updated; if not, it will be added
sed -i '/\[crio.runtime\]/a enable_criu_support = true' "$CONFIG_FILE"

sudo systemctl daemon-reload
sudo systemctl enable --now crio

echo "CRI runtime installed susccessfully"

local_ip="$(ip --json addr show eth0 | jq -r '.[0].addr_info[] | select(.family == "inet") | .local')"
cat > /etc/default/kubelet << EOF
KUBELET_EXTRA_ARGS=--node-ip=$local_ip
EOF

# Register worker
if [ -f /vagrant/setup.sh ]; then
  sudo /vagrant/setup.sh
fi

