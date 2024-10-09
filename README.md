# CRI-O Pod and Container Setup

This guide provides detailed instructions for setting up a Pod and Container using `crictl` on a Vagrant Ubuntu environment with CRI-O.

## Prerequisites
- Vagrant running Ubuntu (preferably ARM-compatible for Mac M1 users).
- CRI-O installed and configured.
- `crictl` installed and accessible.

## Additional Steps Required

### Step 1: Pull the Busybox Image
Pull the `busybox` image using `crictl`:

```bash
sudo crictl pull docker.io/library/busybox:latest
```

Verify the image is pulled:

```bash
sudo crictl images | grep busybox
```

### Step 2: Create the Pod
Create the Pod using `crictl`:

```bash
POD_ID=$(sudo crictl runp pod-config.json)
```

### Step 3: Create the Container in the Pod
Create the container inside the Pod using the command:

```bash
CONTAINER_ID=$(sudo crictl create "$POD_ID" container-config.json pod-config.json)
```

### Step 4: Start the Container
Start the container:

```bash
sudo crictl start "$CONTAINER_ID"
```

### Step 5: Verify the Pod and Container
Verify that the Pod and Container are running:

```bash
sudo crictl pods
sudo crictl ps
```