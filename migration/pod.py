import grpc
import sys
import os
import json

from runtime.v1 import api_pb2, api_pb2_grpc

GRPC_SERVER_ADDRESS = 'unix:///var/run/crio/crio.sock'
IDS_FILE = 'pod_container_ids.json'


class PodSandboxManager:
    def __init__(self, runtime_stub, image_stub):
        self.runtime_stub = runtime_stub
        self.image_stub = image_stub

    def create_pod_sandbox(self, pod_config):
        request = api_pb2.RunPodSandboxRequest(config=pod_config)
        response = self.runtime_stub.RunPodSandbox(request)
        print(f"Created pod sandbox with ID: {response.pod_sandbox_id}")
        return response.pod_sandbox_id

    def get_pod_config(self, name, namespace, uid, stateful=False, annotations=None, labels=None):
        annotations = annotations or {}
        labels = labels or {}
        labels['type'] = 'stateful' if stateful else 'stateless'

        security_context = api_pb2.LinuxSandboxSecurityContext(
            namespace_options=api_pb2.NamespaceOption(
                network=api_pb2.NamespaceMode.POD,
                pid=api_pb2.NamespaceMode.POD,
                ipc=api_pb2.NamespaceMode.POD
            ),
            seccomp_profile_path='unconfined'
        )

        metadata = api_pb2.PodSandboxMetadata(
            name=name,
            namespace=namespace,
            uid=uid,
            attempt=0
        )

        pod_config = api_pb2.PodSandboxConfig(
            metadata=metadata,
            hostname=f"{name}-host",
            log_directory=f"/var/log/pods/{name}",
            labels=labels,
            annotations=annotations,
            linux=api_pb2.LinuxPodSandboxConfig(security_context=security_context)
        )
        return pod_config

    def pull_image(self, image_name):
        request = api_pb2.PullImageRequest(
            image=api_pb2.ImageSpec(image=image_name)
        )
        self.image_stub.PullImage(request)
        print(f"Pulled image: {image_name}")

    def create_container(self, pod_sandbox_id, image_name, pod_config, stateful=False):
        self.pull_image(image_name)

        if stateful:
            command = [
                '/bin/sh', '-c',
                (
                    'counter=0; '
                    'while true; do '
                    'timestamp=$(TZ=Asia/Singapore date "+%Y-%m-%d %H:%M:%S"); '
                    'echo "Counter: $counter | Time: $timestamp"; '
                    'counter=$((counter+1)); sleep 1; '
                    'done'
                )
            ]
        else:
            command = ['/bin/sh', '-c', 'sleep infinity']

        labels = {
            'key': 'value',
            'type': 'stateful' if stateful else 'stateless'
        }

        security_context = api_pb2.LinuxContainerSecurityContext(
            namespace_options=api_pb2.NamespaceOption(pid=api_pb2.NamespaceMode.POD),
            capabilities=api_pb2.Capability(add_capabilities=['CAP_NET_ADMIN']),
            privileged=False
        )

        metadata = api_pb2.ContainerMetadata(
            name='mycontainer',
            attempt=0
        )

        container_config = api_pb2.ContainerConfig(
            metadata=metadata,
            image=api_pb2.ImageSpec(image=image_name),
            command=command,
            labels=labels,
            log_path='mycontainer.log',
            linux=api_pb2.LinuxContainerConfig(security_context=security_context)
        )

        request = api_pb2.CreateContainerRequest(
            pod_sandbox_id=pod_sandbox_id,
            config=container_config,
            sandbox_config=pod_config
        )
        response = self.runtime_stub.CreateContainer(request)
        print(f"Created container with ID: {response.container_id}")
        return response.container_id

    def manage_container(self, action, container_id, timeout=10):
        actions = {
            'start': api_pb2.StartContainerRequest,
            'stop': lambda: api_pb2.StopContainerRequest(container_id=container_id, timeout=timeout),
            'remove': api_pb2.RemoveContainerRequest
        }

        if action not in actions:
            raise ValueError("Invalid action. Choose 'start', 'stop', or 'remove'.")

        request_cls = actions[action]
        request = request_cls(container_id=container_id) if callable(request_cls) else request_cls(container_id=container_id)

        method_name = f"{action.capitalize()}Container"
        getattr(self.runtime_stub, method_name)(request)
        print(f"{action.capitalize()}ed container with ID: {container_id}")

    def manage_pod(self, action, pod_sandbox_id):
        actions = {
            'stop': api_pb2.StopPodSandboxRequest,
            'remove': api_pb2.RemovePodSandboxRequest
        }

        if action not in actions:
            raise ValueError("Invalid action. Choose 'stop' or 'remove'.")

        request = actions[action](pod_sandbox_id=pod_sandbox_id)
        method_name = f"{action.capitalize()}PodSandbox"
        getattr(self.runtime_stub, method_name)(request)
        print(f"{action.capitalize()}ed pod sandbox with ID: {pod_sandbox_id}")


def load_ids():
    if not os.path.exists(IDS_FILE):
        print("No pod and container IDs found. Please start first.")
        sys.exit(1)
    with open(IDS_FILE, 'r') as f:
        return json.load(f)


def save_ids(pod_id, container_id):
    with open(IDS_FILE, 'w') as f:
        json.dump({'pod_sandbox_id': pod_id, 'container_id': container_id}, f)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 script.py [start-stateful|start-stateless|teardown]")
        sys.exit(1)

    action = sys.argv[1]
    channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
    runtime_stub = api_pb2_grpc.RuntimeServiceStub(channel)
    image_stub = api_pb2_grpc.ImageServiceStub(channel)
    manager = PodSandboxManager(runtime_stub, image_stub)

    try:
        if action in ['start-stateful', 'start-stateless']:
            stateful = (action == 'start-stateful')
            name = 'stateful-pod' if stateful else 'stateless-pod'
            namespace = 'default'
            uid = f"{name}-uid"
            annotations = {'stateful': 'true'} if stateful else {'stateful': 'false'}

            pod_config = manager.get_pod_config(
                name=name,
                namespace=namespace,
                uid=uid,
                stateful=stateful,
                annotations=annotations
            )
            pod_id = manager.create_pod_sandbox(pod_config)
            container_id = manager.create_container(
                pod_sandbox_id=pod_id,
                image_name='docker.io/library/busybox:latest',
                pod_config=pod_config,
                stateful=stateful
            )
            manager.manage_container('start', container_id)
            save_ids(pod_id, container_id)
            print(f"Started {'stateful' if stateful else 'stateless'} pod and container. "
                  f"Pod ID: {pod_id}, Container ID: {container_id}")

        elif action == 'teardown':
            ids = load_ids()
            container_id = ids['container_id']
            pod_id = ids['pod_sandbox_id']

            manager.manage_container('stop', container_id)
            manager.manage_container('remove', container_id)
            manager.manage_pod('stop', pod_id)
            manager.manage_pod('remove', pod_id)
            os.remove(IDS_FILE)
            print("Pod and container torn down successfully.")

        else:
            print("Invalid action. Use 'start-stateful', 'start-stateless', or 'teardown'.")

    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
