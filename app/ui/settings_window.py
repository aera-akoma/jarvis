from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox,
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
from PySide6.QtCore import Signal

from app.config import AppConfig
from app.core.settings_manager import SettingsManager
from app.security.credentials import CredentialStore
from app.startup import StartupManager
from app.export_import.import_export import ExportImportManager


class SettingsWindow(QDialog):
    data_restored = Signal(object)

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self.config = config or AppConfig()
        self.settings = SettingsManager(self.config)
        self.credentials = CredentialStore()
        self._key_status_text = self._get_key_status()
        self.startup_manager = StartupManager()
        self.export_import = ExportImportManager(database_path=str(self.config.database_path), root=str(self.config.data_dir_path / "exports"))
        self.setWindowTitle("Jarvis Settings")
        self.resize(480, 360)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.theme_input = QLineEdit(self.settings.get("theme", self.config.theme) or self.config.theme)
        self.model_input = QLineEdit(self.settings.get("default_model", self.config.default_model()) or self.config.default_model())
        self.base_url_input = QLineEdit(self.settings.get("openai_base_url") or os.getenv("JARVIS_OPENAI_BASE_URL") or os.getenv("OPENCODE_BASE_URL") or "")
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText(
            "Leave blank to keep the saved key" if self._key_status_text.startswith("A key is saved") else "Enter API key"
        )
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.startup_checkbox = QCheckBox("Launch Jarvis on Windows startup")
        self.startup_checkbox.setChecked(self.startup_manager.is_enabled())

        form.addRow("Theme", self.theme_input)
        form.addRow("Default model", self.model_input)
        form.addRow("Runtime URL", self.base_url_input)
        form.addRow("API key", self.api_key_input)
        layout.addLayout(form)
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

    def _get_key_status(self) -> str:
        if self.credentials.storage_error:
            return f"Secure credential storage is unavailable: {self.credentials.storage_error}"
        try:
            if self.credentials.get("OpenAI"):
                return "A key is saved securely with Windows DPAPI (hidden). This confirms local storage only; provider acceptance is checked when you send a message. Leave blank to keep it."
            return "No API key is saved. Enter the provider key above; it will be stored securely with Windows DPAPI."
        except (OSError, RuntimeError) as exc:
            return f"Could not check secure credential storage: {exc}"

    def _ask_passphrase(self, title: str, prompt: str) -> str | None:
        value, accepted = QInputDialog.getText(self, title, prompt, QLineEdit.EchoMode.Password)
        return value if accepted else None

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
        self.settings.set("theme", self.theme_input.text().strip() or self.config.theme)
        self.settings.set("default_model", self.model_input.text().strip() or self.config.default_model())

        runtime_url = self.base_url_input.text().strip()
        if runtime_url:
            self.settings.set("openai_base_url", runtime_url)
            os.environ["JARVIS_OPENAI_BASE_URL"] = runtime_url
        elif os.getenv("JARVIS_OPENAI_BASE_URL"):
            self.settings.set("openai_base_url", "")
            os.environ.pop("JARVIS_OPENAI_BASE_URL", None)

        new_api_key = self.api_key_input.text().strip()
        if new_api_key:
            try:
                self.credentials.replace_all("OpenAI", new_api_key)
            except (OSError, RuntimeError) as exc:
                QMessageBox.critical(self, "Secure storage unavailable", str(exc))
                return
            self.credential_status.setText(
                "The new key replaced the previously saved key. Exactly one key is kept in Jarvis secure storage."
            )
            QMessageBox.information(
                self, "Saved securely",
                "The new API key replaced all previously stored keys and was saved with Windows DPAPI. Jarvis checks whether the provider accepts it when you send a message. For security, the field stays blank when you reopen Settings.",
            )

        if self.startup_checkbox.isChecked():
            self.startup_manager.enable_startup()
        else:
            self.startup_manager.disable_startup()
        self.close()

    def clear_key(self) -> None:
        try:
            self.credentials.delete("OpenAI")
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "Could not clear credential", str(exc))
            return
        self.api_key_input.clear()
        self.credential_status.setText(
            "No API key is saved. Enter the provider key above; it will be stored securely with Windows DPAPI."
        )
        QMessageBox.information(self, "Removed", "The stored API key has been cleared.")
