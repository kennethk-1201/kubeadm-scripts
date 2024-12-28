#!/bin/bash
#
# Setup for Control Plane (Master) servers
set -euxo pipefail

# If you need public access to API server using the servers Public IP adress, change PUBLIC_IP_ACCESS to true.
IPADDR="10.0.0.10"
PUBLIC_IP_ACCESS="false"
NODENAME=$(hostname -s)
POD_CIDR="192.168.0.0/16"
SERVICE_CIDR="172.16.0.0/16"
CONTAINER_RUNTIME_ENDPOINT="unix:///var/run/crio/crio.sock"

sudo mkdir /etc/kubernetes

# Create the kubeadm-config.yaml configuration file
cat <<EOF | sudo tee /etc/kubernetes/kubeadm-config.yaml
# kubeadm-config.yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
serverTLSBootstrap: true
featureGates:
  ContainerCheckpoint: true
---
apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
kubernetesVersion: v1.31.0
apiServer:
  certSANs:
    - $IPADDR
  extraArgs:
    feature-gates: "ContainerCheckpoint=true"
controllerManager:
  extraArgs:
    feature-gates: "ContainerCheckpoint=true"
scheduler:
  extraArgs:
    feature-gates: "ContainerCheckpoint=true"
networking:
  serviceSubnet: $SERVICE_CIDR
  podSubnet: $POD_CIDR
---
apiVersion: kubeadm.k8s.io/v1beta3
kind: InitConfiguration
localAPIEndpoint:
  advertiseAddress: $IPADDR
  bindPort: 6443
nodeRegistration:
  criSocket: "unix:///var/run/crio/crio.sock"
---
EOF

# Pull required images (api-server, scheduler, etcd and controller manager)
sudo kubeadm config images pull

# Initialize K8s using kubeadm
if [[ "$PUBLIC_IP_ACCESS" == "false" ]]; then

    MASTER_PRIVATE_IP="10.0.0.10"
    sudo kubeadm init  --config=/etc/kubernetes/kubeadm-config.yaml --node-name "$NODENAME" --ignore-preflight-errors Swap

elif [[ "$PUBLIC_IP_ACCESS" == "true" ]]; then

    MASTER_PUBLIC_IP=$(curl ifconfig.me && echo "")
    sudo kubeadm init  --config=/vagrant/kubernetes/kubeadm-config.yaml --control-plane-endpoint="$MASTER_PUBLIC_IP" --apiserver-cert-extra-sans="$MASTER_PUBLIC_IP" --pod-network-cidr="$POD_CIDR" --node-name "$NODENAME" --ignore-preflight-errors Swap

else
    echo "Error: MASTER_PUBLIC_IP has an invalid value: $PUBLIC_IP_ACCESS"
    exit 1
fi

# Configure kubeconfig
mkdir -p "$HOME"/.kube
sudo cp -i /etc/kubernetes/admin.conf "$HOME"/.kube/config
sudo chown "$(id -u)":"$(id -g)" "$HOME"/.kube/config

# Install Calico Network Plugin Network
kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml

# Start metrics server
kubectl apply -f https://raw.githubusercontent.com/techiescamp/kubeadm-scripts/main/manifests/metrics-server.yaml

# Store registration command for worker nodes to use
sudo kubeadm token create --print-join-command > /vagrant/setup.sh
chmod 700 /vagrant/setup.sh

# Update host to use kubectl
sudo cp /etc/kubernetes/admin.conf .kube/config
sudo chmod 777 .kube/config

# Create cluster permissions for checkpointing
kubectl apply -f /vagrant/manifests/checkpointclusterrole.yaml
kubectl apply -f /vagrant/manifests/checkpointrolebinding.yaml
