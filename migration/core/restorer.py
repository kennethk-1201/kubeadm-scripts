import json
import os
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

import grpc

from migration.runtime.v1 import api_pb2, api_pb2_grpc

GRPC_SERVER_ADDRESS = "unix:///var/run/crio/crio.sock"


@dataclass
class PodMetadata:
    name: str
    uid: str
    namespace: str
    attempt: int
    log_directory: str
    labels: Dict[str, str]
    annotations: Dict[str, str]


@dataclass
class ContainerMetadata:
    name: str
    attempt: int
    image: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    log_path: str


def _load_and_sanitize_pod_status(checkpoint_dir: str) -> dict:
    """Stage 1: Load and sanitize pod status data."""
    with open(os.path.join(checkpoint_dir, "pod_status.json"), "r") as f:
        pod_status = json.load(f)

    # Sanitize fields
    for field in ["id", "createdAt", "network"]:
        pod_status.pop(field, None)

    if "linux" in pod_status and "namespaces" in pod_status["linux"]:
        del pod_status["linux"]["namespaces"]

    return pod_status


class PodRestorer:
    """Handles pod restoration operations through a transformation pipeline."""

    def __init__(self):
        self.channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
        self.runtime_stub = api_pb2_grpc.RuntimeServiceStub(self.channel)

    def restore_pod(self, checkpoint_dir: str) -> bool:
        """Main entry point for pod restoration pipeline."""
        try:
            # Pipeline stages
            pod_status = _load_and_sanitize_pod_status(checkpoint_dir)
            pod_metadata = self._extract_pod_metadata(pod_status)
            pod_config = self._transform_to_pod_config(pod_metadata)
            new_pod_id = self._create_pod_sandbox(pod_config)

            if not self._verify_pod_ready(new_pod_id):
                return False

            self._process_containers(checkpoint_dir, new_pod_id, pod_config)
            print("Pod restoration completed on the destination node.")
            return True

        except Exception as e:
            print(f"Error during pod restoration: {e}")
            return False

    @staticmethod
    def _extract_pod_metadata(pod_status: dict) -> PodMetadata:
        """Stage 2: Extract and structure pod metadata."""
        unique_suffix = uuid.uuid4().hex[:6]
        metadata = pod_status.get("metadata", {})

        return PodMetadata(
            name=f"{metadata.get('name', 'pod')}-{unique_suffix}",
            uid=f"{metadata.get('uid', 'uid')}-{unique_suffix}",
            namespace=metadata.get("namespace", "default"),
            attempt=int(metadata.get("attempt", 0)),
            log_directory=pod_status.get("log_directory", "/var/log/pods"),
            labels=pod_status.get("labels", {}),
            annotations=pod_status.get("annotations", {}),
        )

    @staticmethod
    def _transform_to_pod_config(metadata: PodMetadata) -> api_pb2.PodSandboxConfig:
        """Stage 3: Transform metadata into pod config."""
        metadata.labels["restored"] = "true"

        security_context = api_pb2.LinuxSandboxSecurityContext(
            namespace_options=api_pb2.NamespaceOption(
                network=api_pb2.NamespaceMode.POD,
                pid=api_pb2.NamespaceMode.POD,
                ipc=api_pb2.NamespaceMode.POD,
            ),
            seccomp_profile_path="unconfined",
        )

        return api_pb2.PodSandboxConfig(
            metadata=api_pb2.PodSandboxMetadata(
                name=metadata.name,
                uid=metadata.uid,
                namespace=metadata.namespace,
                attempt=metadata.attempt,
            ),
            hostname=f"{metadata.name}-host",
            log_directory=metadata.log_directory,
            dns_config=api_pb2.DNSConfig(),
            port_mappings=[],
            labels=metadata.labels,
            annotations=metadata.annotations,
            linux=api_pb2.LinuxPodSandboxConfig(security_context=security_context),
        )

    def _create_pod_sandbox(self, config: api_pb2.PodSandboxConfig) -> str:
        """Stage 4: Create pod sandbox."""
        response = self.runtime_stub.RunPodSandbox(
            api_pb2.RunPodSandboxRequest(config=config)
        )
        return response.pod_sandbox_id

    def _verify_pod_ready(self, pod_id: str) -> bool:
        """Stage 5: Verify pod readiness."""
        response = self.runtime_stub.PodSandboxStatus(
            api_pb2.PodSandboxStatusRequest(pod_sandbox_id=pod_id)
        )
        return response.status.state == api_pb2.PodSandboxState.SANDBOX_READY

    def _process_containers(
        self, checkpoint_dir: str, pod_id: str, pod_config: api_pb2.PodSandboxConfig
    ):
        """Stage 6: Process and restore containers."""
        container_files = [
            f
            for f in os.listdir(checkpoint_dir)
            if f.endswith("_status.json") and f != "pod_status.json"
        ]

        for status_file in container_files:
            container_id = status_file.replace("_status.json", "")
            container_metadata = self._load_container_metadata(
                checkpoint_dir, status_file
            )

            if not container_metadata:
                continue

            container_config = self._transform_to_container_config(container_metadata)
            self._restore_container(pod_id, container_config, pod_config)

    @staticmethod
    def _load_container_metadata(
        checkpoint_dir: str, status_file: str
    ) -> Optional[ContainerMetadata]:
        """Load and transform container metadata."""
        container_id = status_file.replace("_status.json", "")
        checkpoint_archive = os.path.join(checkpoint_dir, f"{container_id}.tar")

        if not os.path.exists(checkpoint_archive):
            print(f"Checkpoint archive missing for container {container_id}")
            return None

        with open(os.path.join(checkpoint_dir, status_file), "r") as f:
            status = json.load(f)

        if "image" in status:
            status.pop("imageId", None)

        return ContainerMetadata(
            name=f"{status.get('metadata', {}).get('name', 'container')}-{uuid.uuid4().hex[:6]}",
            attempt=int(status.get("metadata", {}).get("attempt", 0)),
            image=checkpoint_archive,
            labels=status.get("labels", {}),
            annotations=status.get(
                "annotations", {"io.kubernetes.cri-o.restore": "true"}
            ),
            log_path=os.path.basename(status.get("logPath", "container.log")),
        )

    @staticmethod
    def _transform_to_container_config(
        metadata: ContainerMetadata,
    ) -> api_pb2.ContainerConfig:
        """Transform container metadata to config."""
        return api_pb2.ContainerConfig(
            metadata=api_pb2.ContainerMetadata(
                name=metadata.name, attempt=metadata.attempt
            ),
            image=api_pb2.ImageSpec(image=metadata.image),
            labels=metadata.labels,
            annotations=metadata.annotations,
            log_path=metadata.log_path,
        )

    def _restore_container(
        self,
        pod_id: str,
        container_config: api_pb2.ContainerConfig,
        pod_config: api_pb2.PodSandboxConfig,
    ):
        """Execute container restoration."""
        try:
            create_response = self.runtime_stub.CreateContainer(
                api_pb2.CreateContainerRequest(
                    pod_sandbox_id=pod_id,
                    config=container_config,
                    sandbox_config=pod_config,
                )
            )

            self.runtime_stub.StartContainer(
                api_pb2.StartContainerRequest(container_id=create_response.container_id)
            )
            print(f"Container {create_response.container_id} restored and started")

        except grpc.RpcError as e:
            print(f"Failed to restore container: {e}")
