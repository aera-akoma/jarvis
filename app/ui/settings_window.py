from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from PySide6.QtCore import QThread, Signal

from app.config import AppConfig
from app.core.settings_manager import SettingsManager
from app.security.credentials import CredentialStore
from app.startup import StartupManager
from app.export_import.import_export import ExportImportManager
from app.opencode.client import OpenCodeClient
from app.providers import default_preset, get_preset, preset_order
from app.ui.login_dialog import LoginDialog


class ConnectionTestWorker(QThread):
    result_ready = Signal(object)

    def __init__(self, base_url: str, api_key: str | None, credential_name: str = "OpenAI") -> None:
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.credential_name = credential_name

    def run(self) -> None:
        client = OpenCodeClient(base_url=self.base_url, api_key=self.api_key, credential_name=self.credential_name)
        models = client.discover_models()
        self.result_ready.emit({"models": models, "error": client.last_error})


class ModelAccessTestWorker(QThread):
    result_ready = Signal(object)

    def __init__(self, base_url: str, api_key: str | None, model: str, credential_name: str = "OpenAI") -> None:
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.credential_name = credential_name

    def run(self) -> None:
        client = OpenCodeClient(base_url=self.base_url, api_key=self.api_key, credential_name=self.credential_name)
        result = client.probe_model_access(self.model)
        result["model"] = self.model
        self.result_ready.emit(result)


class SettingsWindow(QDialog):
    data_restored = Signal(object)

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self.config = config or AppConfig()
        self.settings = SettingsManager(self.config)
        self.credentials = CredentialStore()
        stored_provider_id = self.settings.get("provider_id") or ""
        # Installs upgraded from before provider presets existed have no
        # provider_id and keep their key under the legacy "OpenAI" name, so the
        # default resolves to "custom" (credential_name "OpenAI") and their
        # working setup is preserved until they explicitly choose a preset.
        self._initial_preset = get_preset(stored_provider_id) or default_preset()
        self._key_status_text = self._get_key_status()
        self.startup_manager = StartupManager()
        self.export_import = ExportImportManager(database_path=str(self.config.database_path), root=str(self.config.data_dir_path / "exports"))
        self.setWindowTitle("Jarvis Settings")
        self.resize(520, 560)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.theme_input = QLineEdit(self.settings.get("theme", self.config.theme) or self.config.theme)
        self.model_input = QLineEdit(self.settings.get("default_model", self.config.default_model()) or self.config.default_model())
        self.fallback_input = QLineEdit(self.settings.get("model_fallback", "") or "")
        self.fallback_input.setPlaceholderText("Optional: comma-separated models to try when one hits its quota")
        self.base_url_input = QLineEdit(self.settings.get("openai_base_url") or os.getenv("JARVIS_OPENAI_BASE_URL") or os.getenv("OPENCODE_BASE_URL") or "")

        self.provider_input = QComboBox()
        for preset in preset_order():
            self.provider_input.addItem(preset.label, preset.id)
        self._select_provider(self._initial_preset.id)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText(
            "Leave blank to keep the saved key" if self._key_status_text.startswith("A key is saved") else "Enter API key"
        )
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.startup_checkbox = QCheckBox("Launch Jarvis on Windows startup")
        self.startup_checkbox.setChecked(self.startup_manager.is_enabled())

        form.addRow("Theme", self.theme_input)
        form.addRow("Provider", self.provider_input)
        form.addRow("Default model", self.model_input)
        form.addRow("Fallback models", self.fallback_input)
        form.addRow("Runtime URL", self.base_url_input)
        self.provider_hint = QLabel("")
        self.provider_hint.setWordWrap(True)
        form.addRow("", self.provider_hint)
        form.addRow("API key", self.api_key_input)
        self.test_connection_button = QPushButton("Test connection (catalog only)")
        self.test_connection_button.clicked.connect(self.test_connection)
        form.addRow("", self.test_connection_button)
        self.test_access_button = QPushButton("Test model access (sends one tiny request)")
        self.test_access_button.clicked.connect(self.test_model_access)
        form.addRow("", self.test_access_button)
        self.login_button = QPushButton("Sign in with browser…")
        self.login_button.setToolTip("Sign in through the provider's own page instead of pasting a key.")
        self.login_button.clicked.connect(self.open_login_dialog)
        form.addRow("", self.login_button)
        layout.addLayout(form)
        self.connection_status = QLabel("Test connection checks the public model catalog only. Use Test model access to confirm the saved key can actually reach a model.")
        self.connection_status.setWordWrap(True)
        layout.addWidget(self.connection_status)
        self.access_status = QLabel("")
        self.access_status.setWordWrap(True)
        layout.addWidget(self.access_status)
        self._connection_worker: ConnectionTestWorker | None = None
        self._access_worker: ModelAccessTestWorker | None = None
        layout.addWidget(self.startup_checkbox)

        transfer_row = QHBoxLayout()
        export_button = QPushButton("Export encrypted backup…")
        export_button.clicked.connect(self.export_backup)
        import_button = QPushButton("Import / restore backup…")
        import_button.clicked.connect(self.import_backup)
        transfer_row.addWidget(export_button)
        transfer_row.addWidget(import_button)
        layout.addLayout(transfer_row)

        buttons = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        buttons.addWidget(save_button)

        clear_button = QPushButton("Clear key")
        clear_button.clicked.connect(self.clear_key)
        buttons.addWidget(clear_button)

        layout.addLayout(buttons)

        self.credential_status = QLabel(self._key_status_text)
        self.credential_status.setWordWrap(True)
        layout.addWidget(self.credential_status)

        self._update_provider_fields(self._initial_preset, initial=True)
        self.provider_input.currentIndexChanged.connect(lambda _index: self._update_provider_fields(self._selected_preset()))

    def _select_provider(self, provider_id: str) -> None:
        index = self.provider_input.findData(provider_id)
        self.provider_input.setCurrentIndex(index if index >= 0 else 0)

    def _selected_preset(self):
        return get_preset(self.provider_input.currentData()) or default_preset()

    def _update_provider_fields(self, preset, *, initial: bool = False) -> None:
        if preset.base_url and (not initial or not self.base_url_input.text().strip()):
            self.base_url_input.setText(preset.base_url)
        notes = [preset.note] if preset.note else []
        if preset.docs_url:
            notes.append(f"Get a key: {preset.docs_url}")
        if preset.keyless:
            notes.append("A key is optional for this provider.")
        if preset.in_opencode:
            notes.append("OpenCode also supports this provider.")
        notes.append("Jarvis keeps a separate key per provider.")
        self.provider_hint.setText(" ".join(notes))
        self._refresh_key_status(preset)

    def _refresh_key_status(self, preset) -> None:
        text = self._get_key_status(preset.credential_name)
        self.credential_status.setText(text)
        self.api_key_input.setPlaceholderText(
            "Leave blank to keep the saved key" if text.startswith("A key is saved") else "Enter API key"
        )

    def _get_key_status(self, credential_name: str | None = None) -> str:
        credential_name = credential_name or self._initial_preset.credential_name
        if self.credentials.storage_error:
            return f"Secure credential storage is unavailable: {self.credentials.storage_error}"
        try:
            if self.credentials.get(credential_name):
                return "A key is saved securely with Windows DPAPI (hidden). This confirms local storage only; provider acceptance is checked when you send a message. Leave blank to keep it."
            return "No API key is saved for this provider. Enter the provider key above; it will be stored securely with Windows DPAPI."
        except (OSError, RuntimeError) as exc:
            return f"Could not check secure credential storage: {exc}"

    def _ask_passphrase(self, title: str, prompt: str) -> str | None:
        value, accepted = QInputDialog.getText(self, title, prompt, QLineEdit.EchoMode.Password)
        return value if accepted else None

    def test_connection(self) -> None:
        if self._connection_worker is not None and self._connection_worker.isRunning():
            return
        runtime_url = self.base_url_input.text().strip()
        if not runtime_url:
            self.connection_status.setText("Enter a provider runtime URL before testing the connection.")
            return
        api_key = self.api_key_input.text().strip() or None
        self.connection_status.setText("Testing catalog GET in the background…")
        self.test_connection_button.setEnabled(False)
        worker = ConnectionTestWorker(runtime_url, api_key, self._selected_preset().credential_name)
        self._connection_worker = worker
        worker.result_ready.connect(self._connection_test_finished)
        worker.finished.connect(self._connection_worker_finished)
        worker.start()

    def _connection_test_finished(self, result: dict) -> None:
        models = result.get("models") or []
        if not models:
            self.connection_status.setText(result.get("error") or "Catalog GET failed without a safe diagnostic.")
            return
        message = (
            f"Catalog GET succeeded; {len(models)} Chat Completions-compatible model(s) found. "
            "This does not verify chat-completions access or model permissions."
        )
        default_model = self.model_input.text().strip()
        if default_model:
            message += (
                f" Default model {default_model!r} is available."
                if default_model in models
                else f" Default model {default_model!r} is NOT in this compatible list; pick another in Settings."
            )
        self.connection_status.setText(message)

    def _connection_worker_finished(self) -> None:
        self.test_connection_button.setEnabled(True)
        worker = self.sender()
        if worker is self._connection_worker:
            self._connection_worker = None
        if worker is not None:
            worker.deleteLater()

    def test_model_access(self) -> None:
        if self._access_worker is not None and self._access_worker.isRunning():
            return
        runtime_url = self.base_url_input.text().strip()
        if not runtime_url:
            self.access_status.setText("Enter a provider runtime URL before testing model access.")
            return
        model = self.model_input.text().strip() or self.config.default_model()
        api_key = self.api_key_input.text().strip() or None
        self.access_status.setText(f"Testing access to {model!r} with one small request…")
        self.test_access_button.setEnabled(False)
        worker = ModelAccessTestWorker(runtime_url, api_key, model, self._selected_preset().credential_name)
        self._access_worker = worker
        worker.result_ready.connect(self._access_test_finished)
        worker.finished.connect(self._access_worker_finished)
        worker.start()

    def _access_test_finished(self, result: dict) -> None:
        if result.get("ok"):
            self.access_status.setText(
                f"Access confirmed for {result.get('model')!r}: the provider accepted the credential and answered. "
                "The saved key can reach this model."
            )
        else:
            self.access_status.setText(
                result.get("error") or "Model access test failed without a safe provider diagnostic."
            )

    def _access_worker_finished(self) -> None:
        self.test_access_button.setEnabled(True)
        worker = self.sender()
        if worker is self._access_worker:
            self._access_worker = None
        if worker is not None:
            worker.deleteLater()

    def open_login_dialog(self) -> None:
        dialog = LoginDialog(self.credentials, self)
        dialog.signed_in.connect(self._on_signed_in)
        dialog.exec()

    def _on_signed_in(self, credential_name: str, provider_id: str) -> None:
        # If the signed-in provider maps to a preset, select it so the token is
        # actually used. Azure OpenAI / custom endpoints stay on the current
        # provider; the token is still saved under its own credential name.
        preset = get_preset(provider_id)
        if preset is not None:
            self._select_provider(preset.id)
            self._update_provider_fields(preset)
        self._refresh_key_status(self._selected_preset())
        self.connection_status.setText(
            f"Signed in. The browser token is stored under {credential_name!r}; "
            "use Test model access to confirm it reaches a model."
        )

    def closeEvent(self, event) -> None:
        if self._connection_worker is not None and self._connection_worker.isRunning():
            self._connection_worker.requestInterruption()
            self._connection_worker.wait(6500)
        if self._access_worker is not None and self._access_worker.isRunning():
            self._access_worker.requestInterruption()
            self._access_worker.wait(32000)
        super().closeEvent(event)

    def export_backup(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Save encrypted Jarvis backup", str(self.config.data_dir_path / "exports" / "jarvis-backup.jarvisbackup"), "Jarvis encrypted backup (*.jarvisbackup)")
        if not path:
            return
        passphrase = self._ask_passphrase("Encrypt backup", "Create a passphrase (at least 12 characters). Keep it safe; it cannot be recovered.")
        if passphrase is None:
            return
        confirmation = self._ask_passphrase("Confirm passphrase", "Enter the backup passphrase again.")
        if confirmation is None:
            return
        if passphrase != confirmation:
            QMessageBox.warning(self, "Passphrases do not match", "The backup was not created.")
            return
        try:
            payload = self.export_import.build_backup()
            output = self.export_import.write_payload_backup(path, passphrase, payload)
            preview = self.export_import.preview(payload)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))
            return
        QMessageBox.information(
            self, "Encrypted backup created",
            f"Saved encrypted backup to:\n{output}\n\n"
            f"Conversations: {preview['conversations']} · Messages: {preview['messages']} · Memories: {preview['memories']} · Workflows: {preview['workflows']}\n"
            f"Credential strings redacted: {payload.get('redacted_secret_count', 0)}\n"
            "Credentials are excluded. Store the passphrase separately.",
        )

    def import_backup(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Open encrypted Jarvis backup", str(self.config.data_dir_path / "exports"), "Jarvis encrypted backup (*.jarvisbackup)")
        if not path:
            return
        passphrase = self._ask_passphrase("Unlock backup", "Enter the backup passphrase.")
        if passphrase is None:
            return
        try:
            payload = self.export_import.read_backup(path, passphrase)
            preview = self.export_import.preview(payload)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "Backup could not be opened", str(exc))
            return
        box = QMessageBox(self)
        box.setWindowTitle("Restore Jarvis data")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            f"Backup contents:\nConversations: {preview['conversations']} · Messages: {preview['messages']} · "
            f"Memories: {preview['memories']} · Workflows: {preview['workflows']}\n\n"
            + "\n".join(payload.get("notes", [])) + "\n\n"
            "Choose Merge to keep current data and add the backup. Choose Replace to replace Jarvis personal data. "
            "Credentials are preserved and never imported."
        )
        merge_button = box.addButton("Merge", QMessageBox.ButtonRole.AcceptRole)
        replace_button = box.addButton("Replace personal data", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in (merge_button, replace_button):
            return
        strategy = "merge" if clicked is merge_button else "replace"
        if strategy == "replace":
            answer = QMessageBox.question(
                self, "Confirm replacement",
                "This will remove existing conversations, messages, memories, and workflows before restoring the backup. This cannot be undone. Replace them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            counts = self.export_import.restore_payload(payload, strategy=strategy)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return
        self.data_restored.emit({"strategy": strategy, "counts": counts})
        QMessageBox.information(self, "Restore complete", f"Imported data using {strategy}.\n\n" + "\n".join(f"{name.title()}: {count}" for name, count in counts.items()))

    def save_settings(self) -> None:
        preset = self._selected_preset()
        self.settings.set("provider_id", preset.id)
        self.settings.set("theme", self.theme_input.text().strip() or self.config.theme)
        self.settings.set("default_model", self.model_input.text().strip() or self.config.default_model())
        self.settings.set("model_fallback", self._normalize_fallback(self.fallback_input.text()))

        runtime_url = self.base_url_input.text().strip()
        # Persist to settings only. Mutating the process environment here would
        # leak the choice into other code and tests.
        self.settings.set("openai_base_url", runtime_url)

        new_api_key = self.api_key_input.text().strip()
        if new_api_key:
            try:
                # Per-provider credentials: saving a Groq key never overwrites
                # the OpenCode key (each provider has its own DPAPI entry).
                self.credentials.set(preset.credential_name, new_api_key)
            except (OSError, RuntimeError) as exc:
                QMessageBox.critical(self, "Secure storage unavailable", str(exc))
                return
            self.credential_status.setText(
                f"The key for {preset.label} was saved with Windows DPAPI. Other providers keep their own keys."
            )
            QMessageBox.information(
                self, "Saved securely",
                f"The API key for {preset.label} was saved with Windows DPAPI. Jarvis checks whether the provider "
                "accepts it when you send a message. For security, the field stays blank when you reopen Settings.",
            )

        if self.startup_checkbox.isChecked():
            self.startup_manager.enable_startup()
        else:
            self.startup_manager.disable_startup()
        self.close()

    @staticmethod
    def _normalize_fallback(text: str) -> str:
        models = [model.strip() for chunk in (text or "").splitlines() for model in chunk.split(",")]
        seen: list[str] = []
        for model in models:
            if model and model not in seen:
                seen.append(model)
        return ", ".join(seen)

    def clear_key(self) -> None:
        preset = self._selected_preset()
        try:
            self.credentials.delete(preset.credential_name)
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "Could not clear credential", str(exc))
            return
        self.api_key_input.clear()
        self.credential_status.setText(
            "No API key is saved for this provider. Enter the provider key above; it will be stored securely with Windows DPAPI."
        )
        QMessageBox.information(self, "Removed", f"The stored key for {preset.label} has been cleared.")
