import grpc
import os
import json
import subprocess
import shutil
from google.protobuf.json_format import MessageToDict
import runtime.v1.api_pb2 as api_pb2
import runtime.v1.api_pb2_grpc as api_pb2_grpc

GRPC_SERVER_ADDRESS = 'unix:///var/run/crio/crio.sock'
CHECKPOINT_DIR = '/tmp/pod_checkpoint'
REMOTE_NODE = '10.0.0.11'
REMOTE_CHECKPOINT_DIR = '/tmp/pod_checkpoint'


class PodMigration:
    def __init__(self):
        self.channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
        self.runtime_stub = api_pb2_grpc.RuntimeServiceStub(self.channel)

    def select_pod(self):
        """Select the first running pod for migration."""
        pods_response = self.runtime_stub.ListPodSandbox(api_pb2.ListPodSandboxRequest())
        for pod in pods_response.items:
            if pod.state == api_pb2.PodSandboxState.SANDBOX_READY:
                print(f"Selected running pod: {pod.metadata.name}")
                return pod
        print("No running pods found to migrate.")
        return None

    def prepare_checkpoint(self, pod_id):
        """Checkpoint containers in the specified pod and save their statuses."""
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)

        # List containers in the pod
        containers_response = self.runtime_stub.ListContainers(
            api_pb2.ListContainersRequest(
                filter=api_pb2.ContainerFilter(pod_sandbox_id=pod_id)
            )
        )
        container_ids = [container.id for container in containers_response.containers]
        if not container_ids:
            print("No containers found in the pod.")
            return []

        # Checkpoint each container and save its status
        for container_id in container_ids:
            checkpoint_path = os.path.join(CHECKPOINT_DIR, f'{container_id}.tar')
            self.runtime_stub.CheckpointContainer(
                api_pb2.CheckpointContainerRequest(
                    container_id=container_id,
                    location=checkpoint_path
                )
            )
            print(f"Checkpointed container {container_id} to {checkpoint_path}")

            # Get container status
            container_status_response = self.runtime_stub.ContainerStatus(
                api_pb2.ContainerStatusRequest(container_id=container_id, verbose=True)
            )
            container_status_dict = MessageToDict(container_status_response.status)

            # Replace the 'image' key with the checkpoint path
            container_status_dict['image'] = {'image': checkpoint_path}

            # Convert 'info' field to dictionary
            container_status_dict['info'] = dict(container_status_response.info)

            # Save container status
            status_file = os.path.join(CHECKPOINT_DIR, f'{container_id}_status.json')
            self._save_json(container_status_dict, status_file)

        # Save pod status
        pod_status_response = self.runtime_stub.PodSandboxStatus(
            api_pb2.PodSandboxStatusRequest(pod_sandbox_id=pod_id)
        )
        pod_status_dict = MessageToDict(pod_status_response.status)
        self._save_json(pod_status_dict, os.path.join(CHECKPOINT_DIR, 'pod_status.json'))

        return container_ids

    def transfer_checkpoint(self):
        """Transfer the checkpoint data to the remote node."""
        subprocess.run(
            ['scp', '-r', CHECKPOINT_DIR, f'vagrant@{REMOTE_NODE}:{REMOTE_CHECKPOINT_DIR}'],
            check=True
        )
        print("Checkpoint data transferred to the destination node.")

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

    def _save_json(self, data, file_path):
        """Save data to a JSON file."""
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Saved data to {file_path}")

    def migrate(self):
        """Run the pod migration process."""
        pod = self.select_pod()
        if not pod:
            return

        container_ids = self.prepare_checkpoint(pod.id)
        if not container_ids:
            return

        self.transfer_checkpoint()
        self.stop_and_remove_pod(pod.id)
        self.cleanup()
        print("Migration process completed.")


if __name__ == "__main__":
    migration = PodMigration()
    try:
        migration.migrate()
    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()}")
    except Exception as e:
        print(f"Error: {e}")
