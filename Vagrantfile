# User-configurable option
INSTALL_K8S = false

Vagrant.configure("2") do |config|
  config.vm.provision "shell", inline: <<-SHELL
      apt-get update -y
      echo "10.0.0.10  master-node" >> /etc/hosts
      echo "10.0.0.11  worker-node01" >> /etc/hosts
      echo "10.0.0.12  worker-node02" >> /etc/hosts
  SHELL

  # Define the master node
  config.vm.define "master" do |master|
    master.vm.box = "bento/ubuntu-22.04"
    master.vm.hostname = "master-node"
    master.vm.network "private_network", ip: "10.0.0.10"
    master.vm.provider "parallels" do |prl|
      prl.memory = 4048
      prl.cpus = 2
    end

    # Sync the directory containing the Go tarball
    master.vm.synced_folder "go-tarball", "/vm/go-tarball", create: true

    # Other synced folders
    master.vm.synced_folder "../kubernetes", "/vm/kubernetes"
    master.vm.synced_folder "../cri-o", "/vm/checkpoint/cri-o", create: true
    master.vm.synced_folder "migration", "/vm/migration", create: true

    # Provision common setup
    master.vm.provision "common-setup", type: "shell", path: "setup/common.sh", env: { 'INSTALL_K8S' => INSTALL_K8S.to_s }
    master.vm.provision "go-move", type: "shell", inline: <<-SHELL
      # Move the Go tarball to the desired location
      mv /vm/go-tarball/go1.23.2.linux-arm64.tar.gz /vm/go1.23.2.linux-arm64.tar.gz
    SHELL
    master.vm.provision "master-setup", type: "shell", path: "setup/master.sh", env: { 'INSTALL_K8S' => INSTALL_K8S.to_s }
  end

  # Define worker nodes
  (1..2).each do |i|
    config.vm.define "worker-node0#{i}", autostart: false do |node|
      node.vm.box = "bento/ubuntu-22.04"
      node.vm.hostname = "worker-node0#{i}"
      node.vm.network "private_network", ip: "10.0.0.1#{i}"
      node.vm.provider "parallels" do |prl|
        prl.memory = 2048
        prl.cpus = 1
      end

      # Sync the directory containing the Go tarball
      node.vm.synced_folder "go-tarball", "/vm/go-tarball", create: true

      # Other synced folders
      node.vm.synced_folder "../kubernetes", "/vm/kubernetes"
      node.vm.synced_folder "../cri-o", "/vm/checkpoint/cri-o", create: true
      node.vm.synced_folder "migration", "/vm/migration", create: true

      # Provision common setup
      node.vm.provision "common-setup", type: "shell", path: "setup/common.sh", env: { 'INSTALL_K8S' => INSTALL_K8S.to_s }
      node.vm.provision "go-move", type: "shell", inline: <<-SHELL
        # Move the Go tarball to the desired location
        mv /vm/go-tarball/go1.23.2.linux-arm64.tar.gz /vm/go1.23.2.linux-arm64.tar.gz
      SHELL
      node.vm.provision "register-node", type: "shell", path: "setup/register.sh", env: { 'INSTALL_K8S' => INSTALL_K8S.to_s }
    end
  end

  # If parallel execution is absolutely needed, handle externally or rethink approach
  config.vm.post_up_message = "VMs setup completed. Please start worker nodes manually if necessary."
end
