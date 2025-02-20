#!/bin/bash

set -euxo pipefail

# ------------------------------------------------------------------------------
# 1. INSTALL PRE-REQUISITES
# ------------------------------------------------------------------------------
echo "deb http://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_$(lsb_release -rs)/ /" \
  | sudo tee /etc/apt/sources.list.d/libcontainers.list > /dev/null

curl -L https://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_$(lsb_release -rs)/Release.key \
  | sudo apt-key add -

sudo apt-get purge -y byobu || true
sudo apt-get update -y
sudo apt-get install -y \
  build-essential git make gcc protobuf-compiler pkg-config \
  libseccomp-dev libapparmor-dev libgpgme-dev btrfs-progs libbtrfs-dev \
  libdevmapper-dev libudev-dev libassuan-dev software-properties-common \
  libglib2.0-dev libostree-dev go-md2man conntrack rsync criu runc \
  conmon cri-tools tree buildah podman skopeo

# ------------------------------------------------------------------------------
# 2. CONFIGURE BUILD REGISTRIES (FOR BUILD & PULL)
# ------------------------------------------------------------------------------
sudo mkdir -p /etc/containers
sudo tee /etc/containers/registries.conf <<EOF
unqualified-search-registries = ["docker.io", "quay.io", "gcr.io", "registry.k8s.io"]
EOF

# ------------------------------------------------------------------------------
# 3. INSTALL GO
# ------------------------------------------------------------------------------
GO_TARBALL_PATH="/vagrant/go-tarball/go1.23.2.linux-arm64.tar.gz"
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf "$GO_TARBALL_PATH"
export PATH="/usr/local/go/bin:$PATH"
echo 'export PATH=/usr/local/go/bin:$PATH' | sudo tee -a /home/vagrant/.bashrc
go version
export PATH="$PATH:$(go env GOPATH)/bin"

# Install protobuf/grpc tools (optional)
go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.30.0
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.3.0

# ------------------------------------------------------------------------------
# 4. INSTALL CNI PLUGINS
# ------------------------------------------------------------------------------
sudo mkdir -p /opt/cni/bin
cd /opt/cni/bin
sudo curl -L -O https://github.com/containernetworking/plugins/releases/download/v1.3.0/cni-plugins-linux-arm64-v1.3.0.tgz
sudo tar -xzf cni-plugins-linux-arm64-v1.3.0.tgz
sudo rm cni-plugins-linux-arm64-v1.3.0.tgz

# ------------------------------------------------------------------------------
# 5. INSTALL & CONFIGURE CRI-O
# ------------------------------------------------------------------------------
cd /home/vagrant/cri-o
make
sudo make install

# ✅ Ensure CRI-O is properly installed before proceeding
if ! command -v crio &> /dev/null; then
    echo "ERROR: CRI-O installation failed. Exiting."
    exit 1
fi

sudo mkdir -p /etc/crio
sudo crio config | sudo tee /etc/crio/crio.conf
sudo sed -i '/\[crio.runtime\]/a\default_runtime = "runc"' /etc/crio/crio.conf
sudo sed -i '/\[crio.runtime.runtimes.crun\]/,+3d' /etc/crio/crio.conf
sudo tee -a /etc/crio/crio.conf <<EOL

[crio.runtime.runtimes.runc]
runtime_path = "/usr/sbin/runc"
runtime_type = "oci"
runtime_root = "/run/runc"
EOL

# Enable CRIU support
sudo sed -i 's/^# enable_criu_support = false/enable_criu_support = true/' /etc/crio/crio.conf

# ✅ Fix crio.service restart logic
sudo systemctl daemon-reload
if systemctl list-unit-files --type=service | grep -q "^crio.service"; then
    echo "CRI-O service found. Enabling and starting..."
    sudo systemctl enable --now crio
else
    echo "WARNING: CRI-O service not found. Skipping enable/start."
fi

sudo groupadd -f crio
sudo usermod -aG crio "$USER"

# ------------------------------------------------------------------------------
# 6. INSTALL KUBELET, KUBEADM, KUBECTL
# ------------------------------------------------------------------------------
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl

# For Kubernetes official packages
sudo mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.31/deb/Release.key \
  | sudo gpg --dearmor --batch --yes -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.31/deb/ /" \
  | sudo tee /etc/apt/sources.list.d/kubernetes.list

sudo apt-get update
sudo apt-get install -y kubeadm kubectl kubelet

# ------------------------------------------------------------------------------
# 7. OVERWRITE KUBELET WITH LOCALLY BUILT BINARY (OPTIONAL)
# ------------------------------------------------------------------------------
cd /home/vagrant/kubernetes
export KUBE_GIT_VERSION="v1.31.0"
export KUBE_GIT_COMMIT="$(git rev-parse HEAD)"
export KUBE_GIT_TREE_STATE="clean"
make WHAT=cmd/kubelet
sudo cp _output/bin/kubelet /usr/bin/kubelet
sudo cp _output/bin/kubelet /usr/local/bin/kubelet
sudo cp _output/bin/kubelet /vagrant/kubelet

# Ensure we’re actually using /usr/local/bin/kubelet in service
sudo sed -i 's|ExecStart=.*|ExecStart=/usr/local/bin/kubelet --config=/var/lib/kubelet/config.yaml --container-runtime-endpoint=unix:///var/run/crio/crio.sock|' \
  /lib/systemd/system/kubelet.service
sudo systemctl daemon-reload
sudo systemctl enable kubelet
sudo systemctl restart kubelet

# ------------------------------------------------------------------------------
# 8. COMMON POST-INSTALL
# ------------------------------------------------------------------------------
sudo mkdir -p /etc/containers
cat <<EOF | sudo tee /etc/containers/policy.json
{
  "default": [
    {
      "type": "insecureAcceptAnything"
    }
  ]
}
EOF

echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
sudo swapoff -a
sudo sed -i '/swap/d' /etc/fstab

echo "common.sh completed successfully!"

# ------------------------------------------------------------------------------
# 9. OPTIONAL: AUTO-LOAD MASTER KUBECONFIG
# ------------------------------------------------------------------------------
export KUBECONFIG=/vagrant/admin.conf
