import os
from typing import Dict, List

from migration.pods.base_pod import BasePod
from migration.runtime.v1 import api_pb2


class HttpServerPod(BasePod):
    """A pod running an HTTP server with a log generator."""

    def __init__(
        self,
        name: str = "http-server",
        namespace: str = "default",
        shared_volume_path: str = "/tmp/shared-logs",
        http_port: int = 8080,
    ):
        super().__init__(name, namespace)
        self.shared_volume_path = shared_volume_path
        self.http_port = http_port
        os.makedirs(self.shared_volume_path, exist_ok=True)

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
            # HTTP Server container
            {
                "image": "python:3.9-slim",
                "command": [
                    "python",
                    "-c",
                    f"""
import http.server
import socketserver
PORT = {self.http_port}
Handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving at port {{PORT}}")
    httpd.serve_forever()
                    """,
                ],
                "mounts": [
                    {
                        "container_path": "/shared",
                        "host_path": self.shared_volume_path,
                        "readonly": False,
                    }
                ],
            },
            # Log Generator container
            {
                "image": "python:3.9-slim",
                "command": [
                    "python",
                    "-c",
                    """
import time
import datetime
while True:
    with open('/shared/app.log', 'a') as f:
        timestamp = datetime.datetime.now().isoformat()
        f.write(f"{timestamp}: Log entry\\n")
    time.sleep(1)
                    """,
                ],
                "mounts": [
                    {
                        "container_path": "/shared",
                        "host_path": self.shared_volume_path,
                        "readonly": False,
                    }
                ],
            },
        ]

    def get_labels(self) -> Dict[str, str]:
        return {"app": "http-server", "type": "web"}
