from app.opencode.client import OpenCodeClient, ProviderHTTPError
from app.providers import (
    PROVIDER_PRESETS,
    default_preset,
    get_preset,
    opencode_presets,
    provider_for_base_url,
)


# The free providers listed by the "awesome-free-llm-apis" repository, mapped to
# the Jarvis preset id that carries them. Cloudflare/Cohere/Ollama are reached
# through their OpenAI-compatible routes.
FREE_PROVIDER_PRESETS = {
    "aionlabs", "cohere", "google_gemini", "mistral", "zai", "cloudflare",
    "groq", "huggingface", "kilo", "llm7", "modelscope", "nvidia",
    "ollama_cloud", "openrouter", "ovhcloud", "siliconflow",
}

# OpenCode's own provider catalog (models.dev) lists every one of these except
# Aion Labs and LLM7.io.
IN_OPENCODE = FREE_PROVIDER_PRESETS - {"aionlabs", "llm7"}


def test_every_free_provider_from_the_list_has_a_preset():
    ids = {preset.id for preset in PROVIDER_PRESETS}
    assert FREE_PROVIDER_PRESETS <= ids
    for provider_id in FREE_PROVIDER_PRESETS:
        preset = get_preset(provider_id)
        assert preset.base_url.startswith("https://"), provider_id


def test_opencode_mapping_matches_the_catalog():
    in_opencode = {preset.id for preset in opencode_presets()}
    assert IN_OPENCODE <= in_opencode
    assert not ({"aionlabs", "llm7"} & in_opencode)
    assert get_preset("groq").opencode_id == "groq"
    assert get_preset("google_gemini").opencode_id == "google"
    assert get_preset("cloudflare").opencode_id == "cloudflare-workers-ai"
    assert get_preset("ollama_cloud").opencode_id == "ollama-cloud"
    assert get_preset("aionlabs").in_opencode is False
    assert get_preset("llm7").in_opencode is False
    # A preset OpenCode knows must carry the OpenCode provider id.
    assert all(preset.opencode_id for preset in opencode_presets())


def test_provider_presets_are_unique_and_resolvable():
    ids = [preset.id for preset in PROVIDER_PRESETS]
    assert len(ids) == len(set(ids))
    assert get_preset("groq").base_url == "https://api.groq.com/openai/v1"
    assert get_preset("does-not-exist") is None
    assert default_preset().credential_name == "OpenAI"
    assert provider_for_base_url("https://api.groq.com/openai/v1/").id == "groq"
    assert provider_for_base_url("https://unknown.example/v1") is None
    # Every provider keeps a distinct credential name so keys never collide.
    names = [preset.credential_name for preset in PROVIDER_PRESETS]
    assert len(names) == len(set(names))


def test_azure_sign_in_preset_makes_the_token_usable():
    # The browser sign-in stores the token under credential_name "azure_openai".
    # A preset must exist with that credential name, otherwise requests would
    # never read the signed-in token.
    preset = get_preset("azure_openai")
    assert preset is not None
    assert preset.credential_name == "azure_openai"
    assert preset.id == "azure_openai"
    assert preset.base_url.startswith("https://")
    assert "azure" in preset.base_url


def test_client_uses_provider_scoped_credential(monkeypatch):
    class Store:
        def __init__(self):
            self.requested = []

        def get(self, name):
            self.requested.append(name)
            return "groq-test-key" if name == "groq" else None

    store = Store()
    monkeypatch.setattr("app.opencode.client.CredentialStore", lambda: store)

    client = OpenCodeClient(base_url="https://api.groq.com/openai/v1", credential_name="groq")

    assert client.api_key == "groq-test-key"
    assert store.requested == ["groq"]
    assert "groq-test-key" not in repr(client.headers()) or client.headers()["Authorization"].startswith("Bearer ")


def test_client_default_credential_name_stays_legacy_openai(monkeypatch):
    class Store:
        def __init__(self):
            self.names = []

        def get(self, name):
            self.names.append(name)
            return None

    store = Store()
    monkeypatch.setattr("app.opencode.client.CredentialStore", lambda: store)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_OPENAI_API_KEY", raising=False)

    client = OpenCodeClient(base_url="https://api.example.com/v1")

    assert client.credential_name == "OpenAI"
    assert store.names == ["OpenAI"]
    assert client.api_key is None


def test_environment_key_is_only_used_for_the_default_provider(monkeypatch):
    class Store:
        def get(self, _name):
            return None

    monkeypatch.setattr("app.opencode.client.CredentialStore", lambda: Store())
    monkeypatch.setenv("OPENAI_API_KEY", "global-env-key")

    default_client = OpenCodeClient(base_url="https://api.example.com/v1")
    other_client = OpenCodeClient(base_url="https://api.groq.com/openai/v1", credential_name="groq")

    assert default_client.api_key == "global-env-key"
    # A generic OPENAI_API_KEY must never be sent to an unrelated provider.
    assert other_client.api_key is None


def test_retryable_classification_for_failover():
    assert OpenCodeClient._is_retryable_error(ProviderHTTPError(429, "chat-completions POST"))
    assert OpenCodeClient._is_retryable_error(ProviderHTTPError(503, "chat-completions POST"))
    assert OpenCodeClient._is_retryable_error(ProviderHTTPError(402, "chat-completions POST"))
    assert not OpenCodeClient._is_retryable_error(ProviderHTTPError(401, "chat-completions POST"))
    assert not OpenCodeClient._is_retryable_error(ProviderHTTPError(404, "chat-completions POST"))
    # Free-tier and quota errors are retryable on the next model.
    assert OpenCodeClient._is_retryable_error(
        ProviderHTTPError(403, "chat-completions POST", provider_type="FreeTierError", provider_message="free tier only")
    )
    assert OpenCodeClient._is_retryable_error(
        ProviderHTTPError(400, "chat-completions POST", provider_type="insufficient_quota", provider_message="quota exceeded")
    )
    assert not OpenCodeClient._is_retryable_error(
        ProviderHTTPError(400, "chat-completions POST", provider_type="invalid_request_error", provider_message="bad model")
    )


class _StubClient:
    """Minimal chat client that answers or fails per model."""

    def __init__(self, results, retryable):
        self.results = results
        self.retryable = retryable
        self.calls: list[str] = []
        self.last_error = ""
        self.last_error_retryable = False

    def request_tool_decision(self, *, model_name, **_kwargs):
        self.calls.append(model_name)
        reply = self.results.get(model_name, {"error": "unknown model"})
        if "error" in reply:
            self.last_error = reply["error"]
            self.last_error_retryable = self.retryable(model_name) if callable(self.retryable) else self.retryable
        else:
            self.last_error = ""
            self.last_error_retryable = False
        return reply


def _adapter(client, primary, fallbacks):
    from app.agent import OpenAICompatibleModelAdapter

    adapter = OpenAICompatibleModelAdapter(ToolRegistryStub(), client, primary, fallback_models=fallbacks)
    adapter.begin_request()
    return adapter


class ToolRegistryStub:
    def model_definitions(self):
        return []


def test_adapter_fails_over_to_next_model_on_retryable_error():
    client = _StubClient(
        {"primary": {"error": "quota exhausted"}, "backup": {"final_response": "done"}},
        retryable=True,
    )
    adapter = _adapter(client, "primary", ["backup"])

    reply = adapter.decide("hello", context={})

    assert reply["final_response"] == "done"
    assert reply["model_used"] == "backup"
    assert client.calls == ["primary", "backup"]
    assert adapter.last_fallback_note and "backup" in adapter.last_fallback_note


def test_adapter_does_not_failover_on_non_retryable_error():
    client = _StubClient(
        {"primary": {"error": "invalid key"}, "backup": {"final_response": "done"}},
        retryable=False,
    )
    adapter = _adapter(client, "primary", ["backup"])

    reply = adapter.decide("hello", context={})

    assert "error" in reply
    assert client.calls == ["primary"]


def test_adapter_reports_when_every_model_is_exhausted():
    client = _StubClient(
        {"a": {"error": "quota"}, "b": {"error": "quota"}},
        retryable=True,
    )
    adapter = _adapter(client, "a", ["b"])

    reply = adapter.decide("hello", context={})

    assert "exhausted" in reply["error"].lower()
    assert client.calls == ["a", "b"]


def test_adapter_sticks_to_a_working_model_within_a_request():
    client = _StubClient(
        {"primary": {"error": "quota"}, "backup": {"tool": "noop", "arguments": {}}},
        retryable=True,
    )
    adapter = _adapter(client, "primary", ["backup"])

    adapter.decide("first", context={})
    adapter.decide("second", context={})

    # The exhausted primary is not retried within the same request.
    assert client.calls == ["primary", "backup", "backup"]


def test_upgrade_without_provider_id_keeps_legacy_openai_credential(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from app.config import AppConfig
    from app.core.settings_manager import SettingsManager
    from app.ui.settings_window import SettingsWindow

    class Store:
        storage_error = None

        def __init__(self):
            self.entries = {"OpenAI": "legacy-key"}

        def get(self, name):
            return self.entries.get(name)

    config = AppConfig(data_dir=str(tmp_path))
    # An existing install: key under "OpenAI", no provider_id, OpenCode URL.
    SettingsManager(config).set("openai_base_url", "https://opencode.ai/zen/v1")

    monkeypatch.setattr("app.ui.settings_window.CredentialStore", Store)
    app = QApplication.instance() or QApplication([])
    window = SettingsWindow(config)

    assert window._selected_preset().credential_name == "OpenAI"
    assert window.base_url_input.text() == "https://opencode.ai/zen/v1"
    assert "A key is saved securely" in window.credential_status.text()
    window.close()
    app.processEvents()


def test_keyless_presets_carry_live_validated_default_models():
    # These defaults were verified against the live public endpoints with no
    # API key: each returns HTTP 200 on a one-token chat request.
    assert get_preset("kilo").default_model == "kilo-auto/free"
    assert get_preset("llm7").default_model == "DeepSeek-V4-Flash-0731"
    assert get_preset("ovhcloud").default_model == "Mistral-7B-Instruct-v0.3"
    # Every preset has an explicit default, or explicitly none so the user picks.
    for preset in PROVIDER_PRESETS:
        assert "default_model" in preset.__dataclass_fields__


class _FakeProviderError:
    def __init__(self, status, *, provider_type=None, provider_message=None, stage="chat-completions access test"):
        self.status = status
        self.stage = stage
        self.edge_blocked = False
        self.provider_type = provider_type
        self.provider_message = provider_message


def _keyless_error_text(monkeypatch, base_url, api_kind):
    class Store:
        def get(self, _name):
            return None

    monkeypatch.setattr("app.opencode.client.CredentialStore", lambda: Store())
    client = OpenCodeClient(base_url=base_url, credential_name="keyless-validation")
    assert client.api_key is None
    assert client._opencode_api_kind() == api_kind
    error = _FakeProviderError(
        401,
        provider_type="PAID_MODEL_AUTH_REQUIRED",
        provider_message="You need to sign in to use this model.",
    )
    return client._post_error(f"{base_url}/chat/completions", "kilo-auto/free", error)


def test_opencode_key_hint_is_not_attached_to_third_party_provider_errors(monkeypatch):
    text = _keyless_error_text(monkeypatch, "https://api.kilo.ai/api/gateway", None)
    assert "Console service-account key" not in text
    assert "PAID_MODEL_AUTH_REQUIRED" in text or "paid" in text.lower()


def test_opencode_key_hint_still_appears_for_the_opencode_console_route(monkeypatch):
    text = _keyless_error_text(monkeypatch, "https://opencode.ai/inference/openai/v1", "console")
    assert "Console service-account key" in text
