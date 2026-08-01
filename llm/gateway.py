import json
import os
import time
import uuid

import requests


class GatewayProvider:
    """Delegates inference to a shared gateway worker (Phase 7)."""

    def __init__(self, gateway_url=None, poll_interval=0.5, timeout=600):
        self.gateway_url = (gateway_url or os.getenv("LLM_GATEWAY_URL", "")).rstrip("/")
        self.poll_interval = poll_interval
        self.timeout = timeout
        self._model = os.getenv("LLM_MODEL") or os.getenv("OLLAMA_MODEL", "qwen2.5vl:32b")

    @property
    def model(self) -> str:
        return self._model

    def _submit(self, job_type: str, payload: dict) -> str:
        response = requests.post(
            f"{self.gateway_url}/jobs",
            json={"type": job_type, "payload": payload, "model": self._model},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["job_id"]

    def _wait(self, job_id: str) -> dict:
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            response = requests.get(f"{self.gateway_url}/jobs/{job_id}", timeout=30)
            response.raise_for_status()
            data = response.json()
            status = data.get("status")
            if status == "complete":
                return data.get("result", {})
            if status == "failed":
                raise RuntimeError(data.get("error", "Gateway job failed"))
            time.sleep(self.poll_interval)
        raise TimeoutError(f"Gateway job {job_id} timed out after {self.timeout}s")

    def complete_json(self, system: str, user: str, schema: dict | None = None) -> dict:
        job_id = self._submit("complete_json", {"system": system, "user": user, "schema": schema})
        result = self._wait(job_id)
        if isinstance(result, str):
            return json.loads(result)
        return result

    def complete_text(self, system: str, user: str) -> str:
        job_id = self._submit("complete_text", {"system": system, "user": user})
        result = self._wait(job_id)
        return result if isinstance(result, str) else str(result)

    def complete_vision(self, prompt: str, image_b64: str) -> str:
        job_id = self._submit("complete_vision", {"prompt": prompt, "image_b64": image_b64})
        result = self._wait(job_id)
        return result if isinstance(result, str) else str(result)
