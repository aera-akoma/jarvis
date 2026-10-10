import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.config import AppConfig
from app.ui.main_window import MainWindow


def test_app_config_defaults():
    config = AppConfig()
    assert config.app_name == "Jarvis"
    assert config.theme in {"dark", "light"}


def test_main_window_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.OpenCodeClient.available_models", lambda _self: [])
    window = MainWindow(AppConfig(data_dir=str(tmp_path)))
    assert window.windowTitle() == "Jarvis"
    window.close()


def test_startup_reuses_latest_conversation_instead_of_creating_duplicate_chats(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr("app.ui.main_window.OpenCodeClient.available_models", lambda _self: [])
    application = QApplication.instance() or QApplication([])
    config = AppConfig(data_dir=str(tmp_path))

    first = MainWindow(config)
    first_id = first.active_conversation["id"]
    first.close()
    application.processEvents()

    second = MainWindow(config)
    assert second.active_conversation["id"] == first_id
    assert len(second.session_manager.list_conversations()) == 1
    second.close()
    application.processEvents()


def test_send_does_not_run_synchronous_availability_check(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    monkeypatch.setattr("app.ui.main_window.OpenCodeClient.available_models", lambda _self: [])
    application = QApplication.instance() or QApplication([])
    window = MainWindow(AppConfig(data_dir=str(tmp_path)))
    deadline = __import__("time").monotonic() + 3
    while window._models_loading and __import__("time").monotonic() < deadline:
        application.processEvents()
        __import__("time").sleep(0.01)

    window.runtime.is_available = lambda: (_ for _ in ()).throw(AssertionError("must not query provider on UI thread"))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(True))
    window.prompt_input.setText("hello")
    window.send_message()

    assert warnings == [True]
    window.close()
    application.processEvents()
