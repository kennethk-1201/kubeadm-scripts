## Kubernetes Checkpointing Setup

This repository contains the scripts to set up a local Kubernetes cluster on multiple VMs (1 master and 2 workers) with the checkpointing feature gate enabled.

### Setup
1. Install a VirtualBox and Vagrant
2. Setup the cluster by runnung `vagrant up` from the project root. 

### Test the checkpointing feature
Create a pod via kubectl on the master
```
sudo kubectl run webserver --image=nginx -n default
```

*After the pod is running*, create checkpoint in the corresponding worker. Worker 1 has IP `10.0.0.11` while worker 2 has IP `10.0.0.12`.
```
# If pod is running on worker 2, run the code below.
sudo curl -sk -X POST  "https://10.0.0.12:10250/checkpoint/default/webserver/webserver" \
  --key /etc/kubernetes/pki/apiserver-kubelet-client.key \
  --cacert /etc/kubernetes/pki/ca.crt \
  --cert /etc/kubernetes/pki/apiserver-kubelet-client.crt
```

The checkpoint tar file should be stored in `/var/lib/kubelet/checkpoints/checkpoint-<pod>_<namespace>-<container>-<timestamp>.tar` inside the corresponding worker.
