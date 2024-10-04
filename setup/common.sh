#!/bin/bash

set -euo pipefail

# Check if INSTALL_K8S is set; default to false if not provided
INSTALL_K8S="${INSTALL_K8S:-false}"

ADVERTISE_ADDRESS="10.0.0.10"
KUBERNETES_VERSION="1.31.0-1.1"
CONFIG_FILE="/etc/crio/crio.conf.d/10-crio.conf"

# Disable swap if Kubernetes is being installed
if [ "$INSTALL_K8S" = "true" ]; then
    sudo swapoff -a
    echo "@reboot /sbin/swapoff -a" | sudo tee -a /var/spool/cron/crontabs/root > /dev/null
fi

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

if [ "$INSTALL_K8S" = "true" ]; then
    # Kubernetes packages
    curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.31/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.31/deb/ /" | sudo tee /etc/apt/sources.list.d/kubernetes.list > /dev/null
fi

# CRI-O packages
echo "deb http://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_$(lsb_release -rs)/ /" | sudo tee /etc/apt/sources.list.d/libcontainers.list > /dev/null
curl -L https://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_$(lsb_release -rs)/Release.key | sudo apt-key add -

# Update and install necessary packages
sudo apt-get update

# Common packages
sudo apt-get install -y buildah socat conntrack libbtrfs-dev git \
libassuan-dev libglib2.0-dev libc6-dev libgpgme-dev libgpg-error-dev libseccomp-dev \
libsystemd-dev libselinux1-dev pkg-config go-md2man libudev-dev software-properties-common \
gcc make runc jq criu rsync openssh-client openssh-server etcd

# Install Kubernetes packages if required
if [ "$INSTALL_K8S" = "true" ]; then
    sudo apt-get install -y kubectl="$KUBERNETES_VERSION" kubeadm="$KUBERNETES_VERSION" cri-o-runc
fi

# Remove any existing Go installation
sudo rm -rf /usr/local/go

# Extract the Go tarball into /usr/local
sudo tar -C /usr/local -xzf /vm/go-tarball/go1.23.2.linux-arm64.tar.gz

# Set permissions for the Go directory
sudo chown -R root:root /usr/local/go
sudo chmod -R a+rX /usr/local/go

# Update PATH for the current session
export PATH=$PATH:/usr/local/go/bin

# Persist the PATH update for the vagrant user
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc

# Verify Go installation
go version

# Install additional dependencies
sudo apt-get update
sudo apt-get install -y cri-tools

# Install conmon
git clone https://github.com/containers/conmon
cd conmon
make
sudo make install
cd ..

# Build and install CRI-O from source
cd /vm/checkpoint/cri-o
go mod tidy
go mod vendor
make
if [ $? -ne 0 ]; then
    echo "Error during 'make' for CRI-O. Exiting."
    exit 1
fi

sudo make install
if [ $? -ne 0 ]; then
    echo "Error during 'make install' for CRI-O. Exiting."
    exit 1
fi
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
[crio.network]
network_dir = "/etc/cni/net.d/"
plugin_dirs = [
    "/opt/cni/bin/"
]
EOF

# Enable and start etcd for Calico
sudo systemctl enable etcd
sudo systemctl restart etcd

# Install Calico CNI plugins
CNI_VERSION="v1.1.1"
curl -LO https://github.com/containernetworking/plugins/releases/download/$CNI_VERSION/cni-plugins-linux-arm64-$CNI_VERSION.tgz
sudo mkdir -p /opt/cni/bin
sudo tar -C /opt/cni/bin -xzf cni-plugins-linux-arm64-$CNI_VERSION.tgz

# Install Calicoctl
curl -L -o calicoctl https://github.com/projectcalico/calico/releases/download/v3.28.2/calicoctl-linux-arm64
chmod +x calicoctl
sudo mv calicoctl /usr/local/bin/

# Configure Calicoctl to use etcd
sudo mkdir -p /etc/calico
sudo tee /etc/calico/calicoctl.cfg > /dev/null <<EOF
apiVersion: projectcalico.org/v3
kind: CalicoAPIConfig
metadata:
spec:
  datastoreType: "etcdv3"
  etcdEndpoints: "http://127.0.0.1:2379"
EOF
echo 'export CALICOCTL_CONFIG=/etc/calico/calicoctl.cfg' | sudo tee -a ~/.bashrc
source ~/.bashrc

# Enable and start CRI-O service
sudo systemctl daemon-reload
sudo systemctl enable --now crio

echo "Setup completed. Kubernetes installation status: $INSTALL_K8S"
