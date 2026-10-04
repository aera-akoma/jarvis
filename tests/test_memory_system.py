from app.memory.memory_manager import MemoryManager


def test_memory_manager_round_trip(tmp_path):
    manager = MemoryManager(database_path=str(tmp_path / "memory.db"))
    manager.add_memory("Profile", "User prefers concise technical answers.")
    manager.add_memory("Preferences", "Theme: dark mode.")

    memories = manager.search("concise")
    assert len(memories) == 1
    assert memories[0]["category"] == "Profile"

    manager.delete_memory(memories[0]["id"])
    assert manager.search("concise") == []
