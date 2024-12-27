set -euxo pipefail

# Variables
export PATH="$PATH:/home/vagrant/kubernetes/third_party/etcd"
export OS="xUbuntu_22.04"
export VERSION="1.30"
export CONFIG_FILE="/etc/crio/crio.conf.d/10-crio.conf"
export KUBERNETES_VERSION="1.31.0-1.1"
export ALLOW_PRIVILEGED=true


# Reference: https://github.com/kubernetes/community/blob/master/contributors/devel/running-locally.md

# Install Go
sudo add-apt-repository ppa:longsleep/golang-backports -y
sudo apt update
sudo apt install golang-go -y
export PATH="$GOPATH/src/k8s.io/kubernetes/third_party/etcd:${PATH}"

# Clone k8s
git clone https://github.com/kennethk-1201/kubernetes.git

# Install CFSSL
go install github.com/cloudflare/cfssl/cmd/...@latest

# Install etcd
cd kubernetes
sudo ./hack/install-etcd.sh

sudo swapoff -a

# keeps the swap off during reboot
(crontab -l 2>/dev/null; echo "@reboot /sbin/swapoff -a") | crontab - || true
sudo apt-get update -y

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
sudo apt-get install cri-o runc software-properties-common jq apt-transport-https ca-certificates curl gpg build-essential -y
sudo apt-get install pkg-config libprotobuf-dev libprotobuf-c-dev protobuf-c-compiler protobuf-compiler python3-protobuf libnet1 libnet1-dev libnl-3-dev libcap-dev asciidoc xmlto python3-pip -y

# Install latest CRIU
git clone https://github.com/checkpoint-restore/criu.git
cd criu
sudo make SBINDIR=/usr/sbin install
cd ..

sudo setcap cap_checkpoint_restore+eip /usr/sbin/criu

# Configure CRIO
cat <<EOF | sudo tee /etc/crio/crio.conf
[crio.runtime]
default_runtime = "runc"
enable_criu_support = true
drop_infra_ctr = false
EOF

# Update the default_runtime from "crun" to "runc"
sudo sed -i 's/default_runtime = "crun"/default_runtime = "runc"/' "$CONFIG_FILE"
# Add the enable_criu_support option under the [crio.runtime] section
# If it already exists, it will be updated; if not, it will be added
sudo sed -i '/\[crio.runtime\]/a enable_criu_support = true' "$CONFIG_FILE"

# Run CRIO
sudo systemctl daemon-reload
sudo systemctl enable --now crio

export CONTAINER_RUNTIME_ENDPOINT="unix:///var/run/crio/crio.sock"

sudo apt-get install -y kubectl="$KUBERNETES_VERSION"

# Run the command below to set up cluster
# sudo ./hack/local-up-cluster.sh
# kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml

# If you want to restart, run this to avoid compiling the kubernetes components
# sudo ./hack/local-up-cluster.sh -O

# SSH Command: ssh vagrant@127.0.0.1 -p 2222 (password is vagrant)