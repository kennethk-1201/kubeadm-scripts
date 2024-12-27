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

# keeps the swap off during reboot
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

# Prevent script interruption
sudo sed -i "/#\$nrconf{restart} = 'i';/s/.*/\$nrconf{restart} = 'a';/" /etc/needrestart/needrestart.conf

# Install dependencies
sudo apt-get update -y
sudo apt-get install conntrack cri-o runc software-properties-common jq apt-transport-https ca-certificates curl gpg make build-essential -y

# Install CRIU
git clone https://github.com/checkpoint-restore/criu.git
sudo apt-get update -y
sudo apt-get install pkg-config libprotobuf-dev libprotobuf-c-dev protobuf-c-compiler protobuf-compiler python3-protobuf libnet1 libnet1-dev libnl-3-dev libcap-dev asciidoc xmlto python3-pip -y
cd criu
sudo make SBINDIR=/usr/sbin install
cd ..

sudo setcap cap_checkpoint_restore+eip /usr/sbin/criu

# Get keys to install kubectl and kubeadm.
sudo apt-get update -y
sudo apt-get install -y kubectl="$KUBERNETES_VERSION" kubeadm="$KUBERNETES_VERSION"
sudo apt-get update -y
sudo apt-mark hold cri-o kubeadm kubectl

# Build kubelet from source code
git clone https://github.com/kennethk-1201/kubernetes.git
cd kubernetes
sudo git config --global --add safe.directory /home/vagrant/kubernetes
sudo make clean
sudo git tag v1.31.0-1.1
sudo make WHAT=cmd/kubelet
sudo cp _output/bin/kubelet /usr/bin/kubelet
sudo cp _output/bin/kubelet /usr/local/bin/kubelet
cd ..

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
sudo sed -i 's/default_runtime = "crun"/default_runtime = "runc"/' "$CONFIG_FILE"
# Add the enable_criu_support option under the [crio.runtime] section
# If it already exists, it will be updated; if not, it will be added
sudo sed -i '/\[crio.runtime\]/a enable_criu_support = true' "$CONFIG_FILE"

# Start CRIO
sudo systemctl daemon-reload
sudo systemctl enable --now crio

echo "CRI runtime installed susccessfully"

# Update kubelet config
local_ip=$NODE_IP
cat > /etc/default/kubelet << EOF
KUBELET_EXTRA_ARGS=--node-ip=$local_ip
EOF

# Install CNI
CNI_PLUGINS_VERSION="v1.3.0"
ARCH="amd64"
DEST="/opt/cni/bin"
sudo mkdir -p "$DEST"
curl -L "https://github.com/containernetworking/plugins/releases/download/${CNI_PLUGINS_VERSION}/cni-plugins-linux-${ARCH}-${CNI_PLUGINS_VERSION}.tgz" | sudo tar -C "$DEST" -xz

# Install crictl (for debugging)
DOWNLOAD_DIR="/usr/local/bin"
sudo mkdir -p "$DOWNLOAD_DIR"
CRICTL_VERSION="v1.31.0"
ARCH="amd64"
curl -L "https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRICTL_VERSION}/crictl-${CRICTL_VERSION}-linux-${ARCH}.tar.gz" | sudo tar -C $DOWNLOAD_DIR -xz

# Create kubelet systemd service
RELEASE_VERSION="v0.16.2"
curl -sSL "https://raw.githubusercontent.com/kubernetes/release/${RELEASE_VERSION}/cmd/krel/templates/latest/kubelet/kubelet.service" | sed "s:/usr/bin:${DOWNLOAD_DIR}:g" | sudo tee /usr/lib/systemd/system/kubelet.service
sudo mkdir -p /usr/lib/systemd/system/kubelet.service.d
curl -sSL "https://raw.githubusercontent.com/kubernetes/release/${RELEASE_VERSION}/cmd/krel/templates/latest/kubeadm/10-kubeadm.conf" | sed "s:/usr/bin:${DOWNLOAD_DIR}:g" | sudo tee /usr/lib/systemd/system/kubelet.service.d/10-kubeadm.conf

sudo systemctl enable --now kubelet