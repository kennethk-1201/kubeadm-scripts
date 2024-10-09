#!/bin/bash

set -euxo pipefail

# CRI-O packages
echo "deb http://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_$(lsb_release -rs)/ /" | sudo tee /etc/apt/sources.list.d/libcontainers.list > /dev/null
curl -L https://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_$(lsb_release -rs)/Release.key | sudo apt-key add -

# Disable Byobu if installed
sudo apt-get purge -y byobu || true

# Update package lists
sudo apt-get update

# Install necessary packages
sudo apt-get install -y \
    build-essential \
    git \
    make \
    gcc \
    protobuf-compiler \
    pkg-config \
    libseccomp-dev \
    libapparmor-dev \
    libgpgme-dev \
    btrfs-progs \
    libbtrfs-dev \
    libdevmapper-dev \
    libudev-dev \
    libassuan-dev \
    software-properties-common \
    libglib2.0-dev \
    libostree-dev \
    go-md2man \
    conntrack \
    rsync \
    criu \
    runc \
    conmon \
    cri-tools \
    tree

# Install Go
GO_TARBALL_PATH="/vagrant/go-tarball/go1.23.2.linux-arm64.tar.gz"
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf "$GO_TARBALL_PATH"
export PATH="/usr/local/go/bin:$PATH"

# Add Go path to .bashrc for persistence
echo "export PATH=/usr/local/go/bin:\$PATH" | sudo tee -a /home/vagrant/.bashrc

# Verify Go installation
go version

# Install Go gRPC plugins
export PATH="$PATH:$(go env GOPATH)/bin"
go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.30.0
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.3.0

# Create the CNI plugin directory if it does not exist
sudo mkdir -p /opt/cni/bin

# Install CNI plugins
cd /opt/cni/bin
sudo curl -L -O https://github.com/containernetworking/plugins/releases/download/v1.3.0/cni-plugins-linux-arm64-v1.3.0.tgz
sudo tar -xzvf cni-plugins-linux-arm64-v1.3.0.tgz

# Install CNI configuration
sudo mkdir -p /etc/cni/net.d
cat <<EOF | sudo tee /etc/cni/net.d/10-bridge.conf
{
  "cniVersion": "0.3.1",
  "name": "bridge",
  "type": "bridge",
  "bridge": "cni0",
  "isGateway": true,
  "ipMasq": true,
  "ipam": {
    "type": "host-local",
    "ranges": [
      [{"subnet": "10.244.0.0/16"}]
    ],
    "routes": [{"dst": "0.0.0.0/0"}]
  }
}
EOF

# Define policy for image pulling
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

# Define containers registries configuration
cat <<EOF | sudo tee /etc/containers/registries.conf
unqualified-search-registries = ["docker.io"]
EOF

# Build and install CRI-O from local repository
cd "/home/vagrant/cri-o"
make
sudo make install

# Configure CRI-O
sudo mkdir -p /etc/crio
sudo crio config | sudo tee /etc/crio/crio.conf

# Explicitly set runc as the default runtime in crio.conf
sudo sed -i '/\[crio.runtime\]/a\default_runtime = "runc"' /etc/crio/crio.conf

# Remove the crun runtime configuration if present
sudo sed -i '/\[crio.runtime.runtimes.crun\]/,+3d' /etc/crio/crio.conf

# Add runc runtime configuration to crio.conf, if not already present
sudo tee -a /etc/crio/crio.conf <<EOL

[crio.runtime.runtimes.runc]
runtime_path = "/usr/sbin/runc"
runtime_type = "oci"
runtime_root = "/run/runc"
EOL

# Enable CRIU support in CRI-O
sudo sed -i 's/^# enable_criu_support = false/enable_criu_support = true/' /etc/crio/crio.conf

# Enable and start CRI-O service
sudo systemctl daemon-reload
sudo systemctl enable --now crio

# Adjust socket permissions
sudo groupadd -f crio
sudo usermod -aG crio "$USER"
