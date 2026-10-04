from app.search.search_manager import SearchManager
from app.voice.voice_manager import VoiceManager


def test_search_manager_returns_relevant_results():
    manager = SearchManager()
    results = manager.search("Jarvis desktop app")
    assert isinstance(results, list)
    assert len(results) >= 1


def test_voice_manager_has_interfaces():
    manager = VoiceManager()
    assert manager.speech_to_text_available() in {True, False}
    assert manager.text_to_speech_available() in {True, False}
