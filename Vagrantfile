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
    master.vm.synced_folder "../kubernetes", "/vm/kubernetes"
    master.vm.synced_folder "../cri-o", "/vm/checkpoint/cri-o", create: true
    master.vm.provision "common-setup", type: "shell", path: "setup/common.sh"
    master.vm.provision "master-setup", type: "shell", path: "setup/master.sh"
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
      node.vm.synced_folder "../kubernetes", "/vm/kubernetes"
      node.vm.synced_folder "../cri-o", "/vm/checkpoint/cri-o", create: true
      node.vm.provision "common-setup", type: "shell", path: "setup/common.sh"
      node.vm.provision "register-node", type: "shell", path: "setup/register.sh"
    end
  end

  # If parallel execution is absolutely needed, handle externally or rethink approach
  config.vm.post_up_message = "VMs setup completed. Please start worker nodes manually if necessary."
end
