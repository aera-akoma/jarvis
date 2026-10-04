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


def test_credential_store_round_trip(tmp_path):
    store = CredentialStore(path=str(tmp_path / "credentials.json"))
    store.set("OpenAI", "demo-key")
    assert store.get("OpenAI") == "demo-key"

    store.delete("OpenAI")
    assert store.get("OpenAI") is None


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
    import pytest

    path = tmp_path / "credentials.json"
    original = '{"OpenAI": "plaintext-must-not-be-read"}'
    path.write_text(original, encoding="utf-8")
    store = CredentialStore(path=str(path))
    assert store.storage_error
    with pytest.raises(RuntimeError, match="will not load"):
        store.set("OpenAI", "replacement-secret")
    assert path.read_text(encoding="utf-8") == original
