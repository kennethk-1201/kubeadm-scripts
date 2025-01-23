# CRI-O Pod and Container Setup

This guide provides detailed instructions for setting up and managing Pods and Containers using CRI-O on a Vagrant Ubuntu environment.

## Prerequisites
- Vagrant running Ubuntu (preferably ARM-compatible for Mac M1 users)
- CRI-O installed and configured
- Python 3.9 or higher
- Virtual environment setup

## Project Structure

```
migration/
├── core/           # Core implementation files
├── pods/           # Pod type implementations
├── utils/          # Shared utilities
├── scripts/        # Shell script implementations
├── start_pod.sh    # Symlink to create/start pods
├── migrate.sh      # Symlink to migrate pods
├── restore.sh      # Symlink to restore pods
└── cleanup.sh      # Symlink to cleanup resources
```

## Setup Steps

### 1. Initial Setup
```bash
# Register CRI-O and setup dependencies
sudo ./setup/register.sh

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install project dependencies
pip install -e .
```

### 2. Start a Pod
```bash
# Start a counter pod
./migration/start_pod.sh counter pod1

# Or start an HTTP server pod (default port 8080)
./migration/start_pod.sh http web1 --port 8080
```

### 3. Migrate a Pod
```bash
# Migrate first running pod
./migration/migrate.sh

# Or migrate specific pod
./migration/migrate.sh <pod_id>
```

### 4. Restore a Pod
```bash
# Restore pod from checkpoint directory
./migration/restore.sh /tmp/pod_checkpoint
```

### 5. Cleanup
```bash
# Remove all pods and containers
./migration/cleanup.sh
```

## Development Guidelines

### Python Imports
- Use absolute imports from the `migration` package root
- Example: `from migration.core.migrator import PodMigrator`
- Requires PYTHONPATH to include project root directory
- Do not use relative imports

### Shell Scripts
All shell scripts:
- Must be run from project root directory
- Activate virtual environment automatically
- Set PYTHONPATH to project root
- Show current state after execution
- Provide usage information
- Handle errors gracefully

## Verifying State

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

If you encounter errors:

1. Ensure you're in the project root directory when running commands
2. Verify the virtual environment is activated
3. Check if CRI-O service is running:
   ```bash
   sudo systemctl status crio
   ```
4. Verify the checkpoint directory exists for restore operations
5. Check CRI-O logs:
   ```bash
   sudo journalctl -u crio
   ```
