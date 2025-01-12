#!/bin/bash

set -euxo pipefail

# Enable IP forwarding and bridge netfilter
sudo modprobe br_netfilter
echo "1" | sudo tee /proc/sys/net/bridge/bridge-nf-call-iptables
echo "1" | sudo tee /proc/sys/net/ipv4/ip_forward

# Initialize kubeadm
sudo kubeadm init --pod-network-cidr=10.244.0.0/16 --apiserver-advertise-address=$(hostname -I | awk '{print $1}')

# Set up kubeconfig for vagrant user
mkdir -p /home/vagrant/.kube
sudo cp -i /etc/kubernetes/admin.conf /home/vagrant/.kube/config
sudo chown $(id -u vagrant):$(id -g vagrant) /home/vagrant/.kube/config

# Apply CNI Plugin
kubectl apply -f https://raw.githubusercontent.com/flannel-io/flannel/master/Documentation/kube-flannel.yml

# Generate join command and save it
kubeadm token create --print-join-command > /vagrant/setup/join.sh
chmod +x /vagrant/setup/join.sh