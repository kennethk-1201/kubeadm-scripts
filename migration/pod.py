import grpc
import sys
import os
import json

# Import the generated classes
import runtime.v1.api_pb2 as api_pb2
import runtime.v1.api_pb2_grpc as api_pb2_grpc

# Define the gRPC server address (Unix socket)
GRPC_SERVER_ADDRESS = 'unix:///var/run/crio/crio.sock'

def create_pod_sandbox(runtime_stub):
    # Define the pod sandbox configuration
    pod_sandbox_config = api_pb2.PodSandboxConfig(
        metadata=api_pb2.PodSandboxMetadata(
            name='mypod',
            namespace='default',
            uid='mypoduid',
            attempt=0
        ),
        hostname='mypod-hostname',
        log_directory='/var/log/pods/mypod',
        labels={'key1': 'value1'},
        annotations={'key1': 'value1'},
        linux=api_pb2.LinuxPodSandboxConfig(
            security_context=api_pb2.LinuxSandboxSecurityContext(
                namespace_options=api_pb2.NamespaceOption(
                    network=api_pb2.NamespaceMode.POD,
                    pid=api_pb2.NamespaceMode.POD,  # Changed to POD
                    ipc=api_pb2.NamespaceMode.POD
                ),
                seccomp_profile_path='unconfined',
            ),
        )
    )

    # Run the pod sandbox
    request = api_pb2.RunPodSandboxRequest(
        config=pod_sandbox_config,
        runtime_handler=''  # Default runtime handler
    )
    response = runtime_stub.RunPodSandbox(request)
    pod_sandbox_id = response.pod_sandbox_id
    print(f"Created pod sandbox with ID: {pod_sandbox_id}")
    return pod_sandbox_id

def pull_image(image_stub, image_name):
    image_spec = api_pb2.ImageSpec(image=image_name)
    request = api_pb2.PullImageRequest(image=image_spec)
    response = image_stub.PullImage(request)
    print(f"Pulled image: {image_name}")
    return response.image_ref

def create_container(runtime_stub, image_stub, pod_sandbox_id):
    # Pull the image
    image_name = 'docker.io/library/busybox:latest'
    pull_image(image_stub, image_name)

    # Define the container configuration
    container_config = api_pb2.ContainerConfig(
        metadata=api_pb2.ContainerMetadata(
            name='mycontainer',
            attempt=0
        ),
        image=api_pb2.ImageSpec(image=image_name),
        command=['/bin/sh'],
        args=['-c', 'while true; do echo hello world; sleep 1; done'],
        labels={'key1': 'value1'},
        annotations={'key1': 'value1'},
        log_path='mycontainer.log',
        stdin=False,
        stdin_once=False,
        tty=False,
        linux=api_pb2.LinuxContainerConfig(
            security_context=api_pb2.LinuxContainerSecurityContext(
                namespace_options=api_pb2.NamespaceOption(
                    pid=api_pb2.NamespaceMode.POD  # Explicitly set to POD
                ),
                privileged=False,
                capabilities=api_pb2.Capability(add_capabilities=['CAP_SYS_ADMIN'])
            )
        )
    )

    # Define the pod sandbox configuration
    pod_sandbox_config = api_pb2.PodSandboxConfig(
        metadata=api_pb2.PodSandboxMetadata(
            name='mypod',
            namespace='default',
            uid='mypoduid',
            attempt=0
        ),
    )

    # Create the container
    request = api_pb2.CreateContainerRequest(
        pod_sandbox_id=pod_sandbox_id,
        config=container_config,
        sandbox_config=pod_sandbox_config
    )
    response = runtime_stub.CreateContainer(request)
    container_id = response.container_id
    print(f"Created container with ID: {container_id}")
    return container_id

def start_container(runtime_stub, container_id):
    request = api_pb2.StartContainerRequest(container_id=container_id)
    runtime_stub.StartContainer(request)
    print(f"Started container with ID: {container_id}")

def stop_container(runtime_stub, container_id):
    request = api_pb2.StopContainerRequest(container_id=container_id, timeout=10)
    runtime_stub.StopContainer(request)
    print(f"Stopped container with ID: {container_id}")

def remove_container(runtime_stub, container_id):
    request = api_pb2.RemoveContainerRequest(container_id=container_id)
    runtime_stub.RemoveContainer(request)
    print(f"Removed container with ID: {container_id}")

def stop_pod_sandbox(runtime_stub, pod_sandbox_id):
    request = api_pb2.StopPodSandboxRequest(pod_sandbox_id=pod_sandbox_id)
    runtime_stub.StopPodSandbox(request)
    print(f"Stopped pod sandbox with ID: {pod_sandbox_id}")

def remove_pod_sandbox(runtime_stub, pod_sandbox_id):
    request = api_pb2.RemovePodSandboxRequest(pod_sandbox_id=pod_sandbox_id)
    runtime_stub.RemovePodSandbox(request)
    print(f"Removed pod sandbox with ID: {pod_sandbox_id}")

def main():
    # Establish a channel to the gRPC server over Unix socket
    channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
    # Create stubs (clients) for RuntimeService and ImageService
    runtime_stub = api_pb2_grpc.RuntimeServiceStub(channel)
    image_stub = api_pb2_grpc.ImageServiceStub(channel)

    try:
        if len(sys.argv) < 2:
            print("Usage: python3 script.py [start|teardown]")
            sys.exit(1)
        action = sys.argv[1]
        if action == 'start':
            pod_sandbox_id = create_pod_sandbox(runtime_stub)
            container_id = create_container(runtime_stub, image_stub, pod_sandbox_id)
            start_container(runtime_stub, container_id)
            # Save the IDs for teardown
            with open('pod_container_ids.json', 'w') as f:
                json.dump({'pod_sandbox_id': pod_sandbox_id, 'container_id': container_id}, f)
            print("Pod and container started successfully.")
        elif action == 'teardown':
            # Load the IDs
            if not os.path.exists('pod_container_ids.json'):
                print("No pod and container IDs found. Please start first.")
                sys.exit(1)
            with open('pod_container_ids.json', 'r') as f:
                ids = json.load(f)
                pod_sandbox_id = ids['pod_sandbox_id']
                container_id = ids['container_id']
            stop_container(runtime_stub, container_id)
            remove_container(runtime_stub, container_id)
            stop_pod_sandbox(runtime_stub, pod_sandbox_id)
            remove_pod_sandbox(runtime_stub, pod_sandbox_id)
            os.remove('pod_container_ids.json')
            print("Pod and container torn down successfully.")
        else:
            print("Invalid action. Use 'start' or 'teardown'.")
    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
