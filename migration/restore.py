import grpc
import sys
import os
import json
import uuid

import runtime.v1.api_pb2 as api_pb2
import runtime.v1.api_pb2_grpc as api_pb2_grpc

def restore_pod(checkpoint_dir):
    GRPC_SERVER_ADDRESS = 'unix:///var/run/crio/crio.sock'
    channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
    runtime_stub = api_pb2_grpc.RuntimeServiceStub(channel)

    try:
        pod_status_path = os.path.join(checkpoint_dir, 'pod_status.json')
        with open(pod_status_path, 'r') as f:
            pod_status_dict = json.load(f)

        # Generate a unique pod name and UID
        unique_suffix = uuid.uuid4().hex[:6]
        new_pod_name = f"{pod_status_dict['metadata']['name']}-{unique_suffix}"
        new_pod_uid = f"{pod_status_dict['metadata']['uid']}-{unique_suffix}"

        # Set the log_directory in PodSandboxConfig
        log_directory = pod_status_dict.get('log_directory', '/var/log/pods')
        sandbox_security_context = api_pb2.LinuxSandboxSecurityContext(
            namespace_options=api_pb2.NamespaceOption(
                network=api_pb2.NamespaceMode.POD,
                pid=api_pb2.NamespaceMode.POD,
                ipc=api_pb2.NamespaceMode.POD,
            ),
            seccomp_profile_path='unconfined'
        )

        pod_sandbox_config = api_pb2.PodSandboxConfig(
            metadata=api_pb2.PodSandboxMetadata(
                name=new_pod_name,
                uid=new_pod_uid,
                namespace=pod_status_dict['metadata']['namespace'],
                attempt=int(pod_status_dict['metadata'].get('attempt', 1))
            ),
            log_directory=log_directory,
            labels=pod_status_dict.get('labels', {}),
            annotations=pod_status_dict.get('annotations', {}),
            linux=api_pb2.LinuxPodSandboxConfig(security_context=sandbox_security_context)
        )

        # Ensure the log_directory exists
        os.makedirs(log_directory, exist_ok=True)

        # Update labels and annotations
        pod_sandbox_config.labels['restored'] = 'true'

        # Run the pod sandbox
        run_pod_request = api_pb2.RunPodSandboxRequest(
            config=pod_sandbox_config,
            runtime_handler=pod_status_dict.get('runtime_handler', '')
        )
        run_pod_response = runtime_stub.RunPodSandbox(run_pod_request)
        new_pod_id = run_pod_response.pod_sandbox_id
        print(f"Pod sandbox started with ID: {new_pod_id}")

        pod_status = runtime_stub.PodSandboxStatus(
            api_pb2.PodSandboxStatusRequest(pod_sandbox_id=new_pod_id)
        )
        if pod_status.status.state != api_pb2.PodSandboxState.SANDBOX_READY:
            print(f"Error: Pod sandbox {new_pod_id} is not in a ready state.")
            sys.exit(1)

        # Restore each container within the pod
        for filename in os.listdir(checkpoint_dir):
            if not filename.endswith('_status.json') or filename == 'pod_status.json':
                continue

            container_id = filename.replace('_status.json', '')
            container_status_path = os.path.join(checkpoint_dir, filename)
            checkpoint_archive_name = f"{container_id}.tar"
            checkpoint_path = os.path.abspath(os.path.join(checkpoint_dir, checkpoint_archive_name))

            # Verify that the checkpoint archive exists
            if not os.path.exists(checkpoint_path):
                print(f"Checkpoint archive {checkpoint_path} does not exist for container {container_id}")
                continue

            with open(container_status_path, 'r') as f:
                container_status_dict = json.load(f)

            print(f"Restoring container with ID: {container_id}")

            # Use the original image reference
            image_ref = container_status_dict.get('image', {}).get('image') or "docker.io/library/busybox:latest"
            unique_container_name = f"{container_status_dict['metadata']['name']}-{unique_suffix}"

            # Use a relative path for log_path
            log_path = container_status_dict.get('logPath', 'container.log')
            log_path = os.path.basename(log_path)  # Ensure it's a filename
            print("Log path:", log_path)

            # Extract runtime specification details
            info_json = container_status_dict.get('info', {}).get('info', '{}')
            info_dict = json.loads(info_json)
            runtime_spec = info_dict.get('runtimeSpec', {})

            # Prepare the container arguments
            command = runtime_spec.get('process', {}).get('args', [])
            print("Command:", command)

            # Prepare environment variables
            envs = []
            for env in runtime_spec.get('process', {}).get('env', []):
                key_value = env.split('=', 1)
                if len(key_value) == 2:
                    envs.append(api_pb2.KeyValue(key=key_value[0], value=key_value[1]))

            # Prepare mounts with correct field names
            mounts = [
                api_pb2.Mount(
                    container_path=m['destination'],
                    host_path=m['source'],
                )
                for m in runtime_spec.get('mounts', [])
            ]

            # Prepare capabilities
            capabilities = runtime_spec.get('process', {}).get('capabilities', {}).get('effective', [])

            # Build the container configuration
            container_config = api_pb2.ContainerConfig(
                metadata=api_pb2.ContainerMetadata(
                    name=unique_container_name,
                    attempt=int(container_status_dict['metadata'].get('attempt', 1))
                ),
                image=api_pb2.ImageSpec(image=image_ref),
                command=command,
                envs=envs,
                working_dir=runtime_spec.get('process', {}).get('cwd', '/'),
                mounts=mounts,
                linux=api_pb2.LinuxContainerConfig(
                    security_context=api_pb2.LinuxContainerSecurityContext(
                        capabilities=api_pb2.Capability(
                            add_capabilities=capabilities
                        ),
                        # Added namespace options to fix the issue
                        namespace_options=api_pb2.NamespaceOption(
                            network=api_pb2.NamespaceMode.POD,
                            pid=api_pb2.NamespaceMode.POD,
                            ipc=api_pb2.NamespaceMode.POD,
                        ),
                    ),
                ),
                labels=container_status_dict.get('labels', {}),
                annotations=container_status_dict.get('annotations', {}),
                log_path=log_path  # Now a relative path
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
                start_response = runtime_stub.StartContainer(
                    api_pb2.StartContainerRequest(container_id=new_container_id)
                )
                print(f"Container {new_container_id} started and restored from checkpoint.")

            except grpc.RpcError as e:
                print(f"Failed to create or start container {container_id}: {e.code()} - {e.details()}")
                continue

        print("Pod restoration completed on the destination node.")

    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python restore.py <checkpoint_dir>")
        sys.exit(1)
    checkpoint_dir = sys.argv[1]
    restore_pod(checkpoint_dir)
