from __future__ import annotations

import json
import os
import uuid
from urllib import error, request


class OpenCodeClient:
    DEFAULT_MODEL = "OpenCode Zen"

    def __init__(self, base_url: str | None = None) -> None:
        raw_base_url = base_url or os.getenv("JARVIS_OPENAI_BASE_URL") or os.getenv("OPENCODE_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        self.base_url = raw_base_url.rstrip("/") if raw_base_url else None
        self.api_key = os.getenv("OPENCODE_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("JARVIS_OPENAI_API_KEY")
        self.session_id: str | None = None
        self.last_error: str | None = None
        self._model_cache: list[str] = []

    def create_session(self) -> str:
        self.session_id = uuid.uuid4().hex
        return self.session_id

    def _runtime_urls(self) -> list[str]:
        if not self.base_url:
            return []
        urls = {self.base_url}
        for suffix in ("/v1", "/api", "/openai", "/openai/v1", "/inference/openai/v1"):
            urls.add(self.base_url.rstrip("/") + suffix)
        return sorted(urls)

    def _coerce_models(self, payload: object) -> list[str]:
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get("data") or payload.get("models") or payload.get("items") or []
        else:
            return []

        models: list[str] = []
        for item in items:
            if isinstance(item, str):
                models.append(item)
            elif isinstance(item, dict):
                if item.get("id"):
                    models.append(str(item["id"]))
                elif item.get("name"):
                    models.append(str(item["name"]))
        return models

    def discover_models(self) -> list[str]:
        if not self.base_url:
            self._model_cache = []
            self.last_error = "OpenCode runtime unavailable. Configure JARVIS_OPENAI_BASE_URL first."
            return []

        self.last_error = None
        for root in self._runtime_urls():
            for suffix in ("", "/models", "/v1/models", "/api/models", "/openai/v1/models", "/inference/openai/v1/models"):
                endpoint = root.rstrip("/") + suffix
                req = request.Request(endpoint, headers=self.headers(), method="GET")
                try:
                    with request.urlopen(req, timeout=10) as response:
                        body = response.read().decode("utf-8", errors="replace")
                        payload = json.loads(body)
                        models = self._coerce_models(payload)
                        if models:
                            self._model_cache = models
                            return models
                except (error.URLError, ValueError, json.JSONDecodeError, OSError):
                    continue

        self._model_cache = []
        self.last_error = "OpenCode runtime unavailable. No model catalog was returned from the configured runtime."
        return []

    def available_models(self) -> list[str]:
        return self.discover_models() or self._model_cache

    def is_available(self) -> bool:
        return bool(self.available_models())

    def test_connection(self) -> bool:
        return self.is_available()

    def build_request(self, prompt: str, model_name: str = DEFAULT_MODEL) -> dict:
        return {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }

    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def respond(self, prompt: str, model_name: str = DEFAULT_MODEL) -> str:
        normalized = (prompt or "").strip()
        if not normalized:
            return "Please provide a prompt before sending it to the model."

        if not self.base_url:
            return "Jarvis is ready, but the OpenCode runtime unavailable. Configure the OpenCode runtime URL and credentials before sending chat requests."

        available = self.available_models()
        if not available:
            return "Jarvis is ready, but the OpenCode runtime unavailable. No model catalog was returned from the configured runtime."

        selected_model = model_name or available[0]
        if selected_model not in available:
            selected_model = available[0]

        payload = self.build_request(normalized, selected_model)
        response = self._chat_completion_request(payload)
        if response:
            return response

        return "Jarvis is ready, but the OpenCode request failed. The runtime is reachable but did not return a valid model response."

    def _chat_completion_request(self, payload: dict) -> str:
        if not self.base_url:
            return ""

        candidate_endpoints = [
            f"{self.base_url}/chat/completions",
            f"{self.base_url}/v1/chat/completions",
            f"{self.base_url}/openai/v1/chat/completions",
            f"{self.base_url}/inference/openai/v1/chat/completions",
        ]

        for endpoint in candidate_endpoints:
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(endpoint, data=data, headers=self.headers(), method="POST")
            try:
                with request.urlopen(req, timeout=15) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    result = json.loads(body)
                    if "choices" in result and result["choices"]:
                        message = result["choices"][0].get("message") or {}
                        return str(message.get("content") or "")
                    if "content" in result and isinstance(result["content"], str):
                        return result["content"]
                    if "error" in result:
                        detail = result["error"]
                        if isinstance(detail, dict):
                            return f"OpenCode runtime error: {detail.get('message', 'unknown error')}"
                        return f"OpenCode runtime error: {detail}"
            except (error.HTTPError, error.URLError, ValueError, json.JSONDecodeError):
                continue
        return ""
