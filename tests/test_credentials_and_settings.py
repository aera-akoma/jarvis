import os

import pytest

from app.config import AppConfig
from app.core.settings_manager import SettingsManager
from app.security.credentials import CredentialStore


def test_settings_manager_round_trip(tmp_path):
    config = AppConfig(data_dir=str(tmp_path))
    settings = SettingsManager(config)
    settings.set("theme", "light")
    settings.set("default_model", "Claude Sonnet")

    assert settings.get("theme") == "light"
    assert settings.get("default_model") == "Claude Sonnet"


@pytest.mark.skipif(os.name != "nt", reason="Credential round trip requires Windows DPAPI")
def test_credential_store_round_trip(tmp_path):
    store = CredentialStore(path=str(tmp_path / "credentials.json"))
    store.set("OpenAI", "demo-key")
    assert store.get("OpenAI") == "demo-key"

    store.delete("OpenAI")
    assert store.get("OpenAI") is None


@pytest.mark.skipif(os.name != "nt", reason="Credential protection requires Windows DPAPI")
def test_credential_store_persists_only_protected_ciphertext(tmp_path):
    import json

    secret = "a-realistic-private-api-key"
    path = tmp_path / "credentials.json"
    store = CredentialStore(path=str(path))
    store.set("OpenAI", secret)
    content = path.read_text(encoding="utf-8")
    assert secret not in content
    payload = json.loads(content)
    assert payload["format"] == "jarvis-windows-dpapi-credentials"
    assert store.get("OpenAI") == secret


def test_credential_store_refuses_legacy_plaintext_without_overwriting(tmp_path):
    path = tmp_path / "credentials.json"
    original = '{"OpenAI": "plaintext-must-not-be-read"}'
    path.write_text(original, encoding="utf-8")
    store = CredentialStore(path=str(path))
    assert store.storage_error
    with pytest.raises(RuntimeError, match="will not load"):
        store.set("OpenAI", "replacement-secret")
    assert path.read_text(encoding="utf-8") == original


def test_settings_window_says_saved_api_key_is_hidden_and_kept_when_blank(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from app.ui.settings_window import SettingsWindow

    class SavedCredentialStore:
        storage_error = None

        def __init__(self):
            self.value = "test-only-secret"

        def get(self, name):
            assert name == "OpenAI"
            return self.value

    monkeypatch.setattr("app.ui.settings_window.CredentialStore", SavedCredentialStore)
    app = QApplication.instance() or QApplication([])
    window = SettingsWindow(AppConfig(data_dir=str(tmp_path)))

    assert window.api_key_input.text() == ""
    assert "A key is saved securely" in window.credential_status.text()
    assert "Leave blank to keep it" in window.credential_status.text()
    assert "provider acceptance is checked when you send a message" in window.credential_status.text()
    window.close()
    app.processEvents()
