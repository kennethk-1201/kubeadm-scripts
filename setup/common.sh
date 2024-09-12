#!/bin/bash
#
# Common setup for all servers (Control Plane and Nodes)

set -euo pipefail

ADVERTISE_ADDRESS="10.0.0.10"
KUBERNETES_VERSION="1.31.0-1.1"
CONFIG_FILE="/etc/crio/crio.conf.d/10-crio.conf"

# Disable swap - Kubernetes does not support swap memory
sudo swapoff -a
echo "@reboot /sbin/swapoff -a" | sudo tee -a /var/spool/cron/crontabs/root > /dev/null

# Networking prerequisites
echo -e "overlay\nbr_netfilter" | sudo tee /etc/modules-load.d/k8s.conf > /dev/null
sudo modprobe overlay br_netfilter

# Apply sysctl params without reboot for networking
sudo tee /etc/sysctl.d/k8s.conf > /dev/null <<EOF
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
EOF
sudo sysctl --system

# Configure package repositories and keys
sudo mkdir -p -m 755 /etc/apt/keyrings

# Kubernetes packages
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.31/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.31/deb/ /" | sudo tee /etc/apt/sources.list.d/kubernetes.list > /dev/null

# CRI-O packages
echo "deb http://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_$(lsb_release -rs)/ /" | sudo tee /etc/apt/sources.list.d/libcontainers.list > /dev/null
curl -L https://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_$(lsb_release -rs)/Release.key | sudo apt-key add -

# Update and install all necessary packages in one go
sudo apt-get update
sudo apt-get install -y socat conntrack libbtrfs-dev containers-common git libassuan-dev libglib2.0-dev libc6-dev libgpgme-dev libgpg-error-dev libseccomp-dev libsystemd-dev libselinux1-dev pkg-config go-md2man cri-o-runc libudev-dev software-properties-common gcc make runc jq criu golang-go kubectl="$KUBERNETES_VERSION" kubeadm="$KUBERNETES_VERSION"

# Install conmon
git clone https://github.com/containers/conmon
cd conmon
make
sudo make install
cd ..

# Build and install CRI-O from source
cd /vm/checkpoint/cri-o
go mod vendor
make
sudo make install
cd ..

# Configure CRI-O
sudo tee /etc/crio/crio.conf > /dev/null <<EOF
[crio.runtime]
default_runtime = "runc"
enable_criu_support = true
drop_infra_ctr = false
[crio.runtime.runtimes.runc]
runtime_path = "/usr/sbin/runc"
runtime_type = "oci"
EOF

# Build kubelet from source if necessary
cd /vm/kubernetes
make all WHAT=cmd/kubelet
sudo cp /vm/kubernetes/_output/bin/kubelet /usr/bin/kubelet

# Configure basic kubelet service file for all nodes
sudo tee /etc/systemd/system/kubelet.service > /dev/null <<EOF
[Unit]
Description=kubelet: The Kubernetes Node Agent
Documentation=https://kubernetes.io/docs/home/
Wants=network-online.target
After=network-online.target

[Service]
ExecStart=/usr/bin/kubelet --config=/etc/kubernetes/kubelet-basic-config.yaml
Restart=always
StartLimitInterval=0
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start CRI-O and kubelet services
sudo systemctl daemon-reload
sudo systemctl enable --now crio
sudo systemctl enable --now kubelet

# Set local IP for kubelet
local_ip="$(ip --json addr show eth0 | jq -r '.[0].addr_info[] | select(.family == "inet") | .local')"
sudo tee /etc/default/kubelet > /dev/null <<EOF
KUBELET_EXTRA_ARGS=--node-ip=$local_ip
EOF

# Reload and restart the kubelet service to apply changes
sudo systemctl restart kubelet

echo "CRI runtime and Kubernetes installed successfully"
