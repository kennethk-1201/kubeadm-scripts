Vagrant.configure("2") do |config|
  # Define the master node
  config.vm.define "master" do |node|
    node.vm.box = "bento/ubuntu-22.04"
    node.vm.hostname = "master"
    node.vm.network "private_network", ip: "10.0.0.9"
    node.vm.provider "parallels" do |prl|
      prl.memory = 4096
      prl.cpus = 2
    end

    # Sync necessary folders
    node.vm.synced_folder "setup", "/vagrant/setup", rsync_auto: true
    node.vm.synced_folder "go-tarball", "/vagrant/go-tarball", create: true, rsync_auto: true
    node.vm.synced_folder "sample-controller", "/home/vagrant/sample-controller", type: "rsync", rsync_auto: true

    # Provision scripts
    node.vm.provision "shell", path: "setup/common.sh"
    node.vm.provision "shell", path: "setup/master.sh"
  end

  # Define worker nodes (node1 and node2)
  (1..2).each do |i|
    config.vm.define "node#{i}" do |node|
      node.vm.box = "bento/ubuntu-22.04"
      node.vm.hostname = "node#{i}"
      node.vm.network "private_network", ip: "10.0.0.#{9+i}"
      node.vm.provider "parallels" do |prl|
        prl.memory = 4096
        prl.cpus = 2
      end

      # Sync necessary folders
      node.vm.synced_folder "setup", "/vagrant/setup", rsync_auto: true
      node.vm.synced_folder "go-tarball", "/vagrant/go-tarball", create: true, rsync_auto: true
      node.vm.synced_folder "sample-controller", "/home/vagrant/sample-controller", type: "rsync", rsync_auto: true

      # Provision scripts
      node.vm.provision "shell", path: "setup/common.sh"
      node.vm.provision "shell", path: "setup/worker.sh"
    end
  end

  # Configure SSH for all machines
  config.ssh.insert_key = false
  config.ssh.forward_agent = true

  # Enable automatic rsync
  config.vm.synced_folder ".", "/vagrant", type: "rsync", rsync_auto: true
end