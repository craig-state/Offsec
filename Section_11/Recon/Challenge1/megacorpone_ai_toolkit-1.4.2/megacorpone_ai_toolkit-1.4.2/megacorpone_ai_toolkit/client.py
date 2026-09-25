"""MegaCorpOne Inference API client.

Provides a simple interface to the internal model serving endpoint.
Used by engineering workstations and CI pipelines.
"""

import requests
from . import config


class InferenceClient:
    def __init__(self, base_url=None, model=None, timeout=30):
        self.base_url = (base_url or config.INFERENCE_API_URL).rstrip("/")
        self.model = model or config.INFERENCE_MODEL
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers["Authorization"] = "Bearer not-needed"

    def complete(self, prompt, max_tokens=512, temperature=0.7):
        response = self._session.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def models(self):
        response = self._session.get(
            f"{self.base_url}/models",
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["data"]

    def health(self):
        """Return True if the inference server is reachable and serving the expected model."""
        try:
            available = [m["id"] for m in self.models()]
            return self.model in available
        except Exception:
            return False
