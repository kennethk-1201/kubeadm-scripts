import grpc

from migration.runtime.v1 import api_pb2, api_pb2_grpc

GRPC_SERVER_ADDRESS = "unix:///var/run/crio/crio.sock"


class PodManager:
    """Manages pod and container lifecycle operations."""

    def __init__(self):
        self.channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
        self.runtime_stub = api_pb2_grpc.RuntimeServiceStub(self.channel)
        self.image_stub = api_pb2_grpc.ImageServiceStub(self.channel)

    def create_pod_from_config(self, pod_config_obj):
        """Create a pod and its containers from a pod configuration object."""
        # Create the pod sandbox
        pod_config = pod_config_obj.get_pod_config()
        pod_id = self.create_pod_sandbox(pod_config)

        container_ids = []
        # Create and start each container
        for container_config in pod_config_obj.get_container_configs():
            container_id = self.create_container(
                pod_sandbox_id=pod_id,
                image_name=container_config["image"],
                pod_config=pod_config,
                command=container_config["command"],
                mounts=container_config.get("mounts"),
            )
            self.manage_container("start", container_id)
            container_ids.append(container_id)

        return pod_id, container_ids

    def create_pod_sandbox(self, pod_config):
        request = api_pb2.RunPodSandboxRequest(config=pod_config)
        response = self.runtime_stub.RunPodSandbox(request)
        print(f"Created pod sandbox with ID: {response.pod_sandbox_id}")
        return response.pod_sandbox_id

    def pull_image(self, image_name):
        request = api_pb2.PullImageRequest(image=api_pb2.ImageSpec(image=image_name))
        self.image_stub.PullImage(request)
        print(f"Pulled image: {image_name}")

    def create_container(
        self, pod_sandbox_id, image_name, pod_config, command, mounts=None
    ):
        self.pull_image(image_name)

        container_config = self._build_container_config(
            image_name=image_name, command=command, mounts=mounts
        )

        request = api_pb2.CreateContainerRequest(
            pod_sandbox_id=pod_sandbox_id,
            config=container_config,
            sandbox_config=pod_config,
        )
        response = self.runtime_stub.CreateContainer(request)
        print(f"Created container with ID: {response.container_id}")
        return response.container_id

    def manage_container(self, action, container_id, timeout=10):
        actions = {
            "start": api_pb2.StartContainerRequest,
            "stop": lambda: api_pb2.StopContainerRequest(
                container_id=container_id, timeout=timeout
            ),
            "remove": api_pb2.RemoveContainerRequest,
        }

        if action not in actions:
            raise ValueError("Invalid action. Choose 'start', 'stop', or 'remove'.")

        request_cls = actions[action]
        request = (
            request_cls(container_id=container_id)
            if callable(request_cls)
            else request_cls(container_id=container_id)
        )

        method_name = f"{action.capitalize()}Container"
        getattr(self.runtime_stub, method_name)(request)
        print(f"{action.capitalize()}ed container with ID: {container_id}")

    def manage_pod(self, action, pod_sandbox_id):
        actions = {
            "stop": api_pb2.StopPodSandboxRequest,
            "remove": api_pb2.RemovePodSandboxRequest,
        }

        if action not in actions:
            raise ValueError("Invalid action. Choose 'stop' or 'remove'.")

        request = actions[action](pod_sandbox_id=pod_sandbox_id)
        method_name = f"{action.capitalize()}PodSandbox"
        getattr(self.runtime_stub, method_name)(request)
        print(f"{action.capitalize()}ed pod sandbox with ID: {pod_sandbox_id}")

    def _build_container_config(self, image_name, command, mounts=None):
        """Helper method to build container configuration."""
        import os
        import uuid

        unique_suffix = uuid.uuid4().hex[:6]
        container_name = f"container_{unique_suffix}"
        log_path = f"container_{unique_suffix}.log"
        os.makedirs(log_path, exist_ok=True)

        mounts_config = []
        if mounts:
            for mount in mounts:
                mounts_config.append(
                    api_pb2.Mount(
                        container_path=mount["container_path"],
                        host_path=mount["host_path"],
                        readonly=mount.get("readonly", False),
                    )
                )

        return api_pb2.ContainerConfig(
            metadata=api_pb2.ContainerMetadata(name=container_name, attempt=0),
            image=api_pb2.ImageSpec(image=image_name),
            command=command,
            log_path=log_path,
            mounts=mounts_config,
            linux=api_pb2.LinuxContainerConfig(
                security_context=api_pb2.LinuxContainerSecurityContext(
                    namespace_options=api_pb2.NamespaceOption(
                        pid=api_pb2.NamespaceMode.POD
                    ),
                    capabilities=api_pb2.Capability(add_capabilities=["CAP_NET_ADMIN"]),
                    privileged=False,
                )
            ),
        )
