from app.memory.memory_manager import MemoryManager
from app.memory.memory_manager import MemoryCandidateExtractor


def test_memory_manager_round_trip(tmp_path):
    manager = MemoryManager(database_path=str(tmp_path / "memory.db"))
    manager.add_memory("Profile", "User prefers concise technical answers.")
    manager.add_memory("Preferences", "Theme: dark mode.")

    memories = manager.search("concise")
    assert len(memories) == 1
    assert memories[0]["category"] == "profile"

    manager.delete_memory(memories[0]["id"])
    assert manager.search("concise") == []


def test_memory_schema_migrates_legacy_rows_with_metadata(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE memory (id TEXT PRIMARY KEY, category TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, source TEXT)")
    connection.execute("INSERT INTO memory VALUES ('old', 'Profile', 'Likes hiking', 'then', 'then', NULL)")
    connection.commit()
    connection.close()

    manager = MemoryManager(str(path))
    item = manager.list_memories()[0]
    assert item["importance"] == 0.5
    assert item["confidence"] == 0.8


def test_memory_deduplicates_retrieves_and_updates(tmp_path):
    manager = MemoryManager(str(tmp_path / "memory.db"))
    original = manager.add_memory("preference", "Prefers concise technical answers", importance=0.6)
    duplicate = manager.add_memory("preference", "Prefers concise technical answers", importance=0.9)
    manager.add_memory("work", "Works on the Jarvis desktop assistant", importance=0.8)

    assert original["id"] == duplicate["id"]
    assert len(manager.list_memories()) == 2
    assert manager.search("concise")[0]["importance"] == 0.9
    assert manager.retrieve_relevant("Please explain the Jarvis assistant")
    updated = manager.update_memory(original["id"], "instruction", "Keep answers concise", importance=0.7)
    assert updated["category"] == "instruction"
    assert updated["content"] == "Keep answers concise"


def test_memory_near_duplicate_updates_existing_record(tmp_path):
    manager = MemoryManager(str(tmp_path / "memory.db"))
    first = manager.add_memory("preference", "I prefer concise, detailed technical explanations", importance=0.5)
    second = manager.add_memory("preference", "I prefer concise detailed technical explanations.", importance=0.9)
    assert first["id"] == second["id"]
    assert len(manager.list_memories()) == 1
    assert second["importance"] == 0.9


def test_memory_requires_explicit_approval_and_rejects_secrets(tmp_path):
    manager = MemoryManager(str(tmp_path / "memory.db"))
    extractor = MemoryCandidateExtractor()

    candidate = extractor.extract("I prefer concise explanations.")
    assert candidate and candidate["category"] == "preference"
    assert manager.list_memories() == []
    assert extractor.extract("Remember my API key is sk-abcdefghijklmno") is None
    try:
        manager.add_memory("profile", "My password is hunter2")
    except ValueError as exc:
        assert "secret" in str(exc)
    else:
        raise AssertionError("Secrets must not be persisted as ordinary memory.")


def test_candidate_classifier_covers_memory_categories_and_multiple_candidates():
    extractor = MemoryCandidateExtractor()
    candidates = extractor.extract_many(
        "I prefer concise answers. I work as a science teacher. "
        "I'm working on the Jarvis assistant. I usually plan lessons on Sunday. "
        "My workflow is to review notes before class. From now on, use metric units."
    )
    assert [item["category"] for item in candidates] == ["preference", "work", "project", "habit", "workflow", "instruction"]
    assert all(0 <= item["confidence"] <= 1 and 0 <= item["importance"] <= 1 for item in candidates)


def test_explicit_remember_classifies_content_and_never_stores_it_automatically(tmp_path):
    manager = MemoryManager(str(tmp_path / "memory.db"))
    candidate = MemoryCandidateExtractor().extract("Remember that I prefer short explanations.")
    assert candidate["category"] == "preference"
    assert candidate["confidence"] > 0.8
    assert manager.list_memories() == []
