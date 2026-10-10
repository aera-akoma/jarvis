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


def test_console_model_discovery_uses_public_catalog_and_documented_family_table(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"object":"list","data":[{"id":"gpt-6-astra","object":"model","owned_by":"opencode"},{"id":"deepseek-v4-flash","object":"model","owned_by":"opencode"},{"id":"claude-sonnet-4-6","object":"model","owned_by":"opencode"},{"id":"kimi-k2.6","object":"model","owned_by":"opencode"}]}'

    def catalog_request(req, **_kwargs):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        return FakeResponse()

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", catalog_request)
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="console-test-key")

    assert client.available_models() == ["deepseek-v4-flash", "kimi-k2.6"]
    assert captured["url"] == "https://opencode.ai/inference/v1/models"
    assert "Authorization" not in captured["headers"]


def test_console_catalog_requires_confirmed_chat_completions_family(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"data":[{"id":"unknown-model"},{"id":"responses-model","endpoint":"/responses"}]}'

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", lambda *_args, **_kwargs: FakeResponse())
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")

    assert client.available_models() == []
    assert "none match a model documented for Chat Completions" in client.last_error


def test_console_model_family_metadata_overrides_documented_id_fallback(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"data":[{"id":"deepseek-v4-flash","api_family":"responses"},{"id":"vendor-chat-model","api_family":"openai-compatible"}]}'

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", lambda *_args, **_kwargs: FakeResponse())
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")

    assert client.available_models() == ["vendor-chat-model"]


def test_provider_endpoint_normalization_accepts_documented_chat_url(monkeypatch):
    client = OpenCodeClient(
        base_url="https://opencode.ai/inference/openai/v1/chat/completions",
        api_key="console-test-key",
    )
    captured = {}

    def fake_post(endpoint, _payload):
        captured["endpoint"] = endpoint
        return {"choices": [{"message": {"content": "hello"}}]}

    monkeypatch.setattr(client, "_post_json", fake_post)
    result = client.request_tool_decision(
        request="hello", model_name="deepseek-v4-flash", tools=[], messages=[], system_prompt="system"
    )

    assert result == {"final_response": "hello"}
    assert client.base_url == "https://opencode.ai/inference/openai/v1"
    assert captured["endpoint"] == "https://opencode.ai/inference/openai/v1/chat/completions"


def test_chat_endpoint_keeps_base_url_query_after_normalized_path():
    client = OpenCodeClient(base_url="https://provider.example/v1?deployment=blue", api_key="test-only-key")

    assert client._chat_completion_endpoints() == [
        "https://provider.example/v1/chat/completions?deployment=blue"
    ]


def test_opencode_other_api_families_are_rejected_without_endpoint_guessing(monkeypatch):
    client = OpenCodeClient(base_url="https://opencode.ai/inference/anthropic/v1/messages", api_key="test-only-key")
    calls = []
    monkeypatch.setattr(client, "_post_json", lambda *args, **kwargs: calls.append(args))

    result = client.request_tool_decision(
        request="hello", model_name="claude-sonnet-4-6", tools=[], messages=[], system_prompt="system"
    )

    assert "different API family" in result["error"]
    assert calls == []
    assert client._chat_completion_endpoints() == []


def test_console_chat_request_blocks_model_from_another_api_family(monkeypatch):
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")
    calls = []
    monkeypatch.setattr(client, "_post_json", lambda *args, **kwargs: calls.append(args))

    result = client.request_tool_decision(
        request="hello", model_name="gpt-6-astra", tools=[], messages=[], system_prompt="system"
    )

    assert "not documented for Chat Completions" in result["error"]
    assert calls == []


def test_safe_endpoint_hides_url_credentials_query_and_token_path_segments():
    safe = OpenCodeClient._safe_endpoint(
        "https://private-user:private-pass@provider.example/v1/token-value-123?api_key=query-secret"
    )

    assert safe == "https://provider.example/v1/<redacted>"
    assert "private-pass" not in safe
    assert "query-secret" not in safe


def test_console_catalog_403_reports_get_stage_without_response_body(monkeypatch):
    from urllib.error import HTTPError

    def forbidden(_request, timeout=6):
        raise HTTPError(
            "https://opencode.ai/inference/v1/models", 403, "Forbidden", {},
            __import__("io").BytesIO(b'{"message":"test-only-provider-body"}'),
        )

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", forbidden)
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")

    assert client.available_models() == []
    assert "catalog GET failed" in client.last_error
    assert "opencode.ai/inference/v1/models" in client.last_error
    assert "HTTP 403" in client.last_error
    assert "account/workspace" in client.last_error
    assert "test-only-key" not in client.last_error
    assert "test-only-provider-body" not in client.last_error


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


def test_chat_403_reports_post_stage_and_redacts_response_body(monkeypatch):
    from app.opencode.client import OpenCodeClient

    class FakeResponse:
        status = 403

        def read(self):
            return b'{"message":"test-only-provider-body","authorization":"test-only-key"}'

    class FakeConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            pass

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr("app.opencode.client.http.client.HTTPSConnection", FakeConnection)
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")
    decision = client.request_tool_decision(
        request="test request", model_name="deepseek-v4-flash", tools=[], messages=[], system_prompt="system"
    )

    assert "chat-completions POST failed" in decision["error"]
    assert "opencode.ai/inference/openai/v1/chat/completions" in decision["error"]
    assert "deepseek-v4-flash" in decision["error"]
    assert "HTTP 403" in decision["error"]
    assert "test-only-provider-body" not in decision["error"]
    assert "test-only-key" not in decision["error"]


def test_chat_request_serializes_text_attachment_and_requires_image_metadata(monkeypatch):
    client = OpenCodeClient(base_url="https://provider.example/v1", api_key="test-only-key")
    captured = {}

    def fake_post(_endpoint, payload):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "received"}}]}

    monkeypatch.setattr(client, "_post_json", fake_post)
    result = client.request_tool_decision(
        request="Summarize this", model_name="test-model", tools=[], messages=[], system_prompt="system",
        attachments=[{"kind": "text", "name": "notes.txt", "content": "private file content"}],
    )
    assert result == {"final_response": "received"}
    content = captured["payload"]["messages"][1]["content"]
    assert content[1] == {"type": "text", "text": "[Untrusted attached text file: notes.txt]\nprivate file content"}

    blocked = client.request_tool_decision(
        request="Describe this", model_name="test-model", tools=[], messages=[], system_prompt="system",
        attachments=[{"kind": "image", "name": "image.png", "path": "unused.png"}],
    )
    assert "not confirmed to support image input" in blocked["error"]


def test_chat_request_serializes_image_only_with_confirmed_image_metadata(monkeypatch):
    client = OpenCodeClient(base_url="https://provider.example/v1", api_key="test-only-key")
    client._model_metadata["vision-model"] = {"modalities": {"input": ["text", "image"]}}
    captured = {}
    monkeypatch.setattr(client, "_image_data_url", lambda _path: "data:image/jpeg;base64,mocked")

    def fake_post(_endpoint, payload):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "received"}}]}

    monkeypatch.setattr(client, "_post_json", fake_post)

    result = client.request_tool_decision(
        request="Describe this", model_name="vision-model", tools=[], messages=[], system_prompt="system",
        attachments=[{"kind": "image", "name": "image.png", "path": "image.png"}],
    )

    assert result == {"final_response": "received"}
    content = captured["payload"]["messages"][1]["content"]
    assert content[1] == {"type": "text", "text": "[Untrusted attached image: image.png]"}
    assert content[2] == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,mocked"}}


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


def test_provider_requests_send_honest_user_agent_instead_of_python_urllib(monkeypatch):
    """Regression: OpenCode's CDN edge returns HTTP 403 (Cloudflare error 1010)
    for the default `Python-urllib/3.x` signature before authentication runs."""
    captured: dict[str, dict] = {}

    def fake_urlopen(request, timeout=6):
        captured["get"] = dict(request.headers)
        raise __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
            request.full_url, 403, "Forbidden", {},
            __import__("io").BytesIO(
                b'{"error_code":1010,"error_name":"browser_signature_banned"}'
            ),
        )

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", fake_urlopen)

    class FakeResponse:
        status = 200

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    class FakeConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, _method, _path, body=None, headers=None):
            captured["post"] = dict(headers or {})

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr("app.opencode.client.http.client.HTTPSConnection", FakeConnection)
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")
    client.available_models()
    client.request_tool_decision(
        request="hello", model_name="deepseek-v4-flash", tools=[], messages=[], system_prompt="system"
    )

    for name in ("get", "post"):
        values = " ".join(str(value) for value in captured[name].values())
        assert OpenCodeClient.USER_AGENT in values, name
        assert "Python-urllib" not in values, name

    assert "Bearer test-only-key" in captured["post"].values()
    # The documented catalog GET is public, so no credential is transmitted on it.
    assert not any(str(value).startswith("Bearer ") for value in captured["get"].values())


def test_catalog_edge_block_is_reported_as_not_a_credential_problem(monkeypatch):
    from urllib.error import HTTPError

    def edge_blocked(_request, timeout=6):
        raise HTTPError(
            "https://opencode.ai/inference/v1/models", 403, "Forbidden", {},
            __import__("io").BytesIO(
                b'{"type":"https://developers.cloudflare.com/...","error_code":1010,'
                b'"error_name":"browser_signature_banned","ray_id":"test-only-ray"}'
            ),
        )

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", edge_blocked)
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")

    assert client.available_models() == []
    assert "catalog GET failed" in client.last_error
    assert "Cloudflare error 1010" in client.last_error
    assert "not an API-key" in client.last_error
    # The response body must never be surfaced.
    assert "browser_signature_banned" not in client.last_error
    assert "test-only-ray" not in client.last_error
    assert "test-only-key" not in client.last_error


def test_chat_post_edge_block_is_reported_as_edge_block(monkeypatch):
    class FakeResponse:
        status = 403

        def read(self):
            return b'{"error_code":1010,"error_name":"browser_signature_banned"}'

    class FakeConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            pass

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr("app.opencode.client.http.client.HTTPSConnection", FakeConnection)
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")

    decision = client.request_tool_decision(
        request="hello", model_name="deepseek-v4-flash", tools=[], messages=[], system_prompt="system"
    )

    assert "Cloudflare error 1010" in decision["error"]
    assert "not an API-key" in decision["error"]
    assert "browser_signature_banned" not in decision["error"]
    assert "test-only-key" not in decision["error"]


def test_missing_credential_is_named_when_paid_model_gets_403(monkeypatch):
    class FakeResponse:
        status = 403

        def read(self):
            return b'{"message":"credential required"}'

    class FakeConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, _method, _path, body=None, headers=None):
            assert not any(str(v).startswith("Bearer ") for v in (headers or {}).values())

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr("app.opencode.client.http.client.HTTPSConnection", FakeConnection)
    monkeypatch.setattr("app.opencode.client.CredentialStore", lambda: type("S", (), {"get": staticmethod(lambda _n: None)})())
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key=None)
    client.api_key = None

    decision = client.request_tool_decision(
        request="hello", model_name="deepseek-v4-flash", tools=[], messages=[], system_prompt="system"
    )

    assert "No API key is configured" in decision["error"]
    assert "test-only" not in decision["error"]


def test_provider_diagnostics_are_logged_without_secrets_or_response_bodies(monkeypatch, caplog):
    import logging
    from urllib.error import HTTPError

    def edge_blocked(_request, timeout=6):
        raise HTTPError(
            "https://opencode.ai/inference/v1/models", 403, "Forbidden", {},
            __import__("io").BytesIO(
                b'{"error_code":1010,"error_name":"browser_signature_banned",'
                b'"secret":"test-only-provider-body"}'
            ),
        )

    monkeypatch.setattr("app.opencode.client.request_module.urlopen", edge_blocked)
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")

    with caplog.at_level(logging.INFO, logger="jarvis.provider"):
        assert client.available_models() == []

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "stage=catalog GET" in text
    assert "status=403" in text
    assert "edge_blocked=True" in text
    assert "opencode.ai/inference/v1/models" in text
    # Never log credentials, headers, or the provider's response body.
    assert "test-only-key" not in text
    assert "test-only-provider-body" not in text
    assert "browser_signature_banned" not in text
    assert "Authorization" not in text
    assert "Bearer" not in text


def test_api_level_403_with_a_key_sent_points_at_console_vs_zen_key_mismatch(monkeypatch):
    class FakeResponse:
        status = 403

        def read(self):
            # A real API refusal, not a CDN edge block.
            return b'{"error":{"message":"model not enabled"}}'

    class FakeConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            pass

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr("app.opencode.client.http.client.HTTPSConnection", FakeConnection)
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")

    decision = client.request_tool_decision(
        request="hello", model_name="deepseek-v4-flash", tools=[], messages=[], system_prompt="system"
    )

    assert "HTTP 403" in decision["error"]
    assert "Console service-account key" in decision["error"]
    assert "https://opencode.ai/zen/v1" in decision["error"]
    assert "test-only-key" not in decision["error"]
    # The provider's own structured message is the most useful diagnostic.
    assert "model not enabled" in decision["error"]


def test_provider_structured_error_type_and_message_are_surfaced(monkeypatch):
    """OpenCode returns {"type":"error","error":{"type":...,"message":...}}."""

    class FakeResponse:
        status = 403

        def read(self):
            return (
                b'{"type":"error","error":{"type":"FreeTierError",'
                b'"message":"OpenCode\'s free tier can only be used from within OpenCode"}}'
            )

    class FakeConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            pass

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr("app.opencode.client.http.client.HTTPSConnection", FakeConnection)
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")

    decision = client.request_tool_decision(
        request="hello", model_name="kimi-k2.6", tools=[], messages=[], system_prompt="system"
    )

    assert "FreeTierError" in decision["error"]
    assert "free tier" in decision["error"]
    assert "official OpenCode client" in decision["error"]
    assert "test-only-key" not in decision["error"]


def test_provider_error_message_never_leaks_the_key_even_if_echoed(monkeypatch):
    class FakeResponse:
        status = 403

        def read(self):
            return (
                b'{"type":"error","error":{"type":"AuthenticationError",'
                b'"message":"Invalid key: Bearer test-only-key"}}'
            )

    class FakeConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            pass

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr("app.opencode.client.http.client.HTTPSConnection", FakeConnection)
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")

    decision = client.request_tool_decision(
        request="hello", model_name="kimi-k2.6", tools=[], messages=[], system_prompt="system"
    )

    assert "AuthenticationError" in decision["error"]
    assert "test-only-key" not in decision["error"]
    assert "Bearer test-only-key" not in decision["error"]


def test_probe_model_access_confirms_when_provider_answers(monkeypatch):
    client = OpenCodeClient(base_url="https://opencode.ai/zen/v1", api_key="test-only-key")
    captured: dict = {}

    def fake_post(endpoint, payload, *, stage="chat-completions POST"):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        captured["stage"] = stage
        return {"choices": [{"message": {"content": "pong"}}]}

    monkeypatch.setattr(client, "_post_json", fake_post)

    result = client.probe_model_access("kimi-k2.6")

    assert result["ok"] is True
    assert captured["endpoint"] == "https://opencode.ai/zen/v1/chat/completions"
    assert captured["payload"]["max_tokens"] == 1
    assert captured["payload"]["messages"] == [{"role": "user", "content": "ping"}]


def test_probe_model_access_surfaces_provider_error_without_leaking_key(monkeypatch):
    from app.opencode.client import ProviderHTTPError

    client = OpenCodeClient(base_url="https://opencode.ai/zen/v1", api_key="test-only-key")

    def fake_post(endpoint, payload, *, stage="chat-completions POST"):
        raise ProviderHTTPError(
            403, stage, provider_type="FreeTierError",
            provider_message="OpenCode's free tier can only be used from within OpenCode",
        )

    monkeypatch.setattr(client, "_post_json", fake_post)

    result = client.probe_model_access("nemotron-3.5-lightning-free")

    assert result["ok"] is False
    assert "FreeTierError" in result["error"]
    assert "HTTP 403" in result["error"]
    assert "test-only-key" not in result["error"]


def test_probe_model_access_does_not_send_for_unsupported_family():
    client = OpenCodeClient(base_url="https://opencode.ai/inference/openai/v1", api_key="test-only-key")

    def fail(*_args, **_kwargs):
        raise AssertionError("no request should be sent")

    client._post_json = fail
    # gpt-5.5 uses the Responses API, not Chat Completions.
    result = client.probe_model_access("gpt-5.5")

    assert result["ok"] is False
    assert "Chat Completions" in result["error"]
