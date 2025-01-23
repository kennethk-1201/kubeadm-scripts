from typing import Dict, List

from migration.pods.base_pod import BasePod
from migration.runtime.v1 import api_pb2


class CounterPod(BasePod):
    """A pod running a simple counter."""

    def get_pod_config(self) -> api_pb2.PodSandboxConfig:
        return api_pb2.PodSandboxConfig(
            metadata=api_pb2.PodSandboxMetadata(
                name=self.name,
                namespace=self.namespace,
                uid=self.uid,
                attempt=0,
            ),
            hostname=f"{self.name}-host",
            log_directory=f"/var/log/pods/{self.name}",
            labels=self.get_labels(),
            annotations=self.get_annotations(),
            linux=api_pb2.LinuxPodSandboxConfig(
                security_context=self.get_security_context()
            ),
        )

    def get_container_configs(self) -> List[Dict]:
        return [
            {
                "image": "python:3.9-slim",
                "command": [
                    "/bin/sh",
                    "-c",
                    "counter=0; "
                    "while true; do "
                    'timestamp=$(TZ=Asia/Singapore date "+%Y-%m-%d %H:%M:%S"); '
                    'echo "Counter: $counter | Time: $timestamp"; '
                    "counter=$((counter+1)); "
                    "sleep 1; "
                    "done",
                ],
            }
        ]

    def get_labels(self) -> Dict[str, str]:
        return {"app": "counter", "type": "stateful"}
