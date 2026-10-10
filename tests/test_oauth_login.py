"""OAuth sign-in tests. Every network call is replaced by a fake transport, so
no live provider is contacted and no real token exists anywhere in this file.
"""

import json

import pytest

from app.security.oauth import (
    DEVICE_CODE_PROVIDERS,
    LOOPBACK_PROVIDERS,
    DeviceCodeLogin,
    DeviceFlowDenied,
    DeviceFlowExpired,
    LoopbackLogin,
    OAuthError,
    TokenBundle,
    login_provider,
    login_providers,
    unwrap_bearer,
)

AZURE = next(p for p in DEVICE_CODE_PROVIDERS if p.id == "azure_openai")
GOOGLE = next(p for p in LOOPBACK_PROVIDERS if p.id == "google_gemini")


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, data, headers):
        self.calls.append({"url": url, "data": dict(data)})
        if not self.responses:
            raise AssertionError("transport called more times than expected")
        return self.responses.pop(0)


def _bundle_json(access="access-1", refresh="refresh-1", expires_at=0.0):
    return TokenBundle(
        access_token=access,
        token_endpoint="https://example/token",
        client_id="client-1",
        refresh_token=refresh,
        scope="scope",
        expires_at=expires_at,
    ).to_json()


# ── Stored credential handling ───────────────────────────────────────────────


def test_unwrap_bearer_passes_plain_key_through():
    assert unwrap_bearer("sk-plain-key") == "sk-plain-key"
    assert unwrap_bearer(None) is None
    assert unwrap_bearer("not json at all") == "not json at all"


def test_unwrap_bearer_extracts_access_token_from_bundle():
    assert unwrap_bearer(_bundle_json(access="access-xyz")) == "access-xyz"


def test_bundle_round_trip_and_expiry():
    bundle = TokenBundle.from_json(_bundle_json(access="a", refresh="r"))
    assert bundle is not None and bundle.access_token == "a" and bundle.refresh_token == "r"
    # No expiry recorded means "do not claim it expired".
    assert bundle.expired is False
    future = TokenBundle.from_json(_bundle_json(expires_at=10**12))
    assert future.expired is False


def test_client_unwraps_stored_oauth_bundle(monkeypatch):
    from app.opencode.client import OpenCodeClient

    class Store:
        def get(self, _name):
            return _bundle_json(access="oauth-access-token")

    monkeypatch.setattr("app.opencode.client.CredentialStore", lambda: Store())
    client = OpenCodeClient(base_url="https://api.groq.com/openai/v1", credential_name="groq")
    assert client.api_key == "oauth-access-token"


# ── Device authorization grant ───────────────────────────────────────────────


def test_device_code_login_requires_client_id():
    with pytest.raises(OAuthError):
        DeviceCodeLogin(AZURE, client_id="")


def test_device_code_login_success_and_pending_and_slow_down():
    transport = FakeTransport([
        (200, {"device_code": "dc", "user_code": "WXYZ", "verification_uri": "https://login.example", "expires_in": 900, "interval": 1}),
        (400, {"error": "authorization_pending"}),
        (400, {"error": "slow_down"}),
        (200, {"access_token": "tok", "refresh_token": "rt", "expires_in": 3600, "token_type": "Bearer"}),
    ])
    login = DeviceCodeLogin(AZURE, client_id="client-1", tenant="tenant-1", transport=transport, sleep=lambda _s: None)

    prompt = login.start()
    assert prompt.user_code == "WXYZ"
    assert "tenant-1" in transport.calls[0]["url"]
    assert "device_code" not in repr(prompt)  # never expose the device code

    bundle = login.poll(prompt)
    assert bundle.access_token == "tok" and bundle.refresh_token == "rt"


def test_device_code_login_denied_and_expired():
    denied = FakeTransport([(200, {"device_code": "d", "user_code": "c", "verification_uri": "u", "expires_in": 60, "interval": 1}), (400, {"error": "access_denied"})])
    login = DeviceCodeLogin(AZURE, client_id="c", transport=denied, sleep=lambda _s: None)
    with pytest.raises(DeviceFlowDenied):
        login.poll(login.start())

    expired = FakeTransport([(200, {"device_code": "d", "user_code": "c", "verification_uri": "u", "expires_in": 60, "interval": 1}), (400, {"error": "expired_token"})])
    login = DeviceCodeLogin(AZURE, client_id="c", transport=expired, sleep=lambda _s: None)
    with pytest.raises(DeviceFlowExpired):
        login.poll(login.start())


def test_device_code_start_error_is_safe():
    transport = FakeTransport([(400, {"error": "invalid_client", "error_description": "bad app"})])
    login = DeviceCodeLogin(AZURE, client_id="c", transport=transport, sleep=lambda _s: None)
    with pytest.raises(OAuthError) as excinfo:
        login.start()
    assert "invalid_client" in str(excinfo.value)


def test_device_code_cancel():
    transport = FakeTransport([(200, {"device_code": "d", "user_code": "c", "verification_uri": "u", "expires_in": 60, "interval": 1})])
    login = DeviceCodeLogin(AZURE, client_id="c", transport=transport, sleep=lambda _s: None)
    prompt = login.start()
    with pytest.raises(OAuthError):
        login.poll(prompt, should_cancel=lambda: True)


# ── Loopback authorization code + PKCE ───────────────────────────────────────


def test_loopback_authorization_url_has_pkce_and_state():
    login = LoopbackLogin(GOOGLE, client_id="cid", redirect_uri="http://127.0.0.1:5555/callback")
    url, state, verifier = login.prepare()
    assert state in url and "code_challenge=" in url and "code_challenge_method=S256" in url
    assert "access_type=offline" in url
    assert verifier not in url  # only the derived challenge is sent


def test_loopback_exchange_returns_bundle():
    transport = FakeTransport([(200, {"access_token": "g-token", "refresh_token": "g-refresh", "expires_in": 3600})])
    login = LoopbackLogin(GOOGLE, client_id="cid", redirect_uri="http://127.0.0.1:5555/callback", transport=transport)
    bundle = login.exchange(code="auth-code", code_verifier="verifier")
    assert bundle.access_token == "g-token"
    assert transport.calls[0]["data"]["grant_type"] == "authorization_code"


def test_loopback_exchange_error_is_safe():
    transport = FakeTransport([(400, {"error": "invalid_grant", "error_description": "code used"})])
    login = LoopbackLogin(GOOGLE, client_id="cid", redirect_uri="http://127.0.0.1:5555/callback", transport=transport)
    with pytest.raises(OAuthError) as excinfo:
        login.exchange(code="x", code_verifier="y")
    assert "invalid_grant" in str(excinfo.value)


# ── Registry + dialog ────────────────────────────────────────────────────────


def test_login_providers_are_resolvable_and_distinct():
    ids = [provider.id for provider in login_providers()]
    assert len(ids) == len(set(ids))
    assert login_provider("azure_openai") is AZURE
    assert login_provider("google_gemini") is GOOGLE
    assert login_provider("nope") is None
    credential_names = [provider.credential_name for provider in login_providers()]
    assert len(credential_names) == len(set(credential_names))


def test_login_dialog_lists_providers(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from app.ui.login_dialog import LoginDialog

    class Store:
        storage_error = None

        def set(self, *_a):
            pass

    app = QApplication.instance() or QApplication([])
    dialog = LoginDialog(Store())
    assert dialog.provider_input.count() == len(login_providers())
    # The Azure entry needs a tenant field enabled; Google does not.
    dialog.provider_input.setCurrentIndex(dialog.provider_input.findData("azure_openai"))
    assert dialog.tenant_input.isEnabled()
    dialog.provider_input.setCurrentIndex(dialog.provider_input.findData("google_gemini"))
    assert not dialog.tenant_input.isEnabled()
    dialog.close()
    app.processEvents()


def test_login_dialog_stores_token_and_signals(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from app.ui.login_dialog import LoginDialog

    stored = {}

    class Store:
        storage_error = None

        def set(self, name, value):
            stored[name] = value

    app = QApplication.instance() or QApplication([])
    dialog = LoginDialog(Store())
    dialog.provider_input.setCurrentIndex(dialog.provider_input.findData("google_gemini"))
    received = []
    dialog.signed_in.connect(lambda name, pid: received.append((name, pid)))

    bundle = TokenBundle.from_json(_bundle_json(access="stored-token"))
    monkeypatch.setattr("app.ui.login_dialog.QMessageBox.information", lambda *a, **k: None)
    dialog._token_ready(bundle)

    assert stored["google_gemini"] == json.dumps(json.loads(bundle.to_json()))
    assert received == [("google_gemini", "google_gemini")]
    dialog.close()
    app.processEvents()
