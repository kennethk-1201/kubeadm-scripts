import json
import os
import shutil
import subprocess

import grpc
from google.protobuf.json_format import MessageToDict

from migration.runtime.v1 import api_pb2, api_pb2_grpc

GRPC_SERVER_ADDRESS = "unix:///var/run/crio/crio.sock"
CHECKPOINT_DIR = "/tmp/pod_checkpoint"
REMOTE_NODE = "10.0.0.11"
REMOTE_CHECKPOINT_DIR = "/tmp/pod_checkpoint"


class PodMigrator:
    """Handles pod migration operations."""

    def __init__(self):
        self.channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
        self.runtime_stub = api_pb2_grpc.RuntimeServiceStub(self.channel)

    def select_pod(self, pod_id=None):
        """
        Select a pod for migration.

        Args:
            pod_id: Optional pod ID. If provided, selects this specific pod.
                   If None, selects the first running pod.
        """
        if pod_id:
            try:
                status_response = self.runtime_stub.PodSandboxStatus(
                    api_pb2.PodSandboxStatusRequest(pod_sandbox_id=pod_id)
                )
                if (
                    status_response.status.state
                    == api_pb2.PodSandboxState.SANDBOX_READY
                ):
                    print(
                        f"Selected pod: {status_response.status.metadata.name} ({pod_id})"
                    )
                    return status_response.status
                else:
                    print(f"Pod {pod_id} is not in ready state")
                    return None
            except grpc.RpcError as e:
                print(f"Error finding pod {pod_id}: {e.details()}")
                return None

        # If no pod_id provided, select first running pod
        pods_response = self.runtime_stub.ListPodSandbox(
            api_pb2.ListPodSandboxRequest()
        )
        for pod in pods_response.items:
            if pod.state == api_pb2.PodSandboxState.SANDBOX_READY:
                print(f"Selected running pod: {pod.metadata.name}")
                return pod
        print("No running pods found to migrate.")
        return None

    def prepare_checkpoint(self, pod_id):
        """Checkpoint containers in the specified pod and save their statuses."""
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)

        containers_response = self.runtime_stub.ListContainers(
            api_pb2.ListContainersRequest(
                filter=api_pb2.ContainerFilter(pod_sandbox_id=pod_id)
            )
        )
        container_ids = [container.id for container in containers_response.containers]
        if not container_ids:
            print("No containers found in the pod.")
            return []

        for container_id in container_ids:
            self._checkpoint_container(container_id)

        # Save pod status
        self._save_pod_status(pod_id)

        return container_ids

    def transfer_checkpoint(self):
        """Transfer the checkpoint data and shared volumes to the remote node."""
        # Transfer checkpoint data
        subprocess.run(
            [
                "scp",
                "-r",
                CHECKPOINT_DIR,
                f"vagrant@{REMOTE_NODE}:{REMOTE_CHECKPOINT_DIR}",
            ],
            check=True,
        )
        print("Checkpoint data transferred to the destination node.")

        # Transfer shared volumes if they exist
        self._transfer_shared_volumes()

    def stop_and_remove_pod(self, pod_id):
        """Stop and remove the specified pod."""
        self.runtime_stub.StopPodSandbox(
            api_pb2.StopPodSandboxRequest(pod_sandbox_id=pod_id)
        )
        self.runtime_stub.RemovePodSandbox(
            api_pb2.RemovePodSandboxRequest(pod_sandbox_id=pod_id)
        )
        print(f"Pod {pod_id} stopped and removed from the source node.")

    def cleanup(self):
        """Remove the checkpoint directory."""
        shutil.rmtree(CHECKPOINT_DIR, ignore_errors=True)
        print(f"Cleaned up checkpoint directory: {CHECKPOINT_DIR}")

    def _checkpoint_container(self, container_id):
        """Checkpoint a single container and save its status."""
        checkpoint_path = os.path.join(CHECKPOINT_DIR, f"{container_id}.tar")
        self.runtime_stub.CheckpointContainer(
            api_pb2.CheckpointContainerRequest(
                container_id=container_id, location=checkpoint_path
            )
        )
        print(f"Checkpointed container {container_id} to {checkpoint_path}")

        # Get and save container status
        container_status_response = self.runtime_stub.ContainerStatus(
            api_pb2.ContainerStatusRequest(container_id=container_id, verbose=True)
        )
        container_status_dict = MessageToDict(container_status_response.status)
        container_status_dict["image"] = {"image": checkpoint_path}
        container_status_dict["info"] = dict(container_status_response.info)

        status_file = os.path.join(CHECKPOINT_DIR, f"{container_id}_status.json")
        self._save_json(container_status_dict, status_file)

    def _save_pod_status(self, pod_id):
        """Save pod status to a JSON file."""
        pod_status_response = self.runtime_stub.PodSandboxStatus(
            api_pb2.PodSandboxStatusRequest(pod_sandbox_id=pod_id)
        )
        pod_status_dict = MessageToDict(pod_status_response.status)
        self._save_json(
            pod_status_dict, os.path.join(CHECKPOINT_DIR, "pod_status.json")
        )

    def _transfer_shared_volumes(self):
        """Transfer shared volumes if they exist."""
        pod_status_path = os.path.join(CHECKPOINT_DIR, "pod_status.json")
        if os.path.exists(pod_status_path):
            with open(pod_status_path, "r") as f:
                pod_status = json.load(f)
                shared_volume = pod_status.get("annotations", {}).get("shared-volume")
                if shared_volume and os.path.exists(shared_volume):
                    subprocess.run(
                        [
                            "scp",
                            "-r",
                            shared_volume,
                            f"vagrant@{REMOTE_NODE}:{shared_volume}",
                        ],
                        check=True,
                    )
                    print(
                        f"Shared volume {shared_volume} transferred to the destination node."
                    )

    def _save_json(self, data, file_path):
        """Save data to a JSON file."""
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved data to {file_path}")

    def migrate(self, pod_id=None):
        """
        Run the pod migration process.

        Args:
            pod_id: Optional pod ID to migrate. If None, migrates first running pod.
        """
        pod = self.select_pod(pod_id)
        if not pod:
            return

        container_ids = self.prepare_checkpoint(
            pod.id if hasattr(pod, "id") else pod.metadata.uid
        )
        if not container_ids:
            return

        self.transfer_checkpoint()
        self.stop_and_remove_pod(pod.id)
        self.cleanup()
        print("Migration process completed.")
