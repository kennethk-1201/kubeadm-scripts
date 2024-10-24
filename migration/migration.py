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
            if pod.state == api_pb2.PodSandboxStateValue(state=api_pb2.SANDBOX_READY).state:
                print(f"Selected running pod: {pod.metadata.name}")
                return pod
        print("No running pods found to migrate.")
        return None

    def prepare_checkpoint(self, pod_id):
        """Checkpoint containers in the specified pod."""
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
        containers_response = self.runtime_stub.ListContainers(
            api_pb2.ListContainersRequest(filter=api_pb2.ContainerFilter(pod_sandbox_id=pod_id))
        )
        container_ids = [c.id for c in containers_response.containers]
        if not container_ids:
            print("No containers found in the pod.")
            return []

        for container_id in container_ids:
            checkpoint_path = os.path.join(CHECKPOINT_DIR, f'{container_id}.tar')
            request = api_pb2.CheckpointContainerRequest(container_id=container_id, location=checkpoint_path)
            self.runtime_stub.CheckpointContainer(request)
            print(f"Checkpointed container {container_id} to {checkpoint_path}")

        # Save pod status and container statuses
        pod_status = self.runtime_stub.PodSandboxStatus(
            api_pb2.PodSandboxStatusRequest(pod_sandbox_id=pod_id)
        ).status
        self._save_json(MessageToDict(pod_status), os.path.join(CHECKPOINT_DIR, 'pod_status.json'))

        for container_id in container_ids:
            # Set verbose=True to get the full container specification
            container_status_response = self.runtime_stub.ContainerStatus(
                api_pb2.ContainerStatusRequest(container_id=container_id, verbose=True)
            )
            container_status_dict = MessageToDict(container_status_response.status)

            # Convert the 'info' map to a regular dictionary
            container_info_dict = {}
            for key, value in container_status_response.info.items():
                container_info_dict[key] = value

            # Include 'info' in the container status dictionary
            container_status_dict['info'] = container_info_dict

            self._save_json(container_status_dict, os.path.join(CHECKPOINT_DIR, f'{container_id}_status.json'))
        return container_ids

    def transfer_checkpoint(self):
        """Transfer the checkpoint data to the remote node."""
        subprocess.run(['scp', '-r', CHECKPOINT_DIR, f'vagrant@{REMOTE_NODE}:{REMOTE_CHECKPOINT_DIR}'], check=True)
        print("Checkpoint data transferred to the destination node.")

    def cleanup(self):
        """Remove the checkpoint directory."""
        shutil.rmtree(CHECKPOINT_DIR, ignore_errors=True)
        print(f"Cleaned up checkpoint directory: {CHECKPOINT_DIR}")

    def stop_and_remove_pod(self, pod_id):
        """Stop and remove the specified pod."""
        self.runtime_stub.StopPodSandbox(api_pb2.StopPodSandboxRequest(pod_sandbox_id=pod_id))
        self.runtime_stub.RemovePodSandbox(api_pb2.RemovePodSandboxRequest(pod_sandbox_id=pod_id))
        print("Pod stopped and removed from the source node.")

    def _save_json(self, data, file_path):
        """Save data to a JSON file."""
        with open(file_path, 'w') as f:
            json.dump(data, f)
        print(f"Saved data to {file_path}")

    def migrate(self):
        """Run the pod migration process."""
        pod = self.select_pod()
        if not pod:
            return

        pod_id = pod.id
        container_ids = self.prepare_checkpoint(pod_id)
        if not container_ids:
            return

        self.transfer_checkpoint()
        self.stop_and_remove_pod(pod_id)
        self.cleanup()
        print("Migration process completed.")


if __name__ == "__main__":
    try:
        migration = PodMigration()
        migration.migrate()
    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()}")
    except Exception as e:
        print(f"Error: {e}")
