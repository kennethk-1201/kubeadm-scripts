import os
import sys
import json
import uuid
import grpc

from runtime.v1 import api_pb2, api_pb2_grpc

# Constants
GRPC_SERVER_ADDRESS = 'unix:///var/run/crio/crio.sock'


def restore_pod(checkpoint_dir):
    """Restore a pod and its containers from checkpoint data."""
    # Set up the gRPC channel and stubs
    channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
    runtime_stub = api_pb2_grpc.RuntimeServiceStub(channel)

    try:
        # Load pod status from JSON file
        pod_status_path = os.path.join(checkpoint_dir, 'pod_status.json')
        with open(pod_status_path, 'r') as f:
            pod_status = json.load(f)

        # Generate unique identifiers for the new pod
        unique_suffix = uuid.uuid4().hex[:6]
        metadata = pod_status.get('metadata', {})
        new_pod_name = f"{metadata.get('name', 'pod')}-{unique_suffix}"
        new_pod_uid = f"{metadata.get('uid', 'uid')}-{unique_suffix}"
        namespace = metadata.get('namespace', 'default')
        attempt = int(metadata.get('attempt', 0))

        # Prepare pod sandbox configuration
        log_directory = pod_status.get('log_directory', '/var/log/pods')
        os.makedirs(log_directory, exist_ok=True)

        labels = pod_status.get('labels', {})
        labels['restored'] = 'true'
        annotations = pod_status.get('annotations', {})

        security_context = api_pb2.LinuxSandboxSecurityContext(
            namespace_options=api_pb2.NamespaceOption(
                network=api_pb2.NamespaceMode.POD,
                pid=api_pb2.NamespaceMode.POD,
                ipc=api_pb2.NamespaceMode.POD
            ),
            seccomp_profile_path='unconfined'
        )

        pod_sandbox_config = api_pb2.PodSandboxConfig(
            metadata=api_pb2.PodSandboxMetadata(
                name=new_pod_name,
                uid=new_pod_uid,
                namespace=namespace,
                attempt=attempt
            ),
            log_directory=log_directory,
            labels=labels,
            annotations=annotations,
            linux=api_pb2.LinuxPodSandboxConfig(security_context=security_context)
        )

        # Run the pod sandbox
        run_pod_request = api_pb2.RunPodSandboxRequest(config=pod_sandbox_config)
        run_pod_response = runtime_stub.RunPodSandbox(run_pod_request)
        new_pod_id = run_pod_response.pod_sandbox_id
        print(f"Pod sandbox started with ID: {new_pod_id}")

        # Check if the pod sandbox is ready
        pod_status_response = runtime_stub.PodSandboxStatus(
            api_pb2.PodSandboxStatusRequest(pod_sandbox_id=new_pod_id)
        )
        if pod_status_response.status.state != api_pb2.PodSandboxState.SANDBOX_READY:
            print(f"Error: Pod sandbox {new_pod_id} is not in a ready state.")
            sys.exit(1)

        # Restore each container within the pod
        for filename in os.listdir(checkpoint_dir):
            if filename.endswith('_status.json') and filename != 'pod_status.json':
                restore_container(
                    runtime_stub=runtime_stub,
                    checkpoint_dir=checkpoint_dir,
                    status_filename=filename,
                    new_pod_id=new_pod_id,
                    pod_sandbox_config=pod_sandbox_config,
                    unique_suffix=unique_suffix
                )

        print("Pod restoration completed on the destination node.")

    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()}")
    except Exception as e:
        print(f"Error: {e}")


def restore_container(runtime_stub, checkpoint_dir, status_filename, new_pod_id, pod_sandbox_config, unique_suffix):
    """Restore a single container from its checkpoint data."""
    container_id = status_filename.replace('_status.json', '')
    container_status_path = os.path.join(checkpoint_dir, status_filename)
    checkpoint_archive = os.path.join(checkpoint_dir, f"{container_id}.tar")

    # Verify that the checkpoint archive exists
    if not os.path.exists(checkpoint_archive):
        print(f"Checkpoint archive {checkpoint_archive} does not exist for container {container_id}")
        return

    with open(container_status_path, 'r') as f:
        container_status = json.load(f)

    print(f"Restoring container with ID: {container_id}")

    # Use the checkpoint archive as the image reference
    image_ref = checkpoint_archive
    container_metadata = container_status.get('metadata', {})
    unique_container_name = f"{container_metadata.get('name', 'container')}-{unique_suffix}"
    attempt = int(container_metadata.get('attempt', 0))

    # Prepare container configuration
    log_path = os.path.basename(container_status.get('logPath', 'container.log'))
    labels = container_status.get('labels', {})
    annotations = container_status.get('annotations', {})
    annotations['io.kubernetes.cri-o.restore'] = 'true'

    container_config = api_pb2.ContainerConfig(
        metadata=api_pb2.ContainerMetadata(
            name=unique_container_name,
            attempt=attempt
        ),
        image=api_pb2.ImageSpec(image=image_ref),
        labels=labels,
        annotations=annotations,
        log_path=log_path
    )

    try:
        # Create the container
        create_container_response = runtime_stub.CreateContainer(
            api_pb2.CreateContainerRequest(
                pod_sandbox_id=new_pod_id,
                config=container_config,
                sandbox_config=pod_sandbox_config
            )
        )
        new_container_id = create_container_response.container_id
        print(f"Container created with ID: {new_container_id}")

        # Start the container
        runtime_stub.StartContainer(
            api_pb2.StartContainerRequest(container_id=new_container_id)
        )
        print(f"Container {new_container_id} started and restored from checkpoint.")

    except grpc.RpcError as e:
        print(f"Failed to create or start container {container_id}: {e.code()} - {e.details()}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python restore.py <checkpoint_dir>")
        sys.exit(1)

    checkpoint_dir = sys.argv[1]
    restore_pod(checkpoint_dir)


if __name__ == "__main__":
    main()
