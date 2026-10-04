import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.config import AppConfig
from app.ui.main_window import MainWindow


def test_app_config_defaults():
    config = AppConfig()
    assert config.app_name == "Jarvis"
    assert config.theme in {"dark", "light"}


def test_main_window_exists():
    window = MainWindow()
    assert window.windowTitle() == "Jarvis"
