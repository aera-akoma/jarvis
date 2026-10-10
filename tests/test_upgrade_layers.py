from app.computer.windows import WindowsController
from app.opencode.client import OpenCodeClient
from app.startup import StartupManager


def test_opencode_client_uses_env_and_builds_request(monkeypatch):
    class EmptyCredentialStore:
        def get(self, _name):
            return None

    monkeypatch.setattr("app.opencode.client.CredentialStore", EmptyCredentialStore)
    monkeypatch.setenv("OPENCODE_API_KEY", "demo-key")
    monkeypatch.setenv("JARVIS_OPENAI_BASE_URL", "https://example.com/v1")

    client = OpenCodeClient()
    payload = client.build_request("hello there", "custom-model")

    assert payload["model"] == "custom-model"
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"] == "hello there"
    assert client.headers()["Authorization"] == "Bearer demo-key"


def test_saved_api_key_takes_precedence_over_environment_key(monkeypatch):
    class SavedCredentialStore:
        def get(self, _name):
            return "saved-test-key"

    monkeypatch.setattr("app.opencode.client.CredentialStore", SavedCredentialStore)
    monkeypatch.setenv("OPENCODE_API_KEY", "stale-environment-key")

    client = OpenCodeClient(base_url="https://example.com/v1")

    assert client.headers()["Authorization"] == "Bearer saved-test-key"


def test_startup_manager_creates_cmd_file(tmp_path):
    manager = StartupManager(startup_dir=str(tmp_path))
    manager.enable_startup()
    assert (tmp_path / "Jarvis-startup.cmd").exists()

    manager.disable_startup()
    assert not (tmp_path / "Jarvis-startup.cmd").exists()


def test_windows_controller_opens_application(monkeypatch):
    calls = []

    def fake_startfile(path):
        calls.append(path)

    monkeypatch.setattr("os.startfile", fake_startfile, raising=False)
    controller = WindowsController()

    assert controller.open_application("notepad.exe") is True
    assert calls == ["notepad.exe"]


def test_opencode_client_reports_runtime_unavailable_when_not_configured(monkeypatch):
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCODE_BASE_URL", raising=False)

    client = OpenCodeClient()
    response = client.respond("Hello Jarvis", model_name="OpenCode Zen")

    assert "runtime unavailable" in response.lower()
    assert "I’ve received your request" not in response


def test_opencode_client_discovers_models_from_runtime(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return __import__("json").dumps(self.payload).encode("utf-8")

    def fake_urlopen(req, timeout=6):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        payload = {"data": [{"id": "gpt-4o-mini"}, {"id": "claude-3-5-sonnet"}]}
        return FakeResponse(payload)

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", fake_urlopen)

    client = OpenCodeClient(base_url="https://example.com/v1", api_key="test-only-key")
    models = client.available_models()

    assert models == ["gpt-4o-mini", "claude-3-5-sonnet"]
    assert captured["url"] == "https://example.com/v1/models"
    assert captured["timeout"] <= 6


def test_zen_model_discovery_filters_out_models_with_other_api_families(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return __import__("json").dumps({"data": [
                {"id": "gpt-6-astra"},
                {"id": "claude-opus-5-5"},
                {"id": "deepseek-v4-flash"},
                {"id": "jev-1.13"},
            ]}).encode("utf-8")

    def catalog_request(req, **_kwargs):
        captured["headers"] = dict(req.header_items())
        return FakeResponse()

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", catalog_request)
    client = OpenCodeClient(base_url="https://opencode.ai/zen/v1", api_key="test-only-key")

    assert client.available_models() == ["deepseek-v4-flash"]
    assert "Authorization" not in captured["headers"]


def test_zen_model_discovery_explains_when_only_incompatible_models_are_available(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"data":[{"id":"gpt-6-astra"},{"id":"claude-opus-5-5"}]}'

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", lambda *_args, **_kwargs: FakeResponse())
    client = OpenCodeClient(base_url="https://opencode.ai/zen/v1", api_key="test-only-key")

    assert client.available_models() == []
    assert "none use the Chat Completions API" in client.last_error


def test_console_model_discovery_uses_shared_catalog_and_bearer_key(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"data":[{"id":"gpt-6-astra"},{"id":"deepseek-v4-flash"}]}'

    def catalog_request(req, **_kwargs):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        return FakeResponse()

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", catalog_request)
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="console-test-key")

    assert client.available_models() == ["deepseek-v4-flash"]
    assert captured["url"] == "https://opencode.ai/inference/v1/models"
    assert captured["headers"]["Authorization"] == "Bearer console-test-key"


def test_console_chat_request_uses_documented_inference_endpoint(monkeypatch):
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="console-test-key")
    captured = {}

    def fake_post(endpoint, _payload):
        captured["endpoint"] = endpoint
        return {"choices": [{"message": {"content": "hello"}}]}

    monkeypatch.setattr(client, "_post_json", fake_post)
    response = client.request_tool_decision(
        request="hello", model_name="deepseek-v4-flash", tools=[], messages=[], system_prompt="system"
    )

    assert response == {"final_response": "hello"}
    assert captured["endpoint"] == "https://opencode.ai/inference/openai/v1/chat/completions"


def test_model_discovery_reports_authentication_failure_without_response_body(monkeypatch):
    from urllib.error import HTTPError

    def rejected(_request, timeout=8):
        raise HTTPError("https://provider.example/v1/models", 401, "Unauthorized", {}, None)

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", rejected)
    client = OpenCodeClient(base_url="https://provider.example/v1", api_key="test-only-key")

    assert client.available_models() == []
    assert "HTTP 401" in client.last_error
    assert "test-only-key" not in client.last_error


def test_model_discovery_explains_forbidden_workspace_access(monkeypatch):
    from urllib.error import HTTPError

    def forbidden(_request, timeout=6):
        raise HTTPError("https://opencode.ai/zen/v1/models", 403, "Forbidden", {}, None)

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", forbidden)
    client = OpenCodeClient(base_url="https://opencode.ai/zen/v1", api_key="test-only-key")

    assert client.available_models() == []
    assert "HTTP 403" in client.last_error
    assert "account/workspace" in client.last_error
    assert "test-only-key" not in client.last_error
