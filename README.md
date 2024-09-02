## Kubernetes Checkpointing Setup

This repository contains the scripts to set up a local Kubernetes cluster on multiple VMs (1 master and 2 workers) with the checkpointing feature gate enabled.

### Setup
1. Install a VirtualBox
2. Setup the cluster by runnung `vagrant up` from the project root.

### Test the checkpointing feature
Create a pod via kubectl on the master
```
sudo kubectl run webserver --image=nginx -n default
```

Create checkpoint in worker 1
```
sudo curl -sk -X POST  "https://10.0.0.11:10250/checkpoint/default/webserver/webserver" \
  --key /etc/kubernetes/pki/apiserver-kubelet-client.key \
  --cacert /etc/kubernetes/pki/ca.crt \
  --cert /etc/kubernetes/pki/apiserver-kubelet-client.crt
```

The checkpoint tar file should be stored in `/var/lib/kubelet/checkpoints/checkpoint-<pod>_<namespace>-<container>-<timestamp>.tar`.
