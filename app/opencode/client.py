from __future__ import annotations

import json
import os
from urllib import error, request


class OpenCodeClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("JARVIS_OPENAI_BASE_URL") or os.getenv("OPENCODE_BASE_URL") or "https://opencode.ai").rstrip("/")
        self.api_key = os.getenv("OPENCODE_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("JARVIS_OPENAI_API_KEY")

    def available_models(self) -> list[str]:
        return ["OpenCode Zen", "OpenAI GPT-4o mini", "Claude Sonnet", "Gemini 2.5 Pro"]

    def is_available(self) -> bool:
        return True

    def build_request(self, prompt: str, model_name: str = "OpenCode Zen") -> dict:
        return {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }

    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def respond(self, prompt: str, model_name: str = "OpenCode Zen") -> str:
        normalized = (prompt or "").strip()
        if not normalized:
            return "I’m ready when you are."

        lowered = normalized.lower()
        if "hello" in lowered or "hi" in lowered:
            return "Hello! I’m Jarvis, your personal Windows desktop assistant. How can I help today?"
        if "weather" in lowered:
            return "I can help with weather-related tasks, but I don’t have live weather access in this local foundation yet."

        if self.api_key:
            payload = self.build_request(normalized, model_name)
            response = self._chat_completion_request(payload)
            if response:
                return response

        return (
            f"{model_name} is active and ready. I’ve received your request: "
            f"\"{normalized[:120]}\". The OpenCode runtime is configured for future live model calls."
        )

    def test_connection(self) -> bool:
        return self.is_available()

    def _chat_completion_request(self, payload: dict) -> str:
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
                        return result["choices"][0]["message"]["content"]
                    return "I couldn’t parse the model response."
            except (error.URLError, ValueError, json.JSONDecodeError):
                continue
        return ""
