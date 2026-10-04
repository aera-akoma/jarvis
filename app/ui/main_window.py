from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig
from app.core.session_manager import SessionManager
from app.memory.memory_manager import MemoryManager
from app.opencode.client import OpenCodeClient
from app.search.search_manager import SearchManager
from app.tasks import TaskManager
from app.ui.memory_view import MemoryView
from app.ui.settings_window import SettingsWindow
from app.voice.voice_manager import VoiceManager


class MainWindow(QMainWindow):
    def __init__(self, config: Optional[AppConfig] = None) -> None:
        if QApplication.instance() is None:
            QApplication([])
        super().__init__()
        self.config = config or AppConfig()
        self.session_manager = SessionManager(self.config)
        self.memory_manager = MemoryManager(self.config.database_path)
        self.search_manager = SearchManager()
        self.voice_manager = VoiceManager()
        self.runtime = OpenCodeClient()
        self.task_manager = TaskManager()
        self.current_task = self.task_manager.create_task("Current session", project_path=self.config.data_dir)
        self.active_conversation = self.session_manager.create_conversation("New Chat", self.config.default_model())
        self.setWindowTitle(self.config.app_name)
        self.resize(1200, 800)
        self._build_ui()
        self._refresh_history()
        self.apply_theme(self.config.theme)

    def _populate_model_selector(self) -> None:
        self.model_selector.clear()
        models = self.runtime.available_models()
        if not models:
            self.model_selector.addItem("OpenCode runtime unavailable")
            self.model_selector.setEnabled(False)
            return

        self.model_selector.addItems(models)
        if self.config.default_model() in models:
            self.model_selector.setCurrentText(self.config.default_model())
        else:
            self.model_selector.setCurrentIndex(0)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(12)

        title = QLabel("JARVIS")
        title.setObjectName("jarvisTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        sidebar_layout.addWidget(title)

        self.new_chat_button = QPushButton("+ New Chat")
        self.new_chat_button.setObjectName("newChat")
        self.new_chat_button.clicked.connect(self.new_chat)
        sidebar_layout.addWidget(self.new_chat_button)

        chats = QLabel("Chats")
        chats.setObjectName("sectionLabel")
        sidebar_layout.addWidget(chats)

        self.conversation_list = QListWidget()
        self._populate_conversation_list()
        sidebar_layout.addWidget(self.conversation_list)

        settings_button = QPushButton("⚙ Settings")
        settings_button.setObjectName("settingsButton")
        settings_button.clicked.connect(self.show_settings)
        sidebar_layout.addWidget(settings_button)

        memory_button = QPushButton("🧠 Memory")
        memory_button.setObjectName("memoryButton")
        memory_button.clicked.connect(self.show_memory)
        sidebar_layout.addWidget(memory_button)

        root_layout.addWidget(sidebar, 30)

        content = QFrame()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(20, 20, 20, 10)
        header_label = QLabel("Jarvis")
        header_label.setObjectName("headerLabel")
        header.addWidget(header_label)
        header.addStretch()
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        header.addWidget(self.status_label)
        self.emergency_stop_button = QPushButton("🛑 STOP")
        self.emergency_stop_button.clicked.connect(self.stop_current_task)
        header.addWidget(self.emergency_stop_button)
        header_button = QPushButton("⚙")
        header_button.clicked.connect(self.show_settings)
        header.addWidget(header_button)
        content_layout.addLayout(header)

        self.chat_history = QTextBrowser()
        self.chat_history.setObjectName("chatHistory")
        self.chat_history.setReadOnly(True)
        self.chat_history.setOpenExternalLinks(False)
        content_layout.addWidget(self.chat_history, 1)

        composer = QFrame()
        composer.setObjectName("composer")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(12, 10, 12, 12)
        composer_layout.setSpacing(8)

        attach = QPushButton("📎")
        voice = QPushButton("🎤")
        voice.clicked.connect(self.show_voice_status)
        search = QPushButton("Search")
        search.clicked.connect(self.show_search)
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("Ask Jarvis anything...")
        self.prompt_input.returnPressed.connect(self.send_message)

        self.model_selector = QComboBox()
        self._populate_model_selector()

        send = QPushButton("Send →")
        send.clicked.connect(self.send_message)

        composer_layout.addWidget(attach)
        composer_layout.addWidget(voice)
        composer_layout.addWidget(search)
        composer_layout.addWidget(self.prompt_input, 1)
        composer_layout.addWidget(self.model_selector)
        composer_layout.addWidget(send)
        content_layout.addWidget(composer)

        root_layout.addWidget(content, 70)
        self.setCentralWidget(root)

    def _populate_conversation_list(self) -> None:
        self.conversation_list.clear()
        for conversation in self.session_manager.list_conversations():
            self.conversation_list.addItem(conversation["title"])

    def new_chat(self) -> None:
        self.active_conversation = self.session_manager.create_conversation("New Chat", self.model_selector.currentText() if hasattr(self, "model_selector") else self.config.default_model())
        self.prompt_input.clear()
        self._refresh_history()
        self._populate_conversation_list()

    def _refresh_history(self) -> None:
        self.chat_history.clear()
        messages = self.session_manager.get_messages(self.active_conversation["id"])
        if not messages:
            self.chat_history.append("Welcome to Jarvis.\nYour personal desktop AI assistant is ready.")
            return

        for message in messages:
            role = message["role"].title()
            self.chat_history.append(f"{role}: {message['content']}")

    def send_message(self) -> None:
        text = self.prompt_input.text().strip()
        if not text:
            return

        if not self.runtime.is_available():
            QMessageBox.warning(
                self,
                "OpenCode runtime unavailable",
                "The configured OpenCode runtime is not available. Set JARVIS_OPENAI_BASE_URL and any required credentials, then retry.",
            )
            return

        self.current_task = self.task_manager.create_task(f"Chat: {text[:32]}", project_path=self.config.data_dir, selected_model=self.model_selector.currentText())
        self.task_manager.start(self.current_task.id)
        self.status_label.setText("Running")

        self.session_manager.save_message(self.active_conversation["id"], "user", text)
        response = self.runtime.respond(text, self.model_selector.currentText())
        self.session_manager.save_message(self.active_conversation["id"], "assistant", response)
        self.task_manager.mark_completed(self.current_task.id)
        self.status_label.setText("Ready")
        self.prompt_input.clear()
        self._refresh_history()
        self._populate_conversation_list()

    def stop_current_task(self) -> None:
        self.current_task.request_stop()
        self.status_label.setText("Stopped")
        self.task_manager.emergency_stop.stop()

    def show_settings(self) -> None:
        window = SettingsWindow(self.config)
        window.exec()

    def show_memory(self) -> None:
        window = MemoryView(self.memory_manager)
        window.exec()

    def show_search(self) -> None:
        query = self.prompt_input.text().strip() or "Jarvis desktop app"
        results = self.search_manager.search(query)
        if not results:
            QMessageBox.information(self, "Search", "No local results found for this query.")
            return
        preview = results[0]["snippet"]
        QMessageBox.information(self, "Search", f"Top result: {results[0]['title']}\n\n{preview}")

    def show_voice_status(self) -> None:
        status = "Voice input is available as a local interface stub."
        if self.voice_manager.speech_to_text_available() or self.voice_manager.text_to_speech_available():
            status = "Voice interfaces are enabled for local speech support."
        QMessageBox.information(self, "Voice", status)

    def apply_theme(self, theme: str) -> None:
        self.config.theme = theme
        if theme == "dark":
            self.setStyleSheet(
                """
                QMainWindow { background: #121a22; color: #eaf2ff; }
                QWidget { background: #121a22; color: #eaf2ff; }
                #sidebar { background: #1a2430; border: 1px solid #243244; }
                #content { background: #121a22; }
                #composer { background: #182330; border: 1px solid #243244; border-radius: 12px; }
                QPushButton, QLineEdit, QComboBox, QListWidget, QTextBrowser { background: #1f2d3d; color: #eaf2ff; border: 1px solid #2d4055; border-radius: 8px; padding: 8px; }
                QLabel { color: #eaf2ff; }
                #jarvisTitle { font-size: 20px; font-weight: 700; }
                #headerLabel { font-size: 16px; font-weight: 600; }
                #chatHistory { background: #0d1621; border: 1px solid #243244; border-radius: 12px; padding: 12px; }
                #newChat { background: #263d59; }
                #settingsButton { background: #263d59; }
                """
            )
        else:
            self.setStyleSheet(
                """
                QMainWindow { background: #f3f6fb; color: #17212b; }
                QWidget { background: #f3f6fb; color: #17212b; }
                #sidebar { background: #edf2f8; border: 1px solid #dfe7f5; }
                #content { background: #f3f6fb; }
                #composer { background: #ffffff; border: 1px solid #dde6f1; border-radius: 12px; }
                QPushButton, QLineEdit, QComboBox, QListWidget, QTextBrowser { background: #ffffff; color: #17212b; border: 1px solid #d9e1ee; border-radius: 8px; padding: 8px; }
                QLabel { color: #17212b; }
                #jarvisTitle { font-size: 20px; font-weight: 700; }
                #headerLabel { font-size: 16px; font-weight: 600; }
                #chatHistory { background: #ffffff; border: 1px solid #dde6f1; border-radius: 12px; padding: 12px; }
                #newChat { background: #e2ebff; }
                #settingsButton { background: #e2ebff; }
                """
            )
