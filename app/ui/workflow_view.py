from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout,
)

from app.workflows.workflow_manager import WorkflowManager


class WorkflowView(QDialog):
    def __init__(self, manager: WorkflowManager, run_callback) -> None:
        super().__init__()
        self.manager = manager
        self.run_callback = run_callback
        self.setWindowTitle("Jarvis Workflows")
        self.resize(680, 480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Saved workflows are visible and run only when you request them. Risky steps ask for approval."))
        self.workflows = QListWidget()
        self.workflows.currentItemChanged.connect(self._show_details)
        layout.addWidget(self.workflows, 1)
        self.details = QLabel("")
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        run = QPushButton("Run selected")
        run.clicked.connect(self.run_selected)
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self.delete_selected)
        buttons.addWidget(refresh)
        buttons.addStretch()
        buttons.addWidget(run)
        buttons.addWidget(delete)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self) -> None:
        self.workflows.clear()
        for workflow in self.manager.list_workflows():
            item = QListWidgetItem(workflow["name"])
            item.setData(256, workflow)
            self.workflows.addItem(item)
        self.details.setText(f"{self.workflows.count()} saved workflows")

    def _show_details(self, current, _previous=None) -> None:
        workflow = current.data(256) if current else None
        if not workflow:
            return
        summary = []
        for index, step in enumerate(workflow["steps"], 1):
            if isinstance(step, dict):
                summary.append(f"{index}. {step.get('tool')} — {json.dumps(step.get('arguments', {}), ensure_ascii=False)}")
            else:
                summary.append(f"{index}. {step}")
        self.details.setText("\n".join(summary))

    def run_selected(self) -> None:
        item = self.workflows.currentItem()
        if not item:
            return
        workflow = item.data(256)
        result = self.run_callback(workflow["id"])
        if result.get("started"):
            QMessageBox.information(self, "Workflow started", f"Started workflow: {workflow['name']}\nApproval prompts will appear for risky steps.")
        elif result.get("success"):
            QMessageBox.information(self, "Workflow complete", f"Completed workflow: {workflow['name']}")
        else:
            QMessageBox.warning(self, "Workflow stopped", result.get("error", "Workflow did not complete."))
        self.refresh()

    def delete_selected(self) -> None:
        item = self.workflows.currentItem()
        if not item:
            return
        workflow = item.data(256)
        answer = QMessageBox.question(self, "Delete workflow", f"Delete saved workflow '{workflow['name']}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.manager.delete_workflow(workflow["id"])
            self.refresh()
