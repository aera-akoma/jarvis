from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import json
import os
from pathlib import Path
import secrets


_FORMAT = "jarvis-windows-dpapi-credentials"


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Secure credential storage is available only through Windows DPAPI.")

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    source_buffer = ctypes.create_string_buffer(data)
    source = DataBlob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    destination = DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if decrypt:
        function = crypt32.CryptUnprotectData
        function.argtypes = [ctypes.POINTER(DataBlob), ctypes.POINTER(ctypes.wintypes.LPWSTR),
                             ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.wintypes.DWORD, ctypes.POINTER(DataBlob)]
        success = function(ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(destination))
    else:
        function = crypt32.CryptProtectData
        function.argtypes = [ctypes.POINTER(DataBlob), ctypes.wintypes.LPCWSTR,
                             ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.wintypes.DWORD, ctypes.POINTER(DataBlob)]
        success = function(ctypes.byref(source), "Jarvis credential", None, None, None, 0x1, ctypes.byref(destination))
    function.restype = ctypes.wintypes.BOOL
    if not success:
        raise OSError(ctypes.get_last_error(), "Windows could not access the protected credential.")
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(ctypes.cast(destination.pbData, ctypes.c_void_p))


class CredentialStore:
    """Fail-closed credential storage protected with the current Windows user DPAPI key."""

    def __init__(self, path: str | None = None) -> None:
        if path is None:
            base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "Jarvis"
            base.mkdir(parents=True, exist_ok=True)
            self.path = base / "credentials.json"
        else:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._store: dict[str, str] = {}
        self.storage_error: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("format") != _FORMAT or payload.get("version") != 1 or not isinstance(payload.get("entries"), dict):
                raise ValueError("Credential file is not in the protected Jarvis format.")
            self._store = {
                str(key): base64.b64encode(_dpapi(base64.b64decode(value, validate=True), decrypt=True)).decode("ascii")
                for key, value in payload["entries"].items()
                if isinstance(value, str)
            }
            # Cache decrypted bytes only in memory as base64; they are never written back as plaintext.
            self._store = {key: base64.b64encode(base64.b64decode(value)).decode("ascii") for key, value in self._store.items()}
        except Exception:
            self._store.clear()
            self.storage_error = (
                "Saved credentials could not be verified as Windows-protected data. "
                "Jarvis will not load or overwrite that file; remove or back it up manually, then re-enter credentials."
            )

    def _require_available(self) -> None:
        if self.storage_error:
            raise RuntimeError(self.storage_error)
        if os.name != "nt":
            raise RuntimeError("Jarvis refuses to store credentials without Windows DPAPI secure storage.")

    def _save(self) -> None:
        self._require_available()
        entries = {
            key: base64.b64encode(_dpapi(base64.b64decode(value), decrypt=False)).decode("ascii")
            for key, value in self._store.items()
        }
        payload = json.dumps({"format": _FORMAT, "version": 1, "entries": entries}, indent=2)
        temporary = self.path.with_name(self.path.name + f".{secrets.token_hex(6)}.tmp")
        try:
            temporary.write_text(payload, encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def set(self, key: str, value: str) -> None:
        self._require_available()
        # Keep a base64 representation only in process memory to avoid accidental text serialization.
        self._store[key] = base64.b64encode(value.encode("utf-8")).decode("ascii")
        self._save()

    def get(self, key: str) -> str | None:
        self._require_available()
        value = self._store.get(key)
        if value is None:
            return None
        try:
            return base64.b64decode(value, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise RuntimeError("The stored credential could not be decoded safely.") from exc

    def delete(self, key: str) -> None:
        self._require_available()
        self._store.pop(key, None)
        self._save()
