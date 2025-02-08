#!/bin/bash
#
# master.sh - Setup for Control Plane (Master) node

set -euxo pipefail

# ------------------------------------------------------------------------------
# 1. KUBEADM CONFIG
# ------------------------------------------------------------------------------
sudo mkdir -p /etc/kubernetes

cat <<EOF | sudo tee /etc/kubernetes/kubeadm-config.yaml
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

# ------------------------------------------------------------------------------
# 2. INIT THE CLUSTER
# ------------------------------------------------------------------------------
sudo kubeadm config images pull

NODENAME=$(hostname -s)
sudo kubeadm init \
  --config=/etc/kubernetes/kubeadm-config.yaml \
  --node-name "$NODENAME" \
  --ignore-preflight-errors Swap

# ------------------------------------------------------------------------------
# 3. POST-INSTALL SETUP
# ------------------------------------------------------------------------------
mkdir -p "$HOME/.kube"
sudo cp -i /etc/kubernetes/admin.conf "$HOME/.kube/config"
sudo chown "$(id -u)":"$(id -g)" "$HOME/.kube/config"

# Install Calico
kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml

# Install metrics-server
kubectl apply -f https://raw.githubusercontent.com/techiescamp/kubeadm-scripts/main/manifests/metrics-server.yaml

# Save join command
sudo kubeadm token create --print-join-command > /vagrant/setup.sh
chmod 700 /vagrant/setup.sh

# Remove control plane taint (optional; allows workloads on master)
sudo kubectl taint nodes --all node-role.kubernetes.io/control-plane- || true

# ------------------------------------------------------------------------------
# 4. COPY ADMIN.CONF FOR WORKERS
# ------------------------------------------------------------------------------
# This allows worker nodes to automatically pick up the master's kubeconfig
sudo cp /etc/kubernetes/admin.conf /vagrant/admin.conf
sudo chmod 644 /vagrant/admin.conf

echo "master.sh completed successfully!"
