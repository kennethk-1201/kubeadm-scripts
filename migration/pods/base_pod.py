from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from migration.runtime.v1 import api_pb2


class BasePod(ABC):
    """Base class for all pod configurations."""

    def __init__(self, name: str, namespace: str = "default"):
        self.name = name
        self.namespace = namespace
        self.uid = f"{name}-{namespace}"

    @abstractmethod
    def get_pod_config(self) -> api_pb2.PodSandboxConfig:
        """Return the pod sandbox configuration."""
        pass

    @abstractmethod
    def get_container_configs(self) -> List[Dict]:
        """
        Return a list of container configurations.
        Each config should be a dict with:
        {
            'image': str,
            'command': List[str],
            'mounts': Optional[List[Dict]],
            'env': Optional[Dict[str, str]]
        }
        """
        pass

    def get_annotations(self) -> Dict[str, str]:
        """Return pod annotations. Override if needed."""
        return {}

    def get_labels(self) -> Dict[str, str]:
        """Return pod labels. Override if needed."""
        return {}

    @staticmethod
    def get_security_context() -> api_pb2.LinuxSandboxSecurityContext:
        """Return the default security context. Override if needed."""
        return api_pb2.LinuxSandboxSecurityContext(
            namespace_options=api_pb2.NamespaceOption(
                network=api_pb2.NamespaceMode.POD,
                pid=api_pb2.NamespaceMode.POD,
                ipc=api_pb2.NamespaceMode.POD,
            ),
            seccomp_profile_path="unconfined",
        )
