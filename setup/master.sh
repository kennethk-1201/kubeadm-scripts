#!/bin/bash
#
# Setup for Control Plane (Master) servers

set -euxo pipefail

# Check if INSTALL_K8S is set; default to false if not provided
INSTALL_K8S="${INSTALL_K8S:-false}"

if [ "$INSTALL_K8S" != "true" ]; then
    echo "Skipping Kubernetes master setup as INSTALL_K8S is not set to true."
    exit 0
fi

sudo mkdir -p /etc/kubernetes/

sudo apt-get update
sudo apt-get install -y socat conntrack

# Create the kubeadm-config.yaml configuration file
cat <<EOF | sudo tee /etc/kubernetes/kubeadm-config.yaml
# kubeadm-config.yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
featureGates:
  ContainerCheckpoint: true
---
apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
kubernetesVersion: v1.31.0
apiServer:
  extraArgs:
    feature-gates: "ContainerCheckpoint=true"
controllerManager:
  extraArgs:
    feature-gates: "ContainerCheckpoint=true"
scheduler:
  extraArgs:
    feature-gates: "ContainerCheckpoint=true"
networking:
  podSubnet: 192.168.0.0/16
---
apiVersion: kubeadm.k8s.io/v1beta3
kind: InitConfiguration
localAPIEndpoint:
  advertiseAddress: 10.0.0.10
  bindPort: 6443
nodeRegistration:
  criSocket: "unix:///var/run/crio/crio.sock"
EOF

PUBLIC_IP_ACCESS="false"
NODENAME=$(hostname -s)
POD_CIDR="192.168.0.0/16"

# Pull required images
sudo kubeadm config images pull

# Initialize kubeadm based on PUBLIC_IP_ACCESS
if [[ "$PUBLIC_IP_ACCESS" == "false" ]]; then
    MASTER_PRIVATE_IP="10.0.0.10"
    sudo kubeadm init --config=/etc/kubernetes/kubeadm-config.yaml --node-name "$NODENAME" --ignore-preflight-errors Swap
elif [[ "$PUBLIC_IP_ACCESS" == "true" ]]; then
    MASTER_PUBLIC_IP=$(curl ifconfig.me && echo "")
    sudo kubeadm init --config=/etc/kubernetes/kubeadm-config.yaml --control-plane-endpoint="$MASTER_PUBLIC_IP" --apiserver-cert-extra-sans="$MASTER_PUBLIC_IP" --pod-network-cidr="$POD_CIDR" --node-name "$NODENAME" --ignore-preflight-errors Swap
else
    echo "Error: PUBLIC_IP_ACCESS has an invalid value: $PUBLIC_IP_ACCESS"
    exit 1
fi

# Configure kubeconfig
mkdir -p "$HOME"/.kube
sudo cp -i /etc/kubernetes/admin.conf "$HOME"/.kube/config
sudo chown "$(id -u)":"$(id -g)" "$HOME"/.kube/config

# Install Calico Network Plugin
kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml

# Store registration command
sudo kubeadm token create --print-join-command > /vagrant/setup.sh
chmod 700 /vagrant/setup.sh
