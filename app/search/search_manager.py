from __future__ import annotations

import re
from typing import Any


class SearchManager:
    def __init__(self) -> None:
        self.index = {
            "Jarvis": "A local desktop AI assistant built with Python and PySide6.",
            "desktop": "A native Windows desktop interface for personal AI tasks.",
            "OpenCode": "A runtime layer for model access and AI orchestration.",
            "memory": "Durable local memory stores user preferences and recurring tasks.",
            "workflow": "Saved local steps for common repetitive actions.",
        }

    def search(self, query: str) -> list[dict[str, Any]]:
        if not query:
            return []
        needles = [part.lower() for part in query.split() if part.strip()]
        if not needles:
            return []

        results: list[dict[str, Any]] = []
        for key, value in self.index.items():
            haystack = f"{key.lower()} {value.lower()}"
            if any(needle in haystack for needle in needles):
                results.append({"title": key, "snippet": value})
        return results
