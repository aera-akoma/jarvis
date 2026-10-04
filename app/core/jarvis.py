from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JarvisCore:
    name: str = "Jarvis"
    model_name: str = "OpenCode Zen"
    status: str = "ready"
    session_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def ping(self) -> str:
        return "Jarvis core initialized"
