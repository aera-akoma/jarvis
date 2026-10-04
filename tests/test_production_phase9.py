import json
import os
import sys

import pytest

from app.logging_setup import configure_logging, install_exception_logging
from app.startup import StartupManager


def test_crash_logs_exclude_exception_message(tmp_path):
    log_path = configure_logging(tmp_path / "logs")
    previous_hook = sys.excepthook
    try:
        install_exception_logging(log_path)
        try:
            raise RuntimeError("sensitive-user-input-should-not-be-logged")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        text = log_path.read_text(encoding="utf-8")
        assert "Uncaught application exception" in text
        assert "sensitive-user-input-should-not-be-logged" not in text
    finally:
        sys.excepthook = previous_hook


def test_packaged_startup_runs_the_executable_directly(tmp_path, monkeypatch):
    manager = StartupManager(str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Jarvis\Jarvis.exe")
    manager.enable_startup()
    script = manager.startup_file.read_text(encoding="utf-8")
    assert '"C:\\Program Files\\Jarvis\\Jarvis.exe"' in script
    assert "-m app" not in script


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI migration test")
def test_legacy_dpapi_credentials_migrate_to_versioned_format(tmp_path):
    import base64
    from app.security.credentials import CredentialStore, _dpapi

    secret = "legacy-protected-api-key"
    encrypted = base64.b64encode(_dpapi(secret.encode(), decrypt=False)).decode("ascii")
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"OpenAI": encrypted}), encoding="utf-8")
    store = CredentialStore(path=str(path))
    assert store.get("OpenAI") == secret
    assert json.loads(path.read_text(encoding="utf-8"))["format"] == "jarvis-windows-dpapi-credentials"
