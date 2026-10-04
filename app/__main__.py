from __future__ import annotations

import os
import sys
import logging

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import AppConfig
from app.db import DatabaseManager
from app.ui.main_window import MainWindow
from app.logging_setup import configure_logging, install_exception_logging


def main() -> int:
    if os.name == "nt":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QApplication(sys.argv)
    app.setApplicationName("Jarvis")

    config = AppConfig()
    log_path = configure_logging(config.data_dir_path / "logs")
    install_exception_logging(
        log_path,
        notify=lambda message: QMessageBox.critical(None, "Jarvis error", message),
    )
    logging.getLogger("jarvis").info("Jarvis starting")
    DatabaseManager(config)
    window = MainWindow(config)
    window.show()
    exit_code = app.exec()
    logging.getLogger("jarvis").info("Jarvis stopped with exit code %s", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
