from __future__ import annotations

import base64
import json
from pathlib import Path
import os

try:
    import win32crypt
except ImportError:  # pragma: no cover - not available on non-Windows
    win32crypt = None


class CredentialStore:
    def __init__(self, path: str | None = None) -> None:
        if path is None:
            base = Path.home() / "AppData" / "Roaming" / "Jarvis"
            base.mkdir(parents=True, exist_ok=True)
            self.path = base / "credentials.json"
        else:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._store: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                self._store = {str(k): str(v) for k, v in payload.items()}
        except (TypeError, ValueError, OSError):
            self._store = {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._store, indent=2), encoding="utf-8")

    def set(self, key: str, value: str) -> None:
        if os.name == "nt" and win32crypt is not None:
            blob = win32crypt.CryptProtectData(value.encode("utf-8"), None, None, None, None, 0)
            self._store[key] = base64.b64encode(blob).decode("ascii")
        else:
            self._store[key] = value
        self._save()

    def get(self, key: str) -> str | None:
        value = self._store.get(key)
        if value is None:
            return None
        if os.name == "nt" and win32crypt is not None:
            try:
                decoded = base64.b64decode(value.encode("ascii"))
                unprotected = win32crypt.CryptUnprotectData(decoded, None, None, None, 0)[1]
                return unprotected.decode("utf-8")
            except Exception:
                return value
        return value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._save()
