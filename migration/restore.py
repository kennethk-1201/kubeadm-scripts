import grpc
import sys
import os
import json

# Import the generated classes
import runtime.v1.api_pb2 as api_pb2
import runtime.v1.api_pb2_grpc as api_pb2_grpc

def restore_pod(checkpoint_dir):
    # Define the gRPC server address (Unix socket)
    GRPC_SERVER_ADDRESS = 'unix:///var/run/crio/crio.sock'

    # Establish a channel to the gRPC server over Unix socket
    channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
    # Create stubs (clients) for RuntimeService and ImageService
    runtime_stub = api_pb2_grpc.RuntimeServiceStub(channel)
    image_stub = api_pb2_grpc.ImageServiceStub(channel)

    try:
        # Step 1: Load pod sandbox status
        pod_status_path = os.path.join(checkpoint_dir, 'pod_status.json')
        with open(pod_status_path, 'r') as f:
            pod_status_dict = json.load(f)

        pod_sandbox_config = api_pb2.PodSandboxConfig(
            metadata=api_pb2.PodSandboxMetadata(
                name=pod_status_dict['metadata']['name'],
                uid=pod_status_dict['metadata']['uid'],
                namespace=pod_status_dict['metadata']['namespace'],
                attempt=int(pod_status_dict['metadata'].get('attempt', 1))
            ),
            labels=pod_status_dict.get('labels', {}),
            annotations=pod_status_dict.get('annotations', {}),
            linux=api_pb2.LinuxPodSandboxConfig()  # Adjust as necessary
        )

        # Step 2: Run pod sandbox
        run_pod_request = api_pb2.RunPodSandboxRequest(
            config=pod_sandbox_config,
            runtime_handler=pod_status_dict.get('runtime_handler', '')
        )
        run_pod_response = runtime_stub.RunPodSandbox(run_pod_request)
        new_pod_id = run_pod_response.pod_sandbox_id
        print(f"Pod sandbox started with ID: {new_pod_id}")

        # Step 3: Restore containers
        for filename in os.listdir(checkpoint_dir):
            if filename.endswith('_status.json'):
                container_id = filename.replace('_status.json', '')
                container_status_path = os.path.join(checkpoint_dir, filename)
                checkpoint_path = os.path.join(checkpoint_dir, f"{container_id}.tar")
                with open(container_status_path, 'r') as f:
                    container_status_dict = json.load(f)

                # Extract image reference
                image_ref = None
                image_field = container_status_dict.get('image', {})
                if isinstance(image_field, dict):
                    image_ref = image_field.get('image')
                if not image_ref:
                    # Try image_ref field
                    image_ref = container_status_dict.get('image_ref')
                if not image_ref:
                    # Try image_id field
                    image_ref = container_status_dict.get('image_id')
                if not image_ref:
                    print(f"Error: Unable to determine image reference for container {container_id}")
                    continue  # Skip this container

                print(f"Image reference for container {container_id}: {image_ref}")

                # Prepare container config
                container_config = api_pb2.ContainerConfig(
                    metadata=api_pb2.ContainerMetadata(
                        name=container_status_dict['metadata']['name'],
                        attempt=int(container_status_dict['metadata'].get('attempt', 1))
                    ),
                    image=api_pb2.ImageSpec(
                        image=image_ref,
                        # Include annotations if available
                        annotations=container_status_dict.get('annotations', {})
                    ),
                    labels=container_status_dict.get('labels', {}),
                    annotations=container_status_dict.get('annotations', {}),
                    linux=api_pb2.LinuxContainerConfig(
                        security_context=api_pb2.LinuxContainerSecurityContext()
                    )
                )

                # Add annotations to restore from checkpoint
                container_config.annotations['io.cri-o.Restore'] = 'true'
                container_config.annotations['io.cri-o.Checkpoint'] = checkpoint_path

                # Pull image if necessary
                image_status_response = image_stub.ImageStatus(
                    api_pb2.ImageStatusRequest(
                        image=api_pb2.ImageSpec(image=image_ref)
                    )
                )
                if not image_status_response.image or not image_status_response.image.id:
                    print(f"Pulling image {image_ref}...")
                    image_stub.PullImage(
                        api_pb2.PullImageRequest(
                            image=api_pb2.ImageSpec(image=image_ref)
                        )
                    )
                    print(f"Image {image_ref} pulled.")

                # Create container
                create_container_request = api_pb2.CreateContainerRequest(
                    pod_sandbox_id=new_pod_id,
                    config=container_config,
                    sandbox_config=pod_sandbox_config
                )
                create_container_response = runtime_stub.CreateContainer(create_container_request)
                new_container_id = create_container_response.container_id
                print(f"Container created with ID: {new_container_id}")

                # Start the container (this will trigger restore from checkpoint)
                runtime_stub.StartContainer(
                    api_pb2.StartContainerRequest(container_id=new_container_id)
                )
                print(f"Container {new_container_id} started and restored from checkpoint.")

        print("Pod restoration completed on the destination node.")

    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python restore_pod.py <checkpoint_dir>")
        sys.exit(1)
    checkpoint_dir = sys.argv[1]
    restore_pod(checkpoint_dir)
