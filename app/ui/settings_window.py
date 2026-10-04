from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.config import AppConfig
from app.core.settings_manager import SettingsManager
from app.security.credentials import CredentialStore
from app.startup import StartupManager


class SettingsWindow(QDialog):
    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self.config = config or AppConfig()
        self.settings = SettingsManager(self.config)
        self.credentials = CredentialStore()
        self.startup_manager = StartupManager()
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
        self.api_key_input.setPlaceholderText("Enter API key")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.startup_checkbox = QCheckBox("Launch Jarvis on Windows startup")
        self.startup_checkbox.setChecked(self.startup_manager.is_enabled())

        form.addRow("Theme", self.theme_input)
        form.addRow("Default model", self.model_input)
        form.addRow("Runtime URL", self.base_url_input)
        form.addRow("API key", self.api_key_input)
        layout.addLayout(form)
        layout.addWidget(self.startup_checkbox)

        buttons = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        buttons.addWidget(save_button)

        clear_button = QPushButton("Clear key")
        clear_button.clicked.connect(self.clear_key)
        buttons.addWidget(clear_button)

        layout.addLayout(buttons)

        status = QLabel("Credentials are stored securely in the OS credential store.")
        layout.addWidget(status)

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

        if self.api_key_input.text().strip():
            self.credentials.set("OpenAI", self.api_key_input.text().strip())
            os.environ["OPENCODE_API_KEY"] = self.api_key_input.text().strip()
            QMessageBox.information(self, "Saved", "Your API key has been stored securely.")

        if self.startup_checkbox.isChecked():
            self.startup_manager.enable_startup()
        else:
            self.startup_manager.disable_startup()
        self.close()

    def clear_key(self) -> None:
        self.credentials.delete("OpenAI")
        self.api_key_input.clear()
        QMessageBox.information(self, "Removed", "The stored API key has been cleared.")
