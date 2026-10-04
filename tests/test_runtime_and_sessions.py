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
