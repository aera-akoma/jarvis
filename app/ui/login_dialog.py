"""Browser sign-in dialog for model providers.

The dialog is deliberately explicit about what each provider needs and what it
does: it opens the provider's own page, the user approves there, and the
resulting token is written straight to the Windows DPAPI credential store. No
token is ever displayed, logged, or sent anywhere except the provider.
"""

from __future__ import annotations

import http.server
import threading
import urllib.parse

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.security.credentials import CredentialStore
from app.security.oauth import (
    DEVICE_CODE_PROVIDERS,
    LOOPBACK_PROVIDERS,
    DeviceCodeLogin,
    LoopbackLogin,
    OAuthError,
    login_providers,
    store_token,
)


class DeviceCodeWorker(QThread):
    prompt_ready = Signal(object)
    token_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, login: DeviceCodeLogin, parent=None) -> None:
        super().__init__(parent)
        self._login = login

    def run(self) -> None:
        try:
            prompt = self._login.start()
            self.prompt_ready.emit(prompt)
            bundle = self._login.poll(
                prompt,
                should_cancel=self.isInterruptionRequested,
            )
        except OAuthError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never leak a traceback to the UI
            self.failed.emit(f"Sign-in failed ({type(exc).__name__}).")
            return
        self.token_ready.emit(bundle)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silence the default stderr logging
        return

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self.server.received = {key: values[0] for key, values in params.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body style='font-family:sans-serif'><h2>Jarvis sign-in complete</h2>"
            b"<p>You can close this tab and return to Jarvis.</p></body></html>"
        )


class LoopbackReceiver:
    """A one-shot local HTTP server that captures the OAuth redirect."""

    def __init__(self, host: str = "127.0.0.1") -> None:
        self._server = http.server.HTTPServer((host, 0), _CallbackHandler)
        self._server.received = None  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def redirect_uri(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/callback"

    def wait(self, timeout: float, should_cancel) -> dict:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            received = getattr(self._server, "received", None)
            if received is not None:
                return dict(received)
            if should_cancel and should_cancel():
                raise OAuthError("Sign-in was cancelled.")
            time.sleep(0.2)
        raise OAuthError("Timed out waiting for the browser to return to Jarvis.")

    def close(self) -> None:
        try:
            self._server.shutdown()
        except OSError:
            pass
        self._server.server_close()


class LoopbackWorker(QThread):
    open_url = Signal(str)
    token_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, provider, *, client_id: str, client_secret: str = "", parent=None) -> None:
        super().__init__(parent)
        self._provider = provider
        self._client_id = client_id
        self._client_secret = client_secret

    def run(self) -> None:
        receiver = None
        try:
            receiver = LoopbackReceiver()
            login = LoopbackLogin(
                self._provider,
                client_id=self._client_id,
                client_secret=self._client_secret,
                redirect_uri=receiver.redirect_uri,
            )
            url, state, verifier = login.prepare()
            self.open_url.emit(url)
            received = receiver.wait(300, self.isInterruptionRequested)
            if received.get("state") != state:
                raise OAuthError("The sign-in response did not match this request.")
            if received.get("error"):
                raise OAuthError(str(received.get("error_description") or received["error"]))
            code = received.get("code")
            if not code:
                raise OAuthError("The provider returned no authorization code.")
            bundle = login.exchange(code=code, code_verifier=verifier)
        except OAuthError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Sign-in failed ({type(exc).__name__}).")
            return
        finally:
            if receiver is not None:
                receiver.close()
        self.token_ready.emit(bundle)


class LoginDialog(QDialog):
    """Pick a provider, sign in through the browser, store the token."""

    signed_in = Signal(str, str)  # credential_name, provider_id

    def __init__(self, credentials: CredentialStore | None = None, parent=None) -> None:
        super().__init__(parent)
        self.credentials = credentials or CredentialStore()
        self._worker = None
        self._provider = None
        self.setWindowTitle("Sign in to a model provider")
        self.resize(560, 460)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.provider_input = QComboBox()
        for provider in login_providers():
            kind = "device code" if provider in DEVICE_CODE_PROVIDERS else "browser"
            self.provider_input.addItem(f"{provider.label} ({kind})", provider.id)
        form.addRow("Provider", self.provider_input)

        self.note_label = QLabel("")
        self.note_label.setWordWrap(True)
        form.addRow("", self.note_label)

        self.client_id_input = QLineEdit()
        self.client_id_input.setPlaceholderText("Your app's client id (from the provider's developer console)")
        form.addRow("Client id", self.client_id_input)

        self.tenant_input = QLineEdit()
        self.tenant_input.setPlaceholderText("Directory (tenant) id, or 'common'")
        form.addRow("Tenant", self.tenant_input)

        self.client_secret_input = QLineEdit()
        self.client_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.client_secret_input.setPlaceholderText("Optional; only if the provider requires it")
        form.addRow("Client secret", self.client_secret_input)

        layout.addLayout(form)

        self.start_button = QPushButton("Start sign-in")
        self.start_button.clicked.connect(self.start_sign_in)
        layout.addWidget(self.start_button)

        code_row = QHBoxLayout()
        self.user_code_input = QLineEdit()
        self.user_code_input.setReadOnly(True)
        self.user_code_input.setPlaceholderText("The code to type at the provider will appear here")
        code_row.addWidget(self.user_code_input)
        self.open_button = QPushButton("Open sign-in page")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_page)
        code_row.addWidget(self.open_button)
        layout.addLayout(code_row)

        self.status = QLabel(
            "Jarvis opens the provider's official page; you approve there. "
            "The token is stored with Windows DPAPI and never shown or logged."
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.provider_input.currentIndexChanged.connect(self._update_fields)
        self._update_fields()

    def _current_provider(self):
        from app.security.oauth import login_provider

        return login_provider(self.provider_input.currentData())

    def _update_fields(self) -> None:
        provider = self._current_provider()
        self._provider = provider
        if provider is None:
            return
        notes = [provider.note] if getattr(provider, "note", "") else []
        if getattr(provider, "docs_url", ""):
            notes.append(f"Setup: {provider.docs_url}")
        self.note_label.setText(" ".join(notes))
        is_device = provider in DEVICE_CODE_PROVIDERS
        self.tenant_input.setEnabled(is_device and getattr(provider, "needs_tenant", False))
        self.client_secret_input.setEnabled(getattr(provider, "needs_client_secret", False))
        self.user_code_input.clear()
        self._verification_url = ""

    def _open_page(self) -> None:
        if getattr(self, "_verification_url", ""):
            QDesktopServices.openUrl(QUrl(self._verification_url))

    def start_sign_in(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        provider = self._provider
        if provider is None:
            return
        client_id = self.client_id_input.text().strip()
        if provider in DEVICE_CODE_PROVIDERS:
            try:
                login = DeviceCodeLogin(
                    provider,
                    client_id=client_id,
                    tenant=self.tenant_input.text().strip(),
                )
            except OAuthError as exc:
                QMessageBox.warning(self, "Sign-in not started", str(exc))
                return
            worker = DeviceCodeWorker(login)
            worker.prompt_ready.connect(self._device_prompt)
        else:
            worker = LoopbackWorker(
                provider,
                client_id=client_id,
                client_secret=self.client_secret_input.text().strip(),
            )
            worker.open_url.connect(self._open_url)
        worker.token_ready.connect(self._token_ready)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        self.start_button.setEnabled(False)
        self.status.setText("Waiting for sign-in… follow the provider page.")
        worker.start()

    def _device_prompt(self, prompt) -> None:
        self.user_code_input.setText(prompt.user_code)
        self._verification_url = prompt.verification_uri_complete or prompt.verification_uri
        self.open_button.setEnabled(bool(self._verification_url))
        self.status.setText(
            f"Open {prompt.verification_uri} and enter the code shown above. Jarvis is polling for approval."
        )
        self._open_page()

    def _open_url(self, url: str) -> None:
        self._verification_url = url
        self.open_button.setEnabled(True)
        self.status.setText("Complete the sign-in in your browser, then return here.")
        self._open_page()

    def _token_ready(self, bundle) -> None:
        provider = self._provider
        try:
            store_token(self.credentials, provider.credential_name, bundle)
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "Secure storage unavailable", str(exc))
            return
        self.status.setText(f"Signed in. The token for {provider.label} was stored securely.")
        self.signed_in.emit(provider.credential_name, provider.id)
        QMessageBox.information(
            self, "Signed in",
            f"Signed in to {provider.label}. The token is stored with Windows DPAPI. "
            "If it expires, sign in again from Settings.",
        )

    def _failed(self, message: str) -> None:
        self.status.setText(message)
        QMessageBox.warning(self, "Sign-in failed", message)

    def _worker_finished(self) -> None:
        self.start_button.setEnabled(True)
        worker = self.sender()
        if worker is self._worker:
            self._worker = None
        if worker is not None:
            worker.deleteLater()

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(5000)
        super().closeEvent(event)
