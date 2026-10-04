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
