Vagrant.configure("2") do |config|
  # Define common configurations
  COMMON_SETTINGS = {
    box: "bento/ubuntu-22.04",
    memory: 4096,
    cpus: 2,
    network: { type: "private_network", ip_prefix: "10.0.0." },
    synced_folders: [
      ["../cri-o", "/home/vagrant/cri-o"],
      ["../cri-api", "/home/vagrant/cri-api"],
      ["setup", "/vagrant/setup"],
      ["go-tarball", "/vagrant/go-tarball", { create: true }],
      ["migration", "/home/vagrant/migration"],
      ["kubernetes", "/home/vagrant/kubernetes"],
      ["pod-migration-controller", "/home/vagrant/pod-migration-controller"],
    ]
  }

  #------------------------------------------------------------------
  # 1. Node1 (Control Plane)
  #------------------------------------------------------------------
  config.vm.define "node1" do |node|
    node.vm.box = COMMON_SETTINGS[:box]
    node.vm.hostname = "node1"
    node.vm.network COMMON_SETTINGS[:network][:type], ip: "#{COMMON_SETTINGS[:network][:ip_prefix]}10"

    node.vm.provider "parallels" do |prl|
      prl.memory = COMMON_SETTINGS[:memory]
      prl.cpus = COMMON_SETTINGS[:cpus]
    end

    # Sync necessary folders
    COMMON_SETTINGS[:synced_folders].each do |src, dest, opts|
      node.vm.synced_folder src, dest, { type: "rsync", rsync_auto: true }.merge(opts || {})
    end

    # Provision scripts
    node.vm.provision "shell", path: "setup/common.sh"  # Common setup
    node.vm.provision "shell", path: "setup/master.sh"  # Master-specific setup
  end

  #------------------------------------------------------------------
  # 2. Node2 (Worker Node)
  #------------------------------------------------------------------
  config.vm.define "node2" do |node|
    node.vm.box = COMMON_SETTINGS[:box]
    node.vm.hostname = "node2"
    node.vm.network COMMON_SETTINGS[:network][:type], ip: "#{COMMON_SETTINGS[:network][:ip_prefix]}11"

    node.vm.provider "parallels" do |prl|
      prl.memory = COMMON_SETTINGS[:memory]
      prl.cpus = COMMON_SETTINGS[:cpus]
    end

    # Sync necessary folders
    COMMON_SETTINGS[:synced_folders].each do |src, dest, opts|
      node.vm.synced_folder src, dest, { type: "rsync", rsync_auto: true }.merge(opts || {})
    end

    # Provision scripts
    node.vm.provision "shell", path: "setup/common.sh"  # Common setup

    # Auto-join cluster if setup script exists
    node.vm.provision "shell", inline: <<-SHELL
      if [ -f /vagrant/setup.sh ]; then
        echo "[node2] Joining the cluster..."
        bash /vagrant/setup.sh
      else
        echo "[node2] /vagrant/setup.sh not found. Please join manually."
      fi
    SHELL
  end
end
