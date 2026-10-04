from app.export_import.import_export import ExportImportManager
from app.workflows.workflow_manager import WorkflowManager


def test_workflow_manager_round_trip(tmp_path):
    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    workflow = manager.save_workflow("Prepare project", ["open_app", "read_files"])
    assert workflow["name"] == "Prepare project"
    assert manager.list_workflows()[0]["name"] == "Prepare project"


def test_export_import_manager(tmp_path):
    manager = ExportImportManager(root=str(tmp_path))
    bundle = manager.export_data({"profile": "A", "preferences": ["dark mode"]})
    assert "profile" in bundle
    restored = manager.import_data(bundle)
    assert restored["preferences"] == ["dark mode"]
