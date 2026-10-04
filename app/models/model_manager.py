from __future__ import annotations

from app.opencode.client import OpenCodeClient


class ModelManager:
    def __init__(self, client: OpenCodeClient | None = None) -> None:
        self.client = client or OpenCodeClient()

    def list_models(self) -> list[str]:
        models = self.client.available_models()
        return list(models)
