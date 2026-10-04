from app.export_import.import_export import ExportImportManager
from app.workflows.workflow_manager import WorkflowManager
from app.permissions.policy import PermissionPolicy
from app.tooling import ToolDefinition, ToolRegistry
from app.agent import AgentLoop


def test_workflow_manager_round_trip(tmp_path):
    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    workflow = manager.save_workflow("Prepare project", ["open_app", "read_files"])
    assert workflow["name"] == "Prepare project"
    assert manager.list_workflows()[0]["name"] == "Prepare project"


def test_repeated_approved_sequences_suggest_and_save_structured_workflow(tmp_path):
    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    sequence = [
        {"name": "open_application", "arguments": {"path": "notepad.exe"}, "result": {"success": True}},
        {"name": "open_browser", "arguments": {"url": "https://example.com"}, "result": {"success": True}},
    ]
    assert manager.record_observation(sequence)
    assert manager.workflow_suggestions() == []
    assert manager.record_observation(sequence)
    suggestion = manager.workflow_suggestions()[0]
    assert suggestion["occurrences"] == 2
    assert suggestion["steps"] == [
        {"tool": "open_application", "arguments": {"path": "notepad.exe"}},
        {"tool": "open_browser", "arguments": {"url": "https://example.com"}},
    ]
    manager.save_workflow("Start work", suggestion["steps"])
    assert manager.workflow_suggestions() == []


def test_workflow_observer_excludes_failed_and_sensitive_actions(tmp_path):
    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    assert not manager.record_observation([
        {"name": "run_powershell", "arguments": {"command": "secret"}, "result": {"success": True}},
        {"name": "open_application", "arguments": {"path": "x"}, "result": {"success": False}},
    ])
    assert manager.workflow_suggestions() == []


def test_workflow_run_requires_start_and_step_approvals(tmp_path):
    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    workflow = manager.save_workflow("Open site", [{"tool": "open_browser", "arguments": {"url": "https://example.com"}}])
    registry = ToolRegistry(workflow_manager=manager)
    calls = []
    registry.register(ToolDefinition("open_browser", "Open URL", "moderate", {"url": "URL"}, lambda url: calls.append(url) or {"success": True, "url": url}))

    class Model:
        def decide(self, _request, *, context=None):
            if not context["agent_messages"]:
                return {"tool": "run_workflow", "arguments": {"workflow_id": workflow["id"]}}
            return {"final_response": "Workflow finished."}

    confirmations = []
    def approve(tool, arguments, level):
        confirmations.append((tool, level))
        return True

    result = AgentLoop(registry=registry, model_adapter=Model(), workflow_manager=manager).process_request("Open my saved workflow", confirm_tool=approve)
    assert result["success"] is True
    assert calls == ["https://example.com"]
    assert confirmations == [("run_workflow", "dangerous"), ("open_browser", "moderate")]


def test_workflow_run_denial_stops_without_executing(tmp_path):
    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    workflow = manager.save_workflow("Open site", [{"tool": "open_browser", "arguments": {"url": "https://example.com"}}])
    registry = ToolRegistry(workflow_manager=manager)
    calls = []
    registry.register(ToolDefinition("open_browser", "Open URL", "moderate", {"url": "URL"}, lambda url: calls.append(url) or {"success": True}))

    result = manager.execute_workflow(workflow["id"], registry=registry, permission_policy=PermissionPolicy(), confirm_step=lambda *_args: False)
    assert result["success"] is False
    assert result["cancelled"] is True
    assert calls == []


def test_workflow_stop_prevents_following_steps(tmp_path):
    from threading import Event

    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    workflow = manager.save_workflow("Open two sites", [
        {"tool": "open_browser", "arguments": {"url": "https://first.example"}},
        {"tool": "open_browser", "arguments": {"url": "https://second.example"}},
    ])
    registry = ToolRegistry(workflow_manager=manager)
    calls = []
    stopped = Event()

    def open_site(url):
        calls.append(url)
        stopped.set()
        return {"success": True}

    registry.register(ToolDefinition("open_browser", "Open URL", "moderate", {"url": "URL"}, open_site))
    result = manager.execute_workflow(
        workflow["id"], registry=registry, permission_policy=PermissionPolicy(),
        confirm_step=lambda *_args: True, should_cancel=stopped.is_set,
    )
    assert result["success"] is False and result["cancelled"] is True
    assert calls == ["https://first.example"]


def test_export_import_manager(tmp_path):
    manager = ExportImportManager(root=str(tmp_path))
    bundle = manager.export_data({"profile": "A", "preferences": ["dark mode"]})
    assert "profile" in bundle
    restored = manager.import_data(bundle)
    assert restored["preferences"] == ["dark mode"]
    assert not (tmp_path / "jarvis_memory_package.json").exists()


def test_encrypted_backup_exports_portable_data_and_excludes_credentials(tmp_path):
    import sqlite3
    from app.config import AppConfig
    from app.db import DatabaseManager
    from app.core.session_manager import SessionManager
    from app.memory.memory_manager import MemoryManager

    source_config = AppConfig(data_dir=str(tmp_path / "source"))
    DatabaseManager(source_config).set_setting("theme", "dark")
    DatabaseManager(source_config).set_setting("default_model", "test-model")
    DatabaseManager(source_config).set_setting("openai_base_url", "https://private:secret@example.com")
    DatabaseManager(source_config).set_setting("OPENCODE_API_KEY", "sk-example-secret-value")
    sessions = SessionManager(source_config)
    conversation = sessions.create_conversation("Science project", project_path="C:/OldPC/Science")
    sessions.save_message(conversation["id"], "user", 'Use this api_key="do-not-export" for testing')
    memory = MemoryManager(str(source_config.database_path))
    memory.add_memory("preference", "Prefers science explanations")
    workflow_manager = WorkflowManager(str(source_config.database_path))
    workflow_manager.save_workflow("Open science", [{"tool": "open_application", "arguments": {"path": "notepad.exe"}}])
    connection = sqlite3.connect(source_config.database_path)
    connection.execute("CREATE TABLE credentials (key TEXT, value TEXT)")
    connection.execute("INSERT INTO credentials VALUES ('API', 'separate-secret')")
    connection.commit()
    connection.close()

    manager = ExportImportManager(database_path=str(source_config.database_path), root=str(tmp_path / "exports"))
    payload = manager.build_backup()
    assert payload["data"]["settings"] == {"theme": "dark", "default_model": "test-model"}
    assert payload["redacted_secret_count"] == 1
    assert 'api_key="[REDACTED]"' in payload["data"]["messages"][0]["content"]
    assert payload["data"]["conversations"][0]["project_path"] == "C:/OldPC/Science"

    path = tmp_path / "portable.jarvisbackup"
    manager.write_backup(path, "a strong portable passphrase")
    ciphertext = path.read_bytes()
    assert b"Science project" not in ciphertext
    assert b"separate-secret" not in ciphertext
    assert manager.read_backup(path, "a strong portable passphrase")["data"]["workflows"]


def test_encrypted_backup_merge_is_idempotent_and_replace_preserves_credentials(tmp_path):
    import sqlite3
    from app.config import AppConfig
    from app.db import DatabaseManager
    from app.core.session_manager import SessionManager
    from app.memory.memory_manager import MemoryManager

    source = AppConfig(data_dir=str(tmp_path / "source"))
    sessions = SessionManager(source)
    conversation = sessions.create_conversation("Migration test")
    sessions.save_message(conversation["id"], "user", "hello")
    MemoryManager(str(source.database_path)).add_memory("profile", "Enjoys astronomy")
    WorkflowManager(str(source.database_path)).save_workflow("Study", ["open_application"])
    source_manager = ExportImportManager(database_path=str(source.database_path))
    backup = tmp_path / "migration.jarvisbackup"
    source_manager.write_backup(backup, "another strong passphrase")
    payload = source_manager.read_backup(backup, "another strong passphrase")

    target = AppConfig(data_dir=str(tmp_path / "target"))
    db = DatabaseManager(target)
    db.set_setting("OPENCODE_API_KEY", "preserve-this-secret")
    target_manager = ExportImportManager(database_path=str(target.database_path))
    first = target_manager.restore_payload(payload, strategy="merge")
    second = target_manager.restore_payload(payload, strategy="merge")
    assert first["conversations"] == 1 and first["messages"] == 1
    assert second == {"settings": 0, "conversations": 0, "messages": 0, "memories": 0, "workflows": 0}

    target_manager.restore_payload(payload, strategy="replace")
    connection = sqlite3.connect(target.database_path)
    try:
        assert connection.execute("SELECT value FROM settings WHERE key='OPENCODE_API_KEY'").fetchone()[0] == "preserve-this-secret"
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1
    finally:
        connection.close()


def test_encrypted_backup_rejects_wrong_passphrase_tampering_and_secret_settings(tmp_path):
    from app.config import AppConfig
    from app.db import DatabaseManager

    config = AppConfig(data_dir=str(tmp_path / "jarvis"))
    DatabaseManager(config).set_setting("theme", "dark")
    manager = ExportImportManager(database_path=str(config.database_path))
    backup = tmp_path / "backup.jarvisbackup"
    manager.write_backup(backup, "passphrase with enough length")
    try:
        manager.read_backup(backup, "wrong passphrase here")
    except ValueError as exc:
        assert "passphrase" in str(exc).lower()
    else:
        raise AssertionError("Wrong passphrases must not unlock the backup.")

    tampered = bytearray(backup.read_bytes())
    tampered[-1] ^= 1
    backup.write_bytes(tampered)
    try:
        manager.read_backup(backup, "passphrase with enough length")
    except ValueError:
        pass
    else:
        raise AssertionError("Modified encrypted backups must be rejected.")

    payload = manager.build_backup()
    payload["data"]["settings"]["api_key"] = "must-not-import"
    try:
        manager.restore_payload(payload)
    except ValueError as exc:
        assert "secret settings" in str(exc)
    else:
        raise AssertionError("Secret settings must not be imported.")


def test_backup_redacts_quoted_secrets_and_rejects_unreviewed_fields(tmp_path):
    manager = ExportImportManager(root=str(tmp_path))
    text = 'password="multiple words here" token: abc123 https://alice:private-pass@example.com'
    redacted, count = manager._redact_text(text)
    assert 'password="[REDACTED]"' in redacted
    assert 'token: "[REDACTED]"' in redacted
    assert "alice:private-pass" not in redacted
    assert count == 3

    config_data = {
        "settings": {}, "conversations": [], "messages": [], "memories": [], "workflows": [],
        "credentials": {"api_key": "must-not-be-exported"},
    }
    payload = {
        "format": manager.FORMAT, "version": manager.VERSION,
        "created_at": "2026-10-04T00:00:00+00:00", "data": config_data,
    }
    try:
        manager.write_payload_backup(tmp_path / "invalid.jarvisbackup", "long enough passphrase", payload)
    except ValueError as exc:
        assert "sections" in str(exc).lower()
    else:
        raise AssertionError("Unreviewed backup sections must not be exported.")
