import sys

import grpc
import os
import json
import uuid

import runtime.v1.api_pb2 as api_pb2
import runtime.v1.api_pb2_grpc as api_pb2_grpc

GRPC_SERVER_ADDRESS = 'unix:///var/run/crio/crio.sock'
CHECKPOINT_DIR = '/tmp/pod_checkpoint'
POD_STATUS_PATH = os.path.join(CHECKPOINT_DIR, 'pod_status.json')

channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
runtime_stub = api_pb2_grpc.RuntimeServiceStub(channel)

with open(POD_STATUS_PATH, 'r') as f:
    pod_status_dict = json.load(f)

# Generate unique identifiers
unique_suffix = uuid.uuid4().hex[:6]

# Extract frequently accessed keys
metadata = pod_status_dict.get('metadata', {})
labels = pod_status_dict.get('labels', {})
annotations = pod_status_dict.get('annotations', {})
namespace = metadata.get('namespace', '')
attempt = int(metadata.get('attempt', 1))

# Generate unique pod name and UID
new_pod_name = f"{metadata.get('name', 'default_name')}-{unique_suffix}"
new_pod_uid = f"{metadata.get('uid', 'default_uid')}-{unique_suffix}"

# Configure log directory with a default fallback
log_directory = pod_status_dict.get('log_directory', '/var/log/pods')

# Create PodSandboxConfig with standardized key access
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
    linux=api_pb2.LinuxPodSandboxConfig()
)

# Ensure the log_directory exists
os.makedirs(log_directory, exist_ok=True)

run_pod_request = api_pb2.RunPodSandboxRequest(
    config=pod_sandbox_config,
)
run_pod_response = runtime_stub.RunPodSandbox(run_pod_request)
run_pod_id = run_pod_response.pod_sandbox_id
print(f"Created pod sandbox with ID: {run_pod_id}")

pod_status = runtime_stub.PodSandboxStatus(
    api_pb2.PodSandboxStatusRequest(pod_sandbox_id=run_pod_id)
)

if pod_status.status.state != api_pb2.PodSandboxState.SANDBOX_READY:
    print(f"Error: Pod sandbox {run_pod_id} is not in a ready state.")
    sys.exit(1)

for filename in os.listdir(CHECKPOINT_DIR):
    if not filename.endswith('_status.json') or filename == 'pod_status.json':
        continue

    container_id = filename.replace('_status.json', '')
    CONTAINER_STATUS_PATH = os.path.join(CHECKPOINT_DIR, filename)

    checkpoint_archive_name = f"{container_id}.tar"
    CHECKPOINT_PATH = os.path.abspath(os.path.join(CHECKPOINT_DIR, checkpoint_archive_name))

    if not os.path.exists(CHECKPOINT_PATH):
        print(f"Error: Container checkpoint {CHECKPOINT_PATH} does not exist.")
        sys.exit(1)

    with open(CONTAINER_STATUS_PATH, 'r') as f:
        container_status_dict = json.load(f)

    image_ref = container_status_dict.get('image', {}).get('image')

    # TODO: Pull image

    container_metadata = container_status_dict.get('metadata', {})
    unique_container_name = f"{container_metadata.get('name')}-{unique_suffix}"

    # Use a relative path for log_path
    log_path = container_status_dict.get('logPath', 'container.log')
    log_path = os.path.basename(log_path)

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

    # Prepare the container mounts
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
                namespace_options=api_pb2.NamespaceOption(
                    network=api_pb2.NamespaceMode.POD,
                    pid=api_pb2.NamespaceMode.POD,
                    ipc=api_pb2.NamespaceMode.POD,
                ),
            ),
        ),
        labels=container_status_dict.get('labels', {}),
        annotations=container_status_dict.get('annotations', {}),
        log_path=log_path
    )

    try:
        # Create the container
        create_container_response = runtime_stub.CreateContainer(
            api_pb2.CreateContainerRequest(
                pod_sandbox_id=run_pod_id,
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