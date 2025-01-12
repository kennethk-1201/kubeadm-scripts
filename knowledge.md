## Package Repositories
- Use pkgs.k8s.io for Kubernetes packages
- Use signed-by method for repository keys in /etc/apt/keyrings/
- Match CRI-O version with Kubernetes version (currently using v1.28)
- CRI-O and Kubernetes versions must be aligned for compatibility

## Project Status
- Initial implementation of pod migration using CRI-O
- Basic checkpoint/restore functionality
- Working on controller integration
- Implemented MigratingPod CRD with:
  - Full spec definition for migration parameters
  - Status tracking with phases
  - Conditions for detailed state tracking
  - Printer columns for kubectl integration
- Sample controller synced to master node for pod migration control

## Kubernetes Setup
- Master node (10.0.0.9) runs control plane and sample-controller
- Worker nodes (10.0.0.10, 10.0.0.11) handle pod workloads
- Uses official Kubernetes packages from pkgs.k8s.io
- No need to sync Kubernetes source code for testing sample-controller
- Flannel CNI for pod networking
- CRI-O as container runtime with CRIU support enabled
- Required kernel settings:
  - IP forwarding enabled (net.ipv4.ip_forward = 1)
  - Bridge netfilter call iptables enabled (net.bridge.bridge-nf-call-iptables = 1)
  - br_netfilter module loaded

## TODOs
1. ✓ Implement MigratingPod CRD
