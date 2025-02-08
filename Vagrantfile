# Vagrantfile

Vagrant.configure("2") do |config|
  #------------------------------------------------------------------
  # 1. Node1 (Control Plane)
  #------------------------------------------------------------------
  config.vm.define "node1" do |node|
    node.vm.box = "bento/ubuntu-22.04"
    node.vm.hostname = "node1"
    node.vm.network "private_network", ip: "10.0.0.10"

    node.vm.provider "parallels" do |prl|
      prl.memory = 4096
      prl.cpus = 2
    end

    # Sync necessary folders (adjust paths as needed)
    node.vm.synced_folder "../cri-o",               "/home/vagrant/cri-o",                type: "rsync", rsync_auto: true
    node.vm.synced_folder "../cri-api",             "/home/vagrant/cri-api",              type: "rsync", rsync_auto: true
    node.vm.synced_folder "setup",                  "/vagrant/setup",                     rsync_auto: true
    node.vm.synced_folder "go-tarball",             "/vagrant/go-tarball", create: true,  rsync_auto: true
    node.vm.synced_folder "migration",              "/home/vagrant/migration",            type: "rsync", rsync_auto: true
    node.vm.synced_folder "kubernetes",             "/home/vagrant/kubernetes",           type: "rsync", rsync_auto: true
    node.vm.synced_folder "k8s-checkpoint-controller", "/home/vagrant/k8s-checkpoint-controller", type: "rsync", rsync_auto: true

    # Provision scripts
    # 1) Common prerequisites (CRI-O, Kubeadm, etc.)
    node.vm.provision "shell", path: "setup/common.sh"
    # 2) Master-specific initialization (kubeadm init, Calico, etc.)
    node.vm.provision "shell", path: "setup/master.sh"
  end

  #------------------------------------------------------------------
  # 2. Node2 (Worker Node)
  #------------------------------------------------------------------
  config.vm.define "node2" do |node|
    node.vm.box = "bento/ubuntu-22.04"
    node.vm.hostname = "node2"
    node.vm.network "private_network", ip: "10.0.0.11"

    node.vm.provider "parallels" do |prl|
      prl.memory = 4096
      prl.cpus = 2
    end

    # Sync necessary folders (adjust paths as needed)
    node.vm.synced_folder "../cri-o",               "/home/vagrant/cri-o",                type: "rsync", rsync_auto: true
    node.vm.synced_folder "../cri-api",             "/home/vagrant/cri-api",              type: "rsync", rsync_auto: true
    node.vm.synced_folder "setup",                  "/vagrant/setup",                     rsync_auto: true
    node.vm.synced_folder "go-tarball",             "/vagrant/go-tarball", create: true,  rsync_auto: true
    node.vm.synced_folder "migration",              "/home/vagrant/migration",            type: "rsync", rsync_auto: true
    node.vm.synced_folder "kubernetes",             "/home/vagrant/kubernetes",           type: "rsync", rsync_auto: true
    node.vm.synced_folder "k8s-checkpoint-controller", "/home/vagrant/k8s-checkpoint-controller", type: "rsync", rsync_auto: true

    # Provision script (common prerequisites only)
    node.vm.provision "shell", path: "setup/common.sh"

    # OPTIONAL: Auto-join node2 if /vagrant/setup.sh exists
    node.vm.provision "shell", inline: <<-SHELL
      if [ -f /vagrant/setup.sh ]; then
        echo "[node2] Joining the cluster..."
        sudo bash /vagrant/setup.sh
      else
        echo "[node2] /vagrant/setup.sh not found. Please join manually."
      fi
    SHELL
  end
end
