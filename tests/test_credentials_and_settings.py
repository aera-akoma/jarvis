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


def test_settings_connection_test_runs_catalog_check_in_background(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from app.ui.settings_window import SettingsWindow

    calls = {}

    class SavedCredentialStore:
        storage_error = None

        def __init__(self):
            pass

        def get(self, _name):
            return None

    class FakeClient:
        def __init__(self, *, base_url, api_key):
            calls["base_url"] = base_url
            calls["api_key"] = api_key
            self.last_error = None

        def discover_models(self):
            calls["worker_thread"] = __import__("threading").current_thread().name
            return ["compatible-model"]

    monkeypatch.setattr("app.ui.settings_window.CredentialStore", SavedCredentialStore)
    monkeypatch.setattr("app.ui.settings_window.OpenCodeClient", FakeClient)
    app = QApplication.instance() or QApplication([])
    window = SettingsWindow(AppConfig(data_dir=str(tmp_path)))
    window.base_url_input.setText("https://provider.example/v1")
    window.api_key_input.setText("connection-test-secret")

    window.test_connection()
    worker = window._connection_worker
    assert worker is not None
    assert worker.wait(2000)
    app.processEvents()

    assert calls["base_url"] == "https://provider.example/v1"
    assert calls["api_key"] == "connection-test-secret"
    assert calls["worker_thread"] != "MainThread"
    assert "does not verify chat-completions access" in window.connection_status.text()
    assert "connection-test-secret" not in window.connection_status.text()
    window.close()
    app.processEvents()


def test_credential_replace_all_persists_exactly_one_protected_entry(tmp_path, monkeypatch):
    import json

    from app.security import credentials as credentials_module

    def fake_dpapi(data, *, decrypt):
        return data.removeprefix(b"test-protected:") if decrypt else b"test-protected:" + data

    monkeypatch.setattr(credentials_module, "_dpapi", fake_dpapi)
    monkeypatch.setattr(CredentialStore, "_require_available", lambda self: None)
    path = tmp_path / "credentials.json"
    store = CredentialStore(path=str(path))
    store.set("Old", "old-test-secret")
    store.set("Another", "another-test-secret")
    store.replace_all("OpenAI", "replacement-test-secret")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert list(payload["entries"]) == ["OpenAI"]
    assert "replacement-test-secret" not in path.read_text(encoding="utf-8")
    assert store.get("OpenAI") == "replacement-test-secret"
    assert CredentialStore(path=str(path)).get("OpenAI") == "replacement-test-secret"


def test_credential_replace_all_rolls_back_after_write_failure(tmp_path, monkeypatch):
    from app.security import credentials as credentials_module

    def fake_dpapi(data, *, decrypt):
        return data.removeprefix(b"test-protected:") if decrypt else b"test-protected:" + data

    monkeypatch.setattr(credentials_module, "_dpapi", fake_dpapi)
    monkeypatch.setattr(CredentialStore, "_require_available", lambda self: None)
    store = CredentialStore(path=str(tmp_path / "credentials.json"))
    store.set("OpenAI", "old-test-secret")
    store.set("Other", "other-test-secret")
    original_file = store.path.read_bytes()

    def fail_save():
        raise OSError("simulated protected-store write failure")

    monkeypatch.setattr(store, "_save", fail_save)
    with pytest.raises(OSError, match="simulated protected-store write failure"):
        store.replace_all("OpenAI", "replacement-test-secret")

    assert store.get("OpenAI") == "old-test-secret"
    assert store.get("Other") == "other-test-secret"
    assert store.path.read_bytes() == original_file


def test_blank_key_save_preserves_existing_credential(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from app.ui.settings_window import SettingsWindow

    class SavedCredentialStore:
        storage_error = None
        value = "keep-this-test-secret"

        def __init__(self):
            pass

        def get(self, _name):
            return self.value

        def replace_all(self, _name, value):
            self.value = value

    class NoopStartupManager:
        def __init__(self):
            pass

        def is_enabled(self):
            return False

        def enable_startup(self):
            pass

        def disable_startup(self):
            pass

    monkeypatch.setattr("app.ui.settings_window.CredentialStore", SavedCredentialStore)
    monkeypatch.setattr("app.ui.settings_window.StartupManager", NoopStartupManager)
    app = QApplication.instance() or QApplication([])
    window = SettingsWindow(AppConfig(data_dir=str(tmp_path)))
    window.api_key_input.clear()

    window.save_settings()

    assert window.credentials.value == "keep-this-test-secret"
    app.processEvents()


def test_nonempty_key_save_replaces_all_saved_entries(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.ui.settings_window import SettingsWindow

    class SavedCredentialStore:
        storage_error = None

        def __init__(self):
            self.entries = {"OpenAI": "old-test-secret", "Other": "another-test-secret"}

        def get(self, name):
            return self.entries.get(name)

        def replace_all(self, name, value):
            self.entries = {name: value}

    class NoopStartupManager:
        def __init__(self):
            pass

        def is_enabled(self):
            return False

        def enable_startup(self):
            pass

        def disable_startup(self):
            pass

    monkeypatch.setattr("app.ui.settings_window.CredentialStore", SavedCredentialStore)
    monkeypatch.setattr("app.ui.settings_window.StartupManager", NoopStartupManager)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    app = QApplication.instance() or QApplication([])
    window = SettingsWindow(AppConfig(data_dir=str(tmp_path)))
    window.base_url_input.setText("https://provider.example/v1")
    window.api_key_input.setText("new-test-secret")

    window.save_settings()

    assert window.credentials.entries == {"OpenAI": "new-test-secret"}
    app.processEvents()


def test_clear_key_removes_saved_credential(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.ui.settings_window import SettingsWindow

    class SavedCredentialStore:
        storage_error = None
        value = "clear-this-test-secret"

        def __init__(self):
            pass

        def get(self, _name):
            return self.value

        def delete(self, _name):
            self.value = None

    monkeypatch.setattr("app.ui.settings_window.CredentialStore", SavedCredentialStore)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    app = QApplication.instance() or QApplication([])
    window = SettingsWindow(AppConfig(data_dir=str(tmp_path)))

    window.clear_key()

    assert window.credentials.value is None
    assert window.api_key_input.text() == ""
    window.close()
    app.processEvents()
