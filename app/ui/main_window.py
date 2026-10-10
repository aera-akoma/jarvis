from __future__ import annotations

from typing import Optional
import json
import threading
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QThread, Signal
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
    QInputDialog,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig
from app.agent import AgentLoop, OpenAICompatibleModelAdapter
from app.computer.windows import WindowsController
from app.core.settings_manager import SettingsManager
from app.core.session_manager import SessionManager
from app.memory.memory_manager import MemoryManager
from app.memory.memory_manager import MemoryCandidateExtractor
from app.opencode.client import OpenCodeClient
from app.search.search_manager import SearchManager
from app.tasks import TaskManager
from app.tooling import ToolRegistry
from app.ui.memory_view import MemoryView
from app.ui.settings_window import SettingsWindow
from app.voice.voice_manager import VoiceManager
from app.workflows.workflow_manager import WorkflowManager
from app.ui.workflow_view import WorkflowView
from app.ui.search_view import SearchView
from app.permissions.policy import PermissionPolicy


class AgentWorker(QThread):
    result_ready = Signal(object)
    confirmation_requested = Signal(object)

    def __init__(self, agent: AgentLoop, request: str, project_path: str, conversation: list[dict], memory: list[dict]) -> None:
        super().__init__()
        self.agent = agent
        self.request = request
        self.project_path = project_path
        self.conversation = conversation
        self.memory = memory

    def _confirm(self, tool: str, arguments: dict, level: str) -> bool:
        response = {"tool": tool, "arguments": arguments, "level": level, "event": threading.Event(), "approved": False}
        self.confirmation_requested.emit(response)
        response["event"].wait()
        return bool(response["approved"])

    def run(self) -> None:
        try:
            result = self.agent.process_request(self.request, project_path=self.project_path,
                                                conversation=self.conversation, memory=self.memory, confirm_tool=self._confirm)
        except Exception as exc:
            result = {"success": False, "cancelled": self.agent.cancelled,
                      "summary": f"Agent request failed: {exc}", "tool_calls": []}
        self.result_ready.emit(result)


class WorkflowWorker(QThread):
    result_ready = Signal(object)
    confirmation_requested = Signal(object)

    def __init__(self, manager: WorkflowManager, workflow_id: str, registry: ToolRegistry, policy: PermissionPolicy) -> None:
        super().__init__()
        self.manager, self.workflow_id, self.registry, self.policy = manager, workflow_id, registry, policy
        self._cancel_requested = threading.Event()

    def cancel(self) -> None:
        self._cancel_requested.set()

    def _confirm(self, tool: str, arguments: dict, level: str) -> bool:
        response = {"tool": tool, "arguments": arguments, "level": level, "event": threading.Event(), "approved": False}
        self.confirmation_requested.emit(response)
        response["event"].wait()
        return bool(response["approved"])

    def run(self) -> None:
        self.result_ready.emit(self.manager.execute_workflow(
            self.workflow_id, registry=self.registry, permission_policy=self.policy, confirm_step=self._confirm,
            should_cancel=self._cancel_requested.is_set,
        ))


class SpeechInputWorker(QThread):
    result_ready = Signal(object)

    def __init__(self, voice_manager: VoiceManager) -> None:
        super().__init__()
        self.voice_manager = voice_manager

    def run(self) -> None:
        try:
            self.result_ready.emit({"success": True, "transcript": self.voice_manager.listen_and_transcribe()})
        except Exception as exc:
            self.result_ready.emit({"success": False, "error": str(exc)})


class SpeechOutputWorker(QThread):
    result_ready = Signal(object)

    def __init__(self, voice_manager: VoiceManager, text: str) -> None:
        super().__init__()
        self.voice_manager, self.text = voice_manager, text

    def run(self) -> None:
        try:
            self.voice_manager.speak(self.text)
            self.result_ready.emit({"success": True})
        except Exception as exc:
            self.result_ready.emit({"success": False, "error": str(exc)})


class ModelListWorker(QThread):
    models_ready = Signal(int, object, str)

    def __init__(self, runtime, generation: int, parent=None) -> None:
        super().__init__(parent)
        self.runtime = runtime
        self.generation = generation

    def run(self) -> None:
        try:
            models = self.runtime.available_models()
            self.models_ready.emit(self.generation, models, self.runtime.last_error or "")
        except Exception:
            self.models_ready.emit(self.generation, [], "Model discovery failed unexpectedly. Check Jarvis logs and Settings.")


class MainWindow(QMainWindow):
    def __init__(self, config: Optional[AppConfig] = None) -> None:
        if QApplication.instance() is None:
            QApplication([])
        super().__init__()
        self.config = config or AppConfig()
        self.session_manager = SessionManager(self.config)
        self.settings_manager = SettingsManager(self.config)
        configured_model = self.settings_manager.get("default_model", self.config.default_model()) or self.config.default_model()
        if configured_model == "OpenCode Zen":
            configured_model = self.config.default_model()
            self.settings_manager.set("default_model", configured_model)
        self.default_model_name = configured_model
        self.memory_manager = MemoryManager(self.config.database_path)
        self.memory_candidate_extractor = MemoryCandidateExtractor()
        self.pending_memory_candidates: list[dict] = []
        self.workflow_manager = WorkflowManager(self.config.database_path)
        self.workflow_worker: WorkflowWorker | None = None
        self.search_manager = SearchManager(self.config.database_path)
        self.voice_manager = VoiceManager()
        configured_voice_output = self.settings_manager.get("voice_output", "false").lower() == "true"
        if configured_voice_output:
            self.voice_manager.enable_speech()
        self.voice_output_enabled = configured_voice_output and self.voice_manager.text_to_speech_available()
        self.speech_input_worker: SpeechInputWorker | None = None
        self.speech_output_worker: SpeechOutputWorker | None = None
        self.runtime = OpenCodeClient(base_url=self.settings_manager.get("openai_base_url"))
        self._model_workers: list[ModelListWorker] = []
        self._model_load_generation = 0
        self._models_loading = False
        self._model_connection_error = ""
        self.windows_controller = WindowsController()
        self.agent_loop: AgentLoop | None = None
        self.agent_worker: AgentWorker | None = None
        self.task_manager = TaskManager()
        self.current_task = self.task_manager.create_task("Current session", project_path=self.config.data_dir)
        conversations = self.session_manager.list_conversations()
        self.active_conversation = (
            conversations[0]
            if conversations
            else self.session_manager.create_conversation("New Chat", self.default_model_name)
        )
        self.setWindowTitle(self.config.app_name)
        self.resize(1200, 800)
        self._build_ui()
        self._refresh_history()
        self.apply_theme(self.config.theme)

    def _populate_model_selector(self) -> None:
        self._model_load_generation += 1
        generation = self._model_load_generation
        self._models_loading = True
        self._model_connection_error = ""
        self.model_selector.clear()
        self.model_selector.addItem("Loading models…")
        self.model_selector.setEnabled(False)
        self.status_label.setText("Checking model connection…")
        worker = ModelListWorker(self.runtime, generation, self)
        worker.models_ready.connect(self._on_models_loaded)
        worker.finished.connect(self._on_model_worker_finished)
        self._model_workers.append(worker)
        worker.start()

    def _on_model_worker_finished(self) -> None:
        worker = self.sender()
        if worker in self._model_workers:
            self._model_workers.remove(worker)
        worker.deleteLater()

    def _on_models_loaded(self, generation: int, models, error_message: str) -> None:
        if generation != self._model_load_generation:
            return
        self._models_loading = False
        self._model_connection_error = error_message
        self.model_selector.clear()
        if not models:
            if "HTTP 403" in error_message:
                failure_label = "Access denied (HTTP 403)"
            elif "HTTP 401" in error_message:
                failure_label = "Authentication failed (HTTP 401)"
            else:
                failure_label = "Model connection unavailable"
            self.model_selector.addItem(failure_label)
            self.model_selector.setEnabled(False)
            self.model_selector.setToolTip(error_message)
            self.status_label.setText(failure_label)
            return

        self.model_selector.addItems(models)
        self.model_selector.setEnabled(True)
        self.model_selector.setToolTip("")
        self.status_label.setText("Ready")
        if self.default_model_name in models:
            self.model_selector.setCurrentText(self.default_model_name)
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

        workflows_button = QPushButton("↻ Workflows")
        workflows_button.clicked.connect(self.show_workflows)
        sidebar_layout.addWidget(workflows_button)

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
        self.voice_output_button = QPushButton("🔊 Voice: On" if self.voice_output_enabled else "🔊 Voice: Off")
        self.voice_output_button.clicked.connect(self.toggle_voice_output)
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
        composer_layout.addWidget(self.voice_output_button)
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
        if self.agent_worker is not None and self.agent_worker.isRunning():
            return
        self.active_conversation = self.session_manager.create_conversation("New Chat", self.model_selector.currentText() if hasattr(self, "model_selector") else self.default_model_name)
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

        if self.agent_worker is not None and self.agent_worker.isRunning():
            return
        if self._models_loading:
            QMessageBox.warning(
                self,
                "Checking model connection",
                "Jarvis is still checking the provider. Wait for the model selector to finish loading, then retry.",
            )
            return
        if not self.model_selector.isEnabled():
            detail = self._model_connection_error or "No compatible model was returned by the configured provider."
            QMessageBox.warning(
                self,
                "Model connection unavailable",
                f"{detail}\n\nOpen Settings to check the API key and runtime URL, then save and retry.",
            )
            return
        model_name = self.model_selector.currentText()
        registry = ToolRegistry(desktop_controller=self.windows_controller, workflow_manager=self.workflow_manager, search_manager=self.search_manager)
        self.agent_loop = AgentLoop(registry=registry, model_adapter=OpenAICompatibleModelAdapter(registry, self.runtime, model_name), action_logger=self._log_action, workflow_manager=self.workflow_manager)
        self.current_task = self.task_manager.create_task(f"Chat: {text[:32]}", project_path=self.config.data_dir, selected_model=model_name)
        self.task_manager.start(self.current_task.id)
        self.status_label.setText("Running")

        self.session_manager.save_message(self.active_conversation["id"], "user", text)
        self.pending_memory_candidates = self.memory_candidate_extractor.extract_many(text)
        self.prompt_input.clear()
        history = self.session_manager.get_messages(self.active_conversation["id"])
        memory_query = " ".join([text, *(message.get("content", "") for message in history[-7:])])
        memories = self.memory_manager.retrieve_relevant(memory_query)
        self.agent_worker = AgentWorker(self.agent_loop, text, self.config.data_dir, history[:-1], memories)
        self.agent_worker.confirmation_requested.connect(self._confirm_tool_call)
        self.agent_worker.result_ready.connect(self._agent_finished)
        self.agent_worker.start()

    def _confirm_tool_call(self, request: dict) -> None:
        details = json.dumps(request["arguments"], ensure_ascii=False, indent=2)
        tool_definition = self.agent_loop.registry.get(request["tool"]) if self.agent_loop else None
        description = f"{tool_definition.description}\n\n" if tool_definition else ""
        answer = QMessageBox.question(self, "Jarvis permission", f"{description}Allow {request['level']} action: {request['tool']}?\n\n{details}", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        request["approved"] = answer == QMessageBox.StandardButton.Yes
        request["event"].set()

    def _agent_finished(self, result: dict) -> None:
        response = result.get("summary") or "Jarvis did not return a response."
        if result.get("cancelled"):
            self.task_manager.get_task(self.current_task.id).status = "cancelled"
        elif result.get("success"):
            self.task_manager.mark_completed(self.current_task.id)
        else:
            self.task_manager.mark_failed(self.current_task.id, response)
        self.session_manager.save_message(self.active_conversation["id"], "assistant", response)
        if result.get("success") and self.voice_output_enabled:
            self._speak_response(response)
        self.status_label.setText("Stopped" if result.get("cancelled") else "Ready")
        self._refresh_history()
        self._populate_conversation_list()
        if result.get("success") and self.workflow_manager.record_observation(result.get("tool_calls", [])):
            suggestion = next(iter(self.workflow_manager.workflow_suggestions()), None)
            if suggestion:
                answer = QMessageBox.question(
                    self, "Save a repeated workflow?",
                    f"Jarvis noticed this successful action sequence has occurred more than once:\n\n"
                    + "\n".join(f"{i}. {step['tool']} {json.dumps(step.get('arguments', {}), ensure_ascii=False)}" for i, step in enumerate(suggestion["steps"], 1))
                    + f"\n\nSave it as a workflow? ({suggestion['occurrences']} times observed)",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    name, accepted = QInputDialog.getText(self, "Name workflow", "Workflow name:", text=suggestion["suggested_name"])
                    if accepted and name.strip():
                        self.workflow_manager.save_workflow(name, suggestion["steps"])
        candidates = self.pending_memory_candidates
        self.pending_memory_candidates = []
        for candidate in candidates:
            answer = QMessageBox.question(
                self, "Save a Jarvis memory?",
                f"Would you like Jarvis to remember this?\n\n[{candidate['category']}] {candidate['content']}\n\nYou can review or delete it later in Memory.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                try:
                    self.memory_manager.add_memory(**candidate)
                except ValueError as exc:
                    QMessageBox.warning(self, "Memory not saved", str(exc))

    def stop_current_task(self) -> None:
        if self.agent_loop is not None:
            self.agent_loop.cancel()
        if self.workflow_worker is not None and self.workflow_worker.isRunning():
            self.workflow_worker.cancel()
        self.task_manager.request_stop(self.current_task.id)
        self.status_label.setText("Stopped")
        self.task_manager.emergency_stop.stop()

    def closeEvent(self, event) -> None:
        # Model discovery runs off the UI thread and has a bounded network timeout.
        # Wait briefly so closing during startup cannot destroy a running QThread.
        for worker in tuple(self._model_workers):
            if worker.isRunning():
                worker.requestInterruption()
                worker.wait(6500)
        super().closeEvent(event)

    def show_settings(self) -> None:
        window = SettingsWindow(self.config)
        window.data_restored.connect(self._data_restored)
        window.exec()
        self.default_model_name = self.settings_manager.get("default_model", self.config.default_model()) or self.config.default_model()
        self.runtime = OpenCodeClient(base_url=self.settings_manager.get("openai_base_url"))
        self._populate_model_selector()

    def _data_restored(self, result: dict) -> None:
        conversations = self.session_manager.list_conversations()
        if not any(item["id"] == self.active_conversation["id"] for item in conversations):
            self.active_conversation = self.session_manager.create_conversation("New Chat", self.default_model_name)
        self._populate_conversation_list()
        self._refresh_history()
        self.status_label.setText(f"Backup {result.get('strategy', 'restore')} complete")

    def show_memory(self) -> None:
        window = MemoryView(self.memory_manager)
        window.exec()

    def show_workflows(self) -> None:
        window = WorkflowView(self.workflow_manager, self.run_saved_workflow)
        window.exec()

    def _log_action(self, entry: dict) -> None:
        log_path = self.config.data_dir_path / "logs" / "action_log.jsonl"
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def run_saved_workflow(self, workflow_id: str) -> dict:
        workflow = self.workflow_manager.get_workflow(workflow_id)
        if workflow is None:
            return {"success": False, "error": "Saved workflow was not found."}
        if self.agent_worker is not None and self.agent_worker.isRunning():
            return {"success": False, "error": "Wait for the current Jarvis request to finish before running a workflow."}
        if self.workflow_worker is not None and self.workflow_worker.isRunning():
            return {"success": False, "error": "A workflow is already running."}
        replayable = {"open_application", "open_browser", "navigate_browser", "focus_window", "list_directory", "search_files", "create_directory"}
        if any(not isinstance(step, dict) or step.get("tool") not in replayable for step in workflow["steps"]):
            return {"success": False, "error": "This saved workflow contains legacy or unsupported steps. Remove it and save a new workflow from repeated actions."}
        plan = "\n".join(f"{i}. {step.get('tool')}: {json.dumps(step.get('arguments', {}), ensure_ascii=False)}" for i, step in enumerate(workflow["steps"], 1) if isinstance(step, dict))
        answer = QMessageBox.question(self, "Run workflow", f"Run '{workflow['name']}'? Risky steps will ask for separate approval.\n\n{plan}",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return {"success": False, "cancelled": True, "error": "Workflow run was cancelled."}
        registry = ToolRegistry(desktop_controller=self.windows_controller, workflow_manager=self.workflow_manager, search_manager=self.search_manager)
        self.workflow_worker = WorkflowWorker(self.workflow_manager, workflow_id, registry, PermissionPolicy())
        self.workflow_worker.confirmation_requested.connect(self._confirm_tool_call)
        self.workflow_worker.result_ready.connect(self._workflow_finished)
        self.workflow_worker.start()
        return {"success": True, "started": True}

    def _workflow_finished(self, result: dict) -> None:
        for step in result.get("steps", []):
            self._log_action({"workflow": result.get("workflow"), **step})
        if result.get("success"):
            QMessageBox.information(self, "Workflow complete", f"Completed workflow: {result.get('workflow', '')}")
        else:
            QMessageBox.warning(self, "Workflow stopped", result.get("error", "Workflow did not complete."))

    def show_search(self) -> None:
        window = SearchView(self.search_manager, initial_query=self.prompt_input.text().strip())
        window.exec()

    def show_voice_status(self) -> None:
        self.voice_manager.enable_speech()
        if not self.voice_manager.speech_to_text_available():
            QMessageBox.information(self, "Voice input unavailable", "Install the voice dependencies from requirements.txt and connect a microphone to enable speech input.")
            return
        if self.speech_input_worker is not None and self.speech_input_worker.isRunning():
            return
        answer = QMessageBox.question(
            self, "Allow one-time voice transcription?",
            "Jarvis will record one short microphone utterance and send the audio to Google's speech-recognition service for transcription. The transcript will appear in the input box for review; it will not be sent to Jarvis until you press Send. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.status_label.setText("Listening…")
        self.speech_input_worker = SpeechInputWorker(self.voice_manager)
        self.speech_input_worker.result_ready.connect(self._voice_transcribed)
        self.speech_input_worker.start()

    def _voice_transcribed(self, result: dict) -> None:
        self.status_label.setText("Ready")
        if result.get("success"):
            self.prompt_input.setText(result["transcript"])
            self.prompt_input.setFocus()
        else:
            QMessageBox.warning(self, "Voice transcription failed", result.get("error", "Unknown voice input error."))

    def toggle_voice_output(self) -> None:
        self.voice_manager.enable_speech()
        if not self.voice_manager.text_to_speech_available():
            QMessageBox.information(self, "Voice output unavailable", "Install pyttsx3 from requirements.txt to enable local Windows speech output.")
            return
        self.voice_output_enabled = not self.voice_output_enabled
        self.settings_manager.set("voice_output", "true" if self.voice_output_enabled else "false")
        self.voice_output_button.setText("🔊 Voice: On" if self.voice_output_enabled else "🔊 Voice: Off")

    def _speak_response(self, text: str) -> None:
        if self.speech_output_worker is not None and self.speech_output_worker.isRunning():
            return
        self.speech_output_worker = SpeechOutputWorker(self.voice_manager, text)
        self.speech_output_worker.result_ready.connect(self._voice_output_finished)
        self.speech_output_worker.start()

    def _voice_output_finished(self, result: dict) -> None:
        if not result.get("success"):
            self.status_label.setText("Voice output failed")
            QMessageBox.warning(self, "Voice output failed", result.get("error", "Unknown voice output error."))

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
