from app.search.search_manager import SearchManager
from app.voice.voice_manager import VoiceManager
from app.core.session_manager import SessionManager
from app.config import AppConfig
from app.memory.memory_manager import MemoryManager
from app.tooling import ToolRegistry
from app.permissions.policy import PermissionPolicy
from app.agent import AgentLoop


def test_search_manager_returns_relevant_results():
    manager = SearchManager()
    results = manager.search("Jarvis desktop app")
    assert isinstance(results, list)
    assert len(results) >= 1


def test_voice_manager_has_interfaces():
    manager = VoiceManager()
    assert manager.speech_to_text_available() in {True, False}
    assert manager.text_to_speech_available() in {True, False}


def test_search_covers_files_memory_and_conversation_sources(tmp_path):
    config = AppConfig(data_dir=str(tmp_path / "jarvis"))
    sessions = SessionManager(config)
    conversation = sessions.create_conversation("Physics revision")
    sessions.save_message(conversation["id"], "user", "Review quantum mechanics before the exam")
    memories = MemoryManager(str(config.database_path))
    memories.add_memory("preference", "Prefers quantum mechanics explanations with diagrams")
    project = tmp_path / "project"
    project.mkdir()
    (project / "notes.md").write_text("Quantum mechanics revision notes", encoding="utf-8")

    manager = SearchManager(config.database_path)
    results = manager.search("quantum mechanics", sources={"files", "memory", "conversations"}, project_path=project)
    assert {result["source"] for result in results} == {"Project file", "Memory", "Conversation"}
    (project / "quickstart-guide.txt").write_text("Nothing about the query is in this body", encoding="utf-8")
    filename_results = manager.search("quickstart", sources={"files"}, project_path=project)
    assert any(result["title"].endswith("quickstart-guide.txt") for result in filename_results)


def test_search_web_provider_is_pluggable_and_results_are_labeled():
    calls = []
    manager = SearchManager(web_provider=lambda query, limit: calls.append((query, limit)) or [
        {"title": "Python docs", "body": "Python documentation", "href": "https://docs.python.org/"},
    ])
    results = manager.search("Python docs", sources={"web"}, limit=5)
    assert calls == [("Python docs", 5)]
    assert results[0]["source"] == "Web search"
    assert results[0]["url"] == "https://docs.python.org/"


def test_voice_manager_transcribes_with_injected_microphone_and_speech_api():
    class Microphone:
        def __enter__(self):
            return "microphone"

        def __exit__(self, *_args):
            return False

    class Recognizer:
        def adjust_for_ambient_noise(self, source, duration):
            assert source == "microphone" and duration == 0.4

        def listen(self, source, timeout, phrase_time_limit):
            assert timeout == 6 and phrase_time_limit == 20
            return "audio"

        def recognize_google(self, audio, language):
            assert audio == "audio" and language == "en-US"
            return "Open my project folder"

    manager = VoiceManager(recognizer_factory=Recognizer, microphone_factory=Microphone, speech_module=object())
    assert manager.speech_to_text_available()
    assert manager.listen_and_transcribe() == "Open my project folder"


def test_voice_manager_uses_injected_local_text_to_speech():
    events = []

    class Engine:
        def say(self, text):
            events.append(("say", text))

        def runAndWait(self):
            events.append(("run",))

        def stop(self):
            events.append(("stop",))

    manager = VoiceManager(tts_factory=Engine)
    assert manager.text_to_speech_available()
    manager.speak("Hello from Jarvis")
    assert events == [("say", "Hello from Jarvis"), ("run",), ("stop",)]


def test_agent_web_search_requires_permission_and_returns_labeled_results(tmp_path):
    calls = []
    search = SearchManager(str(tmp_path / "jarvis.db"), web_provider=lambda query, _limit: calls.append(query) or [
        {"title": "Result", "body": "Example", "href": "https://example.com"},
    ])
    registry = ToolRegistry(search_manager=search)

    class Model:
        def __init__(self):
            self.turn = 0

        def decide(self, _request, *, context=None):
            self.turn += 1
            if self.turn == 1:
                return {"tool": "search_web", "arguments": {"query": "Jarvis search"}}
            if '"source": "Web search"' not in context["agent_messages"][-1]["content"]:
                return {"final_response": "Search was denied."}
            return {"final_response": "Found a web result."}

    denied = AgentLoop(registry=registry, model_adapter=Model()).process_request("Search web")
    assert denied["tool_calls"][0]["result"]["requires_confirmation"] is True
    assert calls == []

    approved_model = Model()
    approved = AgentLoop(registry=registry, model_adapter=approved_model).process_request(
        "Search web", confirm_tool=lambda *_args: True,
    )
    assert approved["success"] is True
    assert calls == ["Jarvis search"]


def test_search_view_exposes_scoped_sources_and_query(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.ui.search_view import SearchView

    application = QApplication.instance() or QApplication([])
    view = SearchView(SearchManager(str(tmp_path / "jarvis.db")), initial_query="Find my project notes")
    assert view.query.text() == "Find my project notes"
    assert view.source_boxes["conversations"].isChecked()
    assert view.source_boxes["memory"].isChecked()
    assert not view.source_boxes["web"].isChecked()
    assert not view.source_boxes["files"].isChecked()
    view.close()
    application.processEvents()
