"""Utility functions for validating pod and container configurations."""

def validate_pod_config(pod_config):
    """Validate pod configuration."""
    required_fields = ["metadata", "linux"]
    for field in required_fields:
        if not hasattr(pod_config, field):
            raise ValueError(f"Missing required field: {field}")

def validate_container_config(container_config):
    """Validate container configuration."""
    required_fields = ["metadata", "image", "command"]
    for field in required_fields:
        if not container_config.get(field):
            raise ValueError(f"Missing required field: {field}")
