from app.core.session_manager import SessionManager
from app.opencode.client import OpenCodeClient


def test_session_manager_round_trip(tmp_path):
    manager = SessionManager(database_path=str(tmp_path / "jarvis.db"))
    conversation = manager.create_conversation("Welcome")
    manager.save_message(conversation["id"], "user", "Hello")
    manager.save_message(conversation["id"], "assistant", "Hi there")

    history = manager.get_messages(conversation["id"])
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_opencode_client_returns_reply():
    client = OpenCodeClient()
    reply = client.respond("Hello Jarvis", model_name="OpenCode Zen")
    assert "Jarvis" in reply or "hello" in reply.lower()


def test_session_manager_rename_conversation(tmp_path):
    manager = SessionManager(database_path=str(tmp_path / "jarvis.db"))
    conversation = manager.create_conversation("Old title")
    renamed = manager.rename_conversation(conversation["id"], "  New title  ")
    assert renamed["title"] == "New title"
    listed = manager.list_conversations()
    assert listed[0]["id"] == conversation["id"]
    assert listed[0]["title"] == "New title"


def test_session_manager_rename_rejects_blank_title(tmp_path):
    import pytest
    manager = SessionManager(database_path=str(tmp_path / "jarvis.db"))
    conversation = manager.create_conversation("A chat")
    with pytest.raises(ValueError):
        manager.rename_conversation(conversation["id"], "   ")


def test_session_manager_delete_conversation_removes_messages(tmp_path):
    manager = SessionManager(database_path=str(tmp_path / "jarvis.db"))
    keep = manager.create_conversation("Keep me")
    drop = manager.create_conversation("Delete me")
    manager.save_message(keep["id"], "user", "Keep this")
    manager.save_message(drop["id"], "user", "Remove this")
    assert manager.delete_conversation(drop["id"]) is True
    assert [c["id"] for c in manager.list_conversations()] == [keep["id"]]
    assert manager.get_messages(drop["id"]) == []
    assert manager.get_messages(keep["id"])[0]["content"] == "Keep this"


def test_session_manager_delete_unknown_conversation_returns_false(tmp_path):
    manager = SessionManager(database_path=str(tmp_path / "jarvis.db"))
    assert manager.delete_conversation("missing-id") is False
