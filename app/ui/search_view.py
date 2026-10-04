from __future__ import annotations

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout,
)

from app.search.search_manager import SearchManager


class SearchWorker(QThread):
    finished_results = Signal(object)

    def __init__(self, manager: SearchManager, query: str, sources: set[str], project_path: str) -> None:
        super().__init__()
        self.manager, self.query, self.sources, self.project_path = manager, query, sources, project_path

    def run(self) -> None:
        try:
            result = self.manager.search(self.query, sources=self.sources, project_path=self.project_path or None)
        except Exception as exc:
            result = [{"source": "Search", "title": "Search failed", "snippet": str(exc), "error": True}]
        self.finished_results.emit(result)


class SearchView(QDialog):
    def __init__(self, manager: SearchManager, *, initial_query: str = "") -> None:
        super().__init__()
        self.manager = manager
        self.worker: SearchWorker | None = None
        self.setWindowTitle("Jarvis Search")
        self.resize(820, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Search local conversations, memory, Jarvis knowledge, project files, or the public web."))
        query_row = QHBoxLayout()
        self.query = QLineEdit(initial_query)
        self.query.setPlaceholderText("Search terms")
        self.query.returnPressed.connect(self.search)
        query_row.addWidget(self.query, 1)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search)
        query_row.addWidget(self.search_button)
        layout.addLayout(query_row)
        source_row = QHBoxLayout()
        self.source_boxes = {
            "knowledge": QCheckBox("Jarvis knowledge"),
            "files": QCheckBox("Project files"),
            "conversations": QCheckBox("Conversations"),
            "memory": QCheckBox("Memory"),
            "web": QCheckBox("Web"),
        }
        for source, checkbox in self.source_boxes.items():
            checkbox.setChecked(source not in {"web", "files"})
            source_row.addWidget(checkbox)
        layout.addLayout(source_row)
        path_row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Choose a folder to search in project files")
        self.folder.setReadOnly(True)
        path_row.addWidget(self.folder, 1)
        choose = QPushButton("Choose folder…")
        choose.clicked.connect(self.choose_folder)
        path_row.addWidget(choose)
        layout.addLayout(path_row)
        self.results = QListWidget()
        self.results.currentItemChanged.connect(self.show_result)
        layout.addWidget(self.results, 1)
        self.details = QTextBrowser()
        self.details.setMaximumHeight(160)
        layout.addWidget(self.details)
        footer = QHBoxLayout()
        self.status = QLabel("Ready")
        footer.addWidget(self.status, 1)
        self.open_button = QPushButton("Open web result")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_result)
        footer.addWidget(self.open_button)
        layout.addLayout(footer)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose project folder")
        if folder:
            self.folder.setText(folder)
            self.source_boxes["files"].setChecked(True)

    def search(self) -> None:
        query = self.query.text().strip()
        sources = {name for name, checkbox in self.source_boxes.items() if checkbox.isChecked()}
        if not query:
            self.status.setText("Enter a query first.")
            return
        if not sources:
            self.status.setText("Select at least one search source.")
            return
        if "files" in sources and not self.folder.text():
            answer = QMessageBox.question(self, "Choose a folder", "Project file search needs a folder you select. Choose one now?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.Yes)
            if answer == QMessageBox.StandardButton.Yes:
                self.choose_folder()
            if not self.folder.text():
                self.status.setText("Choose a folder or turn off Project files.")
                return
        if "web" in sources:
            answer = QMessageBox.question(
                self, "Search the public web?",
                "This query will be sent to an external metasearch provider. Do you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if self.worker and self.worker.isRunning():
            return
        self.search_button.setEnabled(False)
        self.status.setText("Searching…")
        self.worker = SearchWorker(self.manager, query, sources, self.folder.text())
        self.worker.finished_results.connect(self.show_results)
        self.worker.start()

    def show_results(self, results: list[dict]) -> None:
        self.results.clear()
        for result in results:
            item = QListWidgetItem(f"[{result.get('source', 'Result')}] {result.get('title', '')}")
            item.setData(256, result)
            self.results.addItem(item)
        self.search_button.setEnabled(True)
        errors = sum(bool(result.get("error")) for result in results)
        self.status.setText(f"{len(results) - errors} results" + (f" · {errors} source error(s)" if errors else ""))

    def show_result(self, current, _previous=None) -> None:
        result = current.data(256) if current else None
        if not result:
            self.details.clear()
            self.open_button.setEnabled(False)
            return
        url = result.get("url", "")
        self.details.setPlainText(result.get("snippet", "") + (f"\n\n{url}" if url else ""))
        self.open_button.setEnabled(url.startswith(("http://", "https://")))

    def open_result(self) -> None:
        item = self.results.currentItem()
        result = item.data(256) if item else {}
        url = result.get("url", "")
        if url.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(url))

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            self.status.setText("Wait for the current search to finish before closing.")
            event.ignore()
            return
        super().closeEvent(event)
