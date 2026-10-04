from __future__ import annotations


class ModelManager:
    def __init__(self) -> None:
        self.available_models = [
            "OpenCode Zen",
            "OpenAI GPT-4o mini",
            "Claude Sonnet",
            "Gemini 2.5 Pro",
        ]

    def list_models(self) -> list[str]:
        return list(self.available_models)
