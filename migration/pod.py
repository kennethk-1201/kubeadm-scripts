import grpc
import sys
import os
import json

import runtime.v1.api_pb2 as api_pb2
import runtime.v1.api_pb2_grpc as api_pb2_grpc

GRPC_SERVER_ADDRESS = 'unix:///var/run/crio/crio.sock'


class PodSandboxManager:
    def __init__(self, runtime_stub, image_stub):
        self.runtime_stub = runtime_stub
        self.image_stub = image_stub

    def create_pod_sandbox(self, pod_config):
        request = api_pb2.RunPodSandboxRequest(config=pod_config, runtime_handler='')
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
        return api_pb2.PodSandboxConfig(
            metadata=api_pb2.PodSandboxMetadata(name=name, namespace=namespace, uid=uid, attempt=0),
            hostname=f"{name}-host",
            log_directory=f"/var/log/pods/{name}",
            labels=labels,
            annotations=annotations,
            linux=api_pb2.LinuxPodSandboxConfig(security_context=security_context)
        )

    def create_container(self, pod_sandbox_id, image_name, pod_config, stateful=False):
        self.pull_image(image_name)

        # Command to run a counter process
        command = [
            '/bin/sh', '-c',
            'counter=0; while true; do echo "Counter: $counter"; counter=$((counter+1)); sleep 1; done'
        ]

        container_config = api_pb2.ContainerConfig(
            metadata=api_pb2.ContainerMetadata(name='mycontainer', attempt=0),
            image=api_pb2.ImageSpec(image=image_name),
            command=command,
            labels={'key': 'value', 'type': 'stateful' if stateful else 'stateless'},
            log_path='mycontainer.log',
            linux=api_pb2.LinuxContainerConfig(
                security_context=api_pb2.LinuxContainerSecurityContext(
                    namespace_options=api_pb2.NamespaceOption(pid=api_pb2.NamespaceMode.POD),
                    privileged=False,
                    capabilities=api_pb2.Capability(add_capabilities=['CAP_NET_ADMIN']),
                ),
            )
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
        request = actions[action](container_id=container_id)
        getattr(self.runtime_stub, f"{action.capitalize()}Container")(request)
        print(f"{action.capitalize()}ed container with ID: {container_id}")

    def manage_pod(self, action, pod_sandbox_id):
        actions = {
            'stop': api_pb2.StopPodSandboxRequest,
            'remove': api_pb2.RemovePodSandboxRequest
        }
        if action not in actions:
            raise ValueError("Invalid action. Choose 'stop' or 'remove'.")
        request = actions[action](pod_sandbox_id=pod_sandbox_id)
        getattr(self.runtime_stub, f"{action.capitalize()}PodSandbox")(request)
        print(f"{action.capitalize()}ped pod sandbox with ID: {pod_sandbox_id}")

    def pull_image(self, image_name):
        request = api_pb2.PullImageRequest(image=api_pb2.ImageSpec(image=image_name))
        self.image_stub.PullImage(request)
        print(f"Pulled image: {image_name}")


def load_ids():
    if not os.path.exists('pod_container_ids.json'):
        print("No pod and container IDs found. Please start first.")
        sys.exit(1)
    with open('pod_container_ids.json', 'r') as f:
        return json.load(f)


def save_ids(pod_id, container_id):
    with open('pod_container_ids.json', 'w') as f:
        json.dump({'pod_sandbox_id': pod_id, 'container_id': container_id}, f)


def main():
    channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
    runtime_stub = api_pb2_grpc.RuntimeServiceStub(channel)
    image_stub = api_pb2_grpc.ImageServiceStub(channel)
    manager = PodSandboxManager(runtime_stub, image_stub)

    try:
        if len(sys.argv) < 2:
            print("Usage: python3 script.py [start-stateful|teardown]")
            sys.exit(1)
        action = sys.argv[1]

        if action == 'start-stateful':
            name = 'stateful-pod'
            namespace = 'default'
            uid = f"{name}-uid"
            annotations = {'stateful': 'true'}

            pod_config = manager.get_pod_config(name, namespace, uid, stateful=True, annotations=annotations)
            pod_id = manager.create_pod_sandbox(pod_config)
            container_id = manager.create_container(
                pod_id, 'docker.io/library/busybox:latest', pod_config, stateful=True
            )
            manager.manage_container('start', container_id)
            save_ids(pod_id, container_id)
            print(f"Started stateful pod and container. Pod ID: {pod_id}, Container ID: {container_id}")

        elif action == 'teardown':
            ids = load_ids()
            manager.manage_container('stop', ids['container_id'])
            manager.manage_container('remove', ids['container_id'])
            manager.manage_pod('stop', ids['pod_sandbox_id'])
            manager.manage_pod('remove', ids['pod_sandbox_id'])
            os.remove('pod_container_ids.json')
            print("Pod and container torn down successfully.")

        else:
            print("Invalid action. Use 'start-stateful' or 'teardown'.")

    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
