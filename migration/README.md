# Pod Migration System

A system for live migration of pods between nodes using CRI-O's checkpoint and restore capabilities.

## Prerequisites

1. Vagrant with Ubuntu 22.04 (ARM-compatible for Mac M1 users)
2. CRI-O installed and configured on both source and target nodes
3. Network connectivity between nodes
4. Shared storage accessible by both nodes (for checkpoint data)

## Project Structure

```
migration/
├── core/          # Core functionality
│   ├── manager.py    # Pod/container lifecycle management
│   ├── migrator.py   # Pod migration logic
│   └── restorer.py   # Pod restoration logic
├── pods/          # Pod definitions
│   ├── base_pod.py      # Base class for pods
│   ├── counter_pod.py   # Example stateful pod
│   └── http_server_pod.py # Example web server pod
├── utils/         # Helper utilities
└── scripts/       # Shell script implementations
```

## Quick Start

### 1. Setup Environment

The setup script handles all dependencies and configuration:

```bash
# Register CRI-O hooks and setup dependencies
sudo ./setup/register.sh
```

### 2. Start a Pod

Use the start_pod.sh script to create and start pods:

```bash
# Start a counter pod
./migration/start_pod.sh counter pod1

# Start an HTTP server pod (default port 8080)
./migration/start_pod.sh http web1 --port 8080
```

### 3. Migrate a Pod

Use migrate.sh to checkpoint and transfer a pod:

```bash
# Migrate first running pod
./migration/migrate.sh

# Migrate specific pod
./migration/migrate.sh <pod_id>
```

### 4. Restore a Pod

Use restore.sh to restore a pod from checkpoint:

```bash
# Restore pod from checkpoint directory
./migration/restore.sh /tmp/pod_checkpoint
```

### 5. Cleanup

Use cleanup.sh to remove pods and cleanup resources:

```bash
# Remove all pods and containers
./migration/cleanup.sh
```

## Monitoring Pods

### Check Running Pods
```bash
sudo crictl pods
```

### Check Running Containers
```bash
sudo crictl ps
```

### Check Pod Logs
```bash
# Replace [container-id] with actual container ID
sudo crictl logs [container-id]
```

## Troubleshooting

Common issues and solutions:

1. **Permission denied**: Ensure you're running scripts with sudo when needed
   ```bash
   sudo ./migration/cleanup.sh
   ```

2. **Pod not found**: Verify pod is running
   ```bash
   sudo crictl pods
   sudo crictl ps
   ```

3. **CRI-O service issues**: Check service status
   ```bash
   sudo systemctl status crio
   ```

4. **Checkpoint fails**: Verify CRI-O hooks are registered
   ```bash
   sudo ./setup/register.sh
   sudo systemctl restart crio
   ```

5. **Network issues**: Check connectivity between nodes
   ```bash
   ping <target-node>
   ```

## Limitations

1. Network connections are not preserved during migration
2. Some pod configurations may not be supported by checkpoint/restore
3. Both nodes must run compatible CRI-O versions
4. Shared volumes must be accessible on both nodes
