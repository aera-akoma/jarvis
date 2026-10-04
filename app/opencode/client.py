from __future__ import annotations

import json
import http.client
import os
import threading
import uuid
from urllib import error, request
from urllib import request as request_module
from urllib.parse import urlsplit

from app.security.credentials import CredentialStore


class OpenCodeClient:
    DEFAULT_MODEL = "OpenCode Zen"

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        raw_base_url = base_url or os.getenv("JARVIS_OPENAI_BASE_URL") or os.getenv("OPENCODE_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        self.base_url = raw_base_url.rstrip("/") if raw_base_url else None
        stored_key = None
        if api_key is None and not (os.getenv("OPENCODE_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("JARVIS_OPENAI_API_KEY")):
            try:
                stored_key = CredentialStore().get("OpenAI")
            except OSError:
                stored_key = None
        self.api_key = api_key or os.getenv("OPENCODE_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("JARVIS_OPENAI_API_KEY") or stored_key
        self.session_id: str | None = None
        self.last_error: str | None = None
        self._model_cache: list[str] = []
        self._active_connection: http.client.HTTPConnection | None = None
        self._connection_lock = threading.Lock()
        self._request_cancelled = threading.Event()

    def cancel_current_request(self) -> None:
        """Close the active HTTP socket so STOP interrupts a pending response."""
        self._request_cancelled.set()
        with self._connection_lock:
            connection = self._active_connection
        if connection is None:
            return
        sock = connection.sock
        if sock is not None:
            try:
                sock.shutdown(2)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        connection.close()

    def _post_json(self, endpoint: str, payload: dict) -> dict:
        parts = urlsplit(endpoint)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("The configured model endpoint must be an HTTP(S) URL.")
        connection_type = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(parts.hostname, parts.port, timeout=30)
        with self._connection_lock:
            self._active_connection = connection
        try:
            if self._request_cancelled.is_set():
                raise InterruptedError("Model request cancelled.")
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            connection.request("POST", path, body=json.dumps(payload).encode("utf-8"), headers=self.headers())
            if self._request_cancelled.is_set():
                raise InterruptedError("Model request cancelled.")
            response = connection.getresponse()
            body = response.read().decode("utf-8", errors="replace")
            if response.status >= 400:
                raise ValueError(f"HTTP {response.status}: {body[:500]}")
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError("The model endpoint returned a non-object JSON response.")
            return result
        finally:
            with self._connection_lock:
                if self._active_connection is connection:
                    self._active_connection = None
            connection.close()

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
                req = request_module.Request(endpoint, headers=self.headers(), method="GET")
                try:
                    with request_module.urlopen(req, timeout=10) as response:
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

    def request_tool_decision(self, *, request: str, model_name: str, tools: list[dict], messages: list[dict], system_prompt: str) -> dict:
        """Call the configured chat-completions endpoint using its tool API."""
        self._request_cancelled.clear()
        if not self.base_url:
            return {"error": "No model API endpoint is configured. Set JARVIS_OPENAI_BASE_URL to a provider endpoint that supports chat completions and tool calls."}
        api_tools = []
        for tool in tools:
            integer_parameters = {"x", "y", "width", "height", "clicks"}
            properties = {
                key: {"type": "integer" if key in integer_parameters else "string", "description": description}
                for key, description in tool.get("parameters", {}).items()
            }
            api_tools.append({"type": "function", "function": {
                "name": tool["name"], "description": tool.get("description", ""),
                "parameters": {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False},
            }})
        prior = []
        tool_call_index = 0
        for message in messages:
            if message.get("role") == "assistant":
                call = message["tool_call"]
                tool_call_id = f"jarvis-tool-{tool_call_index}"
                tool_call_index += 1
                prior.append({"role": "assistant", "tool_calls": [{"id": tool_call_id, "type": "function", "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])} }]})
            elif message.get("role") == "tool":
                prior.append({"role": "tool", "tool_call_id": f"jarvis-tool-{tool_call_index - 1}", "content": message["content"]})
        payload = {"model": model_name, "temperature": 0.2,
                   "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": request}, *prior],
                   "tools": api_tools, "tool_choice": "auto"}
        last_error = None
        for endpoint in (f"{self.base_url}/chat/completions", f"{self.base_url}/v1/chat/completions", f"{self.base_url}/openai/v1/chat/completions"):
            try:
                body = self._post_json(endpoint, payload)
                message = body["choices"][0]["message"]
                calls = message.get("tool_calls") or []
                if calls:
                    function = calls[0].get("function", {})
                    return {"tool": function.get("name"), "arguments": json.loads(function.get("arguments") or "{}")}
                return {"final_response": str(message.get("content") or "The model returned an empty response.")}
            except (error.HTTPError, error.URLError, http.client.HTTPException, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                last_error = exc
                if self._request_cancelled.is_set():
                    break
        self.last_error = f"Tool-calling model request failed: {last_error}"
        return {"error": self.last_error}

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
            req = request_module.Request(endpoint, data=data, headers=self.headers(), method="POST")
            try:
                with request_module.urlopen(req, timeout=15) as response:
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
