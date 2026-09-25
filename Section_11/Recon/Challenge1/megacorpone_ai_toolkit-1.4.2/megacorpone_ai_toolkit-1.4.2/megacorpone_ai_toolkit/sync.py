"""Model sync and health check module.

Runs periodically via scheduled task on engineering workstations.
Checks inference server availability, caches the model list locally,
and logs a heartbeat for fleet visibility.
"""

import datetime
import json
import os
import platform
import socket
import sys

from . import config
from .client import InferenceClient


def get_hostname():
    return platform.node()


def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("172.16.50.40", 53))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


def _data_dir():
    return os.path.join(os.path.expanduser("~"), ".megacorpone-ai-toolkit")


def sync_models():
    """Fetch available models from the inference server and cache locally."""
    client = InferenceClient()
    models = client.models()

    data_dir = _data_dir()
    os.makedirs(data_dir, exist_ok=True)

    cache = {
        "synced_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoint": config.INFERENCE_API_URL,
        "models": models,
    }
    with open(os.path.join(data_dir, "models.json"), "w") as f:
        json.dump(cache, f, indent=2)

    return models


def log_heartbeat(status="sync_complete", model_count=0):
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    hostname = get_hostname()
    ip = get_ip()
    user = os.environ.get("USERNAME", os.environ.get("USER", "unknown"))

    from . import __version__
    entry = (
        f"{timestamp} | hostname={hostname} | ip={ip} | user={user} "
        f"| pkg={config.PACKAGE_NAME} | version={__version__} "
        f"| models={model_count} | status={status}"
    )
    print(entry)

    data_dir = _data_dir()
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "sync.log"), "a") as f:
        f.write(entry + "\n")


def main():
    try:
        models = sync_models()
        log_heartbeat("sync_complete", model_count=len(models))
    except Exception as e:
        log_heartbeat(f"sync_error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
