import grpc
import sys
import os
import json
import shutil

# Import the generated classes
import runtime.v1.api_pb2 as api_pb2
import runtime.v1.api_pb2_grpc as api_pb2_grpc

# Define the gRPC server address (Unix socket)
GRPC_SERVER_ADDRESS = 'unix:///var/run/crio/crio.sock'

def run_pod_migration():
    # Establish a channel to the gRPC server over Unix socket
    channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
    # Create stubs (clients) for RuntimeService and ImageService
    runtime_stub = api_pb2_grpc.RuntimeServiceStub(channel)

    try:
        # Step 1: List all pods and select the one to migrate
        print("Listing all pods...")
        pods_response = runtime_stub.ListPodSandbox(api_pb2.ListPodSandboxRequest())
        pods = pods_response.items

        if not pods:
            print("No pods found to migrate.")
            return

        # For simplicity, select the first running pod in the list
        pod_to_migrate = None
        for pod in pods:
            if pod.state == api_pb2.PodSandboxStateValue(state=api_pb2.SANDBOX_READY).state:
                pod_to_migrate = pod
                break

        if not pod_to_migrate:
            print("No running pods found to migrate.")
            return

        pod_id = pod_to_migrate.id
        pod_metadata = pod_to_migrate.metadata
        print(f"Selected Pod ID for migration: {pod_id}")
        print(f"Pod Name: {pod_metadata.name}, Namespace: {pod_metadata.namespace}")

        # Step 2: Get pod status
        pod_status_response = runtime_stub.PodSandboxStatus(
            api_pb2.PodSandboxStatusRequest(pod_sandbox_id=pod_id)
        )
        pod_status = pod_status_response.status

        # Step 3: List containers in the pod
        print("Listing containers in the pod...")
        containers_response = runtime_stub.ListContainers(
            api_pb2.ListContainersRequest(
                filter=api_pb2.ContainerFilter(pod_sandbox_id=pod_id)
            )
        )
        containers = containers_response.containers
        if not containers:
            print("No containers found in the pod.")
            return

        container_ids = [container.id for container in containers]
        print(f"Container IDs in the pod: {container_ids}")

        # Step 4: Checkpoint each container
        checkpoint_dir = '/tmp/pod_checkpoint'
        os.makedirs(checkpoint_dir, exist_ok=True)

        print("Checkpointing containers...")
        for container_id in container_ids:
            checkpoint_path = os.path.join(checkpoint_dir, f'{container_id}.tar')
            checkpoint_request = api_pb2.CheckpointContainerRequest(
                container_id=container_id,
                location=checkpoint_path,
                timeout=0  # Use default timeout
            )
            runtime_stub.CheckpointContainer(checkpoint_request)
            print(f"Container {container_id} checkpointed to {checkpoint_path}")

        # Step 5: Save pod sandbox status
        pod_status_path = os.path.join(checkpoint_dir, 'pod_status.json')
        with open(pod_status_path, 'w') as f:
            json.dump(MessageToDict(pod_status), f)
        print(f"Pod sandbox status saved to {pod_status_path}")

        # Step 6: Save container statuses
        for container_id in container_ids:
            container_status_response = runtime_stub.ContainerStatus(
                api_pb2.ContainerStatusRequest(container_id=container_id)
            )
            container_status = container_status_response.status
            container_status_path = os.path.join(
                checkpoint_dir, f'{container_id}_status.json'
            )
            with open(container_status_path, 'w') as f:
                json.dump(MessageToDict(container_status), f)
            print(f"Container {container_id} status saved to {container_status_path}")

        # Step 7: Transfer checkpoint data to destination node
        destination_node = '10.0.0.11'
        remote_checkpoint_dir = '/tmp/pod_checkpoint'
        transfer_cmd = [
            'scp', '-r', checkpoint_dir,
            f'vagrant@{destination_node}:{remote_checkpoint_dir}'
        ]
        print("Transferring checkpoint data to destination node...")
        subprocess.run(transfer_cmd, check=True)
        print("Checkpoint data transferred.")

        # Step 8: Remove the pod from the source node
        print("Stopping the pod on the source node...")
        runtime_stub.StopPodSandbox(
            api_pb2.StopPodSandboxRequest(pod_sandbox_id=pod_id)
        )
        print("Removing the pod from the source node...")
        runtime_stub.RemovePodSandbox(
            api_pb2.RemovePodSandboxRequest(pod_sandbox_id=pod_id)
        )
        print("Pod removed from the source node.")

        print("Migration process completed on the source node.")

    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    from google.protobuf.json_format import MessageToDict
    import subprocess
    run_pod_migration()
