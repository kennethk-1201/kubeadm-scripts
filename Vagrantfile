# Vagrantfile

Vagrant.configure("2") do |config|
  # Define the first node (node1)
  config.vm.define "node1" do |node|
    node.vm.box = "bento/ubuntu-22.04"
    node.vm.hostname = "node1"
    node.vm.network "private_network", ip: "10.0.0.10"
    node.vm.provider "parallels" do |prl|
      prl.memory = 4096
      prl.cpus = 2
    end

    # Sync necessary folders
    node.vm.synced_folder "../cri-o", "/home/vagrant/cri-o", type: "rsync"
    node.vm.synced_folder "../cri-api", "/home/vagrant/cri-api", type: "rsync"
    node.vm.synced_folder "setup", "/vagrant/setup"
    node.vm.synced_folder "go-tarball", "/vagrant/go-tarball", create: true
    node.vm.synced_folder "migration", "/home/vagrant/migration", type: "rsync"

    # Provision script
    node.vm.provision "shell", path: "setup/common.sh"
  end

  # Define the second node (node2)
  config.vm.define "node2" do |node|
    node.vm.box = "bento/ubuntu-22.04"
    node.vm.hostname = "node2"
    node.vm.network "private_network", ip: "10.0.0.11"
    node.vm.provider "parallels" do |prl|
      prl.memory = 4096
      prl.cpus = 2
    end

    # Sync necessary folders
    node.vm.synced_folder "../cri-o", "/home/vagrant/cri-o", type: "rsync"
    node.vm.synced_folder "../cri-api", "/home/vagrant/cri-api", type: "rsync"
    node.vm.synced_folder "setup", "/vagrant/setup"
    node.vm.synced_folder "go-tarball", "/vagrant/go-tarball", create: true
    node.vm.synced_folder "migration", "/home/vagrant/migration", type: "rsync"

    # Provision script
    node.vm.provision "shell", path: "setup/common.sh"
  end
end
