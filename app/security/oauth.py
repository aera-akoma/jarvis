"""Browser sign-in for model providers (device code + installed-app OAuth).

WHY THIS EXISTS
    Most free providers need an API key. A few support signing in with a browser
    instead, which is friendlier and avoids pasting long secrets. This module
    implements the two standards that a desktop app can honour without
    pretending to be the provider's own client:

      * RFC 8628 device authorization grant ("go to this URL and type this code"),
        used by Microsoft Entra ID and other OIDC providers.
      * RFC 7636 authorization code + PKCE on a loopback redirect, used by
        Google and other installed-app flows.

    It deliberately does NOT perform any private/undocumented token exchange
    (for example GitHub Copilot's internal endpoint). Those would impersonate an
    official client, which Jarvis will not do.

SECRETS
    Tokens and refresh tokens are returned to the caller in memory only. Nothing
    here logs or prints a token, and the stored form is a JSON bundle that is
    kept in the Windows DPAPI credential store by the caller. ``unwrap_bearer``
    converts a stored bundle back to a bearer string without any network call.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable


USER_AGENT = "Jarvis/1.0"


class OAuthError(RuntimeError):
    """A safe, user-facing sign-in error (never contains a token)."""


class DeviceFlowExpired(OAuthError):
    pass


class DeviceFlowDenied(OAuthError):
    pass


# A transport is ``(url, form_fields, extra_headers) -> (status, json_dict)``.
# The default uses urllib; tests inject a fake so no network call happens.
Transport = Callable[[str, dict, dict], "tuple[int, dict]"]


def _sanitize(payload: object) -> str:
    """Bound and redact a provider error before it is ever shown to a user."""
    if not isinstance(payload, dict):
        return "The provider refused the sign-in request."
    error = str(payload.get("error") or "").strip()
    description = str(payload.get("error_description") or payload.get("message") or "").strip()
    text = ": ".join(part for part in (error, description) if part) or "The provider refused the sign-in request."
    return text[:300]


def urllib_transport(url: str, data: dict, headers: dict) -> tuple[int, dict]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            text = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(text or "{}")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(text or "{}")
        except ValueError:
            payload = {"error": "http_error", "error_description": f"HTTP {exc.code}"}
        return exc.code, payload
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise OAuthError(f"The sign-in server could not be reached ({type(exc).__name__}).") from exc


# ── Token bundles ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TokenBundle:
    """A store-able OAuth token set. Never logged; serialized only for DPAPI."""

    access_token: str
    token_endpoint: str
    client_id: str
    refresh_token: str = ""
    scope: str = ""
    expires_at: float = 0.0
    token_type: str = "Bearer"

    @property
    def expired(self) -> bool:
        if not self.expires_at:
            return False
        return time.time() >= self.expires_at - 60

    def to_json(self) -> str:
        return json.dumps({
            "type": "jarvis-oauth",
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_endpoint": self.token_endpoint,
            "client_id": self.client_id,
            "scope": self.scope,
            "expires_at": self.expires_at,
            "token_type": self.token_type,
        })

    @classmethod
    def from_json(cls, value: str) -> "TokenBundle | None":
        try:
            payload = json.loads(value)
        except (ValueError, TypeError):
            return None
        if not isinstance(payload, dict) or payload.get("type") != "jarvis-oauth":
            return None
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            return None
        return cls(
            access_token=access_token,
            token_endpoint=str(payload.get("token_endpoint") or ""),
            client_id=str(payload.get("client_id") or ""),
            refresh_token=str(payload.get("refresh_token") or ""),
            scope=str(payload.get("scope") or ""),
            expires_at=float(payload.get("expires_at") or 0.0),
            token_type=str(payload.get("token_type") or "Bearer"),
        )

    def refreshed(self, *, transport: Transport | None = None) -> "TokenBundle":
        """Exchange the refresh token for a new access token (best effort)."""
        if not self.refresh_token or not self.token_endpoint:
            return self
        transport = transport or urllib_transport
        fields = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
        }
        status, payload = transport(self.token_endpoint, fields, {})
        if status >= 400 or not isinstance(payload, dict) or not payload.get("access_token"):
            return self
        return bundle_from_token_response(
            payload, token_endpoint=self.token_endpoint, client_id=self.client_id, scope=self.scope,
            fallback_refresh_token=self.refresh_token,
        )


def bundle_from_token_response(
    payload: dict, *, token_endpoint: str, client_id: str, scope: str, fallback_refresh_token: str = "",
) -> TokenBundle:
    access_token = str(payload.get("access_token") or "")
    if not access_token:
        raise OAuthError("The provider returned no access token.")
    expires_in = payload.get("expires_in")
    try:
        expires_at = time.time() + float(expires_in) if expires_in else 0.0
    except (TypeError, ValueError):
        expires_at = 0.0
    return TokenBundle(
        access_token=access_token,
        token_endpoint=token_endpoint,
        client_id=client_id,
        refresh_token=str(payload.get("refresh_token") or fallback_refresh_token),
        scope=str(payload.get("scope") or scope),
        expires_at=expires_at,
        token_type=str(payload.get("token_type") or "Bearer"),
    )


def unwrap_bearer(value: str | None) -> str | None:
    """Return the bearer string for a stored credential WITHOUT a network call.

    A plain API key is returned unchanged. An OAuth bundle yields its current
    access token. If the bundle has expired and cannot be refreshed here, the
    stale token is still returned so the caller gets an honest auth error rather
    than a silent failure.
    """
    if not value:
        return value
    bundle = TokenBundle.from_json(value)
    if bundle is None:
        return value
    return bundle.access_token


# ── Provider specs ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DeviceCodeProvider:
    id: str
    label: str
    credential_name: str
    device_authorization_endpoint: str
    token_endpoint: str
    scope: str = ""
    needs_client_id: bool = True
    needs_tenant: bool = False
    default_tenant: str = "common"
    docs_url: str = ""
    note: str = ""


@dataclass(frozen=True)
class LoopbackProvider:
    id: str
    label: str
    credential_name: str
    authorization_endpoint: str
    token_endpoint: str
    scope: str = ""
    needs_client_secret: bool = False
    docs_url: str = ""
    note: str = ""


DEVICE_CODE_PROVIDERS: tuple[DeviceCodeProvider, ...] = (
    DeviceCodeProvider(
        id="azure_openai",
        label="Microsoft Entra ID — Azure OpenAI / AI Foundry",
        credential_name="azure_openai",
        device_authorization_endpoint="https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode",
        token_endpoint="https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        scope="https://cognitiveservices.azure.com/.default offline_access",
        needs_client_id=True,
        needs_tenant=True,
        docs_url="https://learn.microsoft.com/entra/identity-platform/v2-oauth2-device-code",
        note="Sign in with the Microsoft account that owns the resource. Register a public-client app and paste its application (client) id.",
    ),
)

LOOPBACK_PROVIDERS: tuple[LoopbackProvider, ...] = (
    LoopbackProvider(
        id="google_gemini",
        label="Google — Gemini free tier (installed-app sign-in)",
        credential_name="google_gemini",
        authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        scope="openid email https://www.googleapis.com/auth/generative-language.retriever",
        docs_url="https://developers.google.com/identity/protocols/oauth2/native-app",
        note="Google device-code sign-in is not offered to installed apps, so this uses a loopback redirect. Create a Desktop OAuth client and paste its client id.",
    ),
)

_BY_ID = {provider.id: provider for provider in (*DEVICE_CODE_PROVIDERS, *LOOPBACK_PROVIDERS)}


def login_provider(provider_id: str):
    return _BY_ID.get(provider_id)


def login_providers() -> tuple:
    """Every provider that supports browser sign-in, device-code first."""
    return (*DEVICE_CODE_PROVIDERS, *LOOPBACK_PROVIDERS)


# ── Device authorization grant (RFC 8628) ────────────────────────────────────


@dataclass
class DeviceCodePrompt:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    verification_uri_complete: str = ""
    raw: dict = field(default_factory=dict, repr=False)

    def __repr__(self) -> str:  # never reveal the device code in logs
        return f"DeviceCodePrompt(user_code={self.user_code!r}, verification_uri={self.verification_uri!r})"


class DeviceCodeLogin:
    """Drive a device-code sign-in against a single provider."""

    def __init__(
        self,
        provider: DeviceCodeProvider,
        *,
        client_id: str,
        tenant: str = "",
        transport: Transport | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.provider = provider
        self.client_id = (client_id or "").strip()
        self.tenant = (tenant or "").strip() or provider.default_tenant
        self._transport = transport or urllib_transport
        self._sleep = sleep or time.sleep
        if provider.needs_client_id and not self.client_id:
            raise OAuthError("This provider needs an application (client) id before you can sign in.")

    def _endpoint(self, template: str) -> str:
        return template.replace("{tenant}", urllib.parse.quote(self.tenant, safe=""))

    def start(self) -> DeviceCodePrompt:
        status, payload = self._transport(
            self._endpoint(self.provider.device_authorization_endpoint),
            {"client_id": self.client_id, "scope": self.provider.scope},
            {},
        )
        if status >= 400 or not isinstance(payload, dict) or not payload.get("device_code"):
            raise OAuthError(_sanitize(payload if isinstance(payload, dict) else {}))
        try:
            interval = max(1, int(payload.get("interval") or 5))
        except (TypeError, ValueError):
            interval = 5
        return DeviceCodePrompt(
            device_code=str(payload["device_code"]),
            user_code=str(payload.get("user_code") or ""),
            verification_uri=str(payload.get("verification_uri") or payload.get("verification_url") or ""),
            verification_uri_complete=str(payload.get("verification_uri_complete") or ""),
            expires_in=int(payload.get("expires_in") or 900),
            interval=interval,
            raw=payload,
        )

    def poll(self, prompt: DeviceCodePrompt, *, should_cancel: Callable[[], bool] | None = None) -> TokenBundle:
        deadline = time.monotonic() + prompt.expires_in
        interval = prompt.interval
        while time.monotonic() < deadline:
            if should_cancel and should_cancel():
                raise OAuthError("Sign-in was cancelled.")
            self._sleep(interval)
            status, payload = self._transport(
                self._endpoint(self.provider.token_endpoint),
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": prompt.device_code,
                    "client_id": self.client_id,
                },
                {},
            )
            payload = payload if isinstance(payload, dict) else {}
            if status < 400 and payload.get("access_token"):
                return bundle_from_token_response(
                    payload, token_endpoint=self._endpoint(self.provider.token_endpoint),
                    client_id=self.client_id, scope=self.provider.scope,
                )
            error = str(payload.get("error") or "")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            if error == "expired_token":
                raise DeviceFlowExpired("The sign-in code expired before it was approved.")
            if error in {"access_denied", "authorization_declined", "consent_required"}:
                raise DeviceFlowDenied("Sign-in was declined or consent was not granted.")
            raise OAuthError(_sanitize(payload))
        raise DeviceFlowExpired("The sign-in code expired before it was approved.")


# ── Authorization code + PKCE on a loopback redirect (RFC 7636) ──────────────


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


class LoopbackLogin:
    """Build the authorization URL and exchange the returned code for tokens."""

    def __init__(
        self,
        provider: LoopbackProvider,
        *,
        client_id: str,
        client_secret: str = "",
        redirect_uri: str,
        transport: Transport | None = None,
    ) -> None:
        self.provider = provider
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.redirect_uri = redirect_uri
        self._transport = transport or urllib_transport
        if not self.client_id:
            raise OAuthError("This provider needs an application (client) id before you can sign in.")

    def authorization_url(self, *, state: str, code_verifier: str) -> str:
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        query = urllib.parse.urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.provider.scope,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        })
        return f"{self.provider.authorization_endpoint}?{query}"

    def exchange(self, *, code: str, code_verifier: str) -> TokenBundle:
        fields = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "code_verifier": code_verifier,
        }
        if self.client_secret:
            fields["client_secret"] = self.client_secret
        status, payload = self._transport(self.provider.token_endpoint, fields, {})
        if status >= 400 or not isinstance(payload, dict) or not payload.get("access_token"):
            raise OAuthError(_sanitize(payload if isinstance(payload, dict) else {}))
        return bundle_from_token_response(
            payload, token_endpoint=self.provider.token_endpoint,
            client_id=self.client_id, scope=self.provider.scope,
        )

    def prepare(self) -> "tuple[str, str, str]":
        """Return ``(authorization_url, state, code_verifier)`` for a fresh attempt."""
        verifier, _ = _pkce_pair()
        state = secrets.token_urlsafe(24)
        return self.authorization_url(state=state, code_verifier=verifier), state, verifier


def store_token(credential_store, credential_name: str, bundle: TokenBundle) -> None:
    """Persist an OAuth bundle under the provider's credential name."""
    credential_store.set(credential_name, bundle.to_json())


def clear_token(credential_store, credential_name: str) -> None:
    credential_store.delete(credential_name)
