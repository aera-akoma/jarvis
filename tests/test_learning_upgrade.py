from __future__ import annotations

from app.agent import AgentLoop
from app.memory.memory_manager import MemoryCandidateExtractor, MemoryManager
from app.permissions.policy import PermissionPolicy
from app.tooling import ToolRegistry


def _registry(tmp_path) -> ToolRegistry:
    return ToolRegistry(memory_manager=MemoryManager(str(tmp_path / "memory.db")))


def test_remember_memory_tool_saves_with_category(tmp_path):
    registry = _registry(tmp_path)
    result = registry.execute("remember_memory", params={"content": "I prefer concise answers.", "category": "preference"})
    assert result["success"] is True
    assert result["saved"]["category"] == "preference"
    assert result["saved"]["source"] == "remember_memory"
    assert len(registry.memory_manager.list_memories()) == 1


def test_remember_memory_auto_classifies_category(tmp_path):
    registry = _registry(tmp_path)
    result = registry.execute("remember_memory", params={"content": "I prefer Groq as my primary model."})
    assert result["success"] is True
    assert result["saved"]["category"] == "preference"


def test_remember_memory_requires_a_category_when_unrecognised(tmp_path):
    registry = _registry(tmp_path)
    result = registry.execute("remember_memory", params={"content": "The sky is blue today."})
    assert result["success"] is False
    assert "category" in result["error"].lower()


def test_remember_memory_blocks_secrets_and_empty_content(tmp_path):
    registry = _registry(tmp_path)
    secret = registry.execute("remember_memory", params={"content": "My API key is sk-abcdefghijklmno123456"})
    assert secret["success"] is False
    empty = registry.execute("remember_memory", params={"content": "   "})
    assert empty["success"] is False
    assert registry.memory_manager.list_memories() == []


def test_remember_memory_tool_requires_moderate_approval():
    policy = PermissionPolicy()
    assert policy.confirm_required("remember_memory", "moderate") is True
    assert policy.allows("remember_memory", "moderate", confirm=True) is True


def test_agent_prompt_shows_categories_and_all_retrieved_memories():
    loop = AgentLoop()
    memory = [{"category": "preference", "content": f"Likes style topic {index}"} for index in range(6)]
    prompt = loop.build_agent_prompt(request="hello", memory=memory)
    assert "[preference]" in prompt
    for index in range(6):
        assert f"topic {index}" in prompt
    assert "remember_memory" in prompt


def test_agent_prompt_memory_is_bounded():
    loop = AgentLoop()
    memory = [{"category": "work", "content": "x" * 1000} for _ in range(10)]
    prompt = loop.build_agent_prompt(request="hello", memory=memory)
    assert len(prompt) < 15000


def test_extract_conversation_finds_preferences_across_messages():
    extractor = MemoryCandidateExtractor()
    messages = [
        {"role": "user", "content": "Please fix the report."},
        {"role": "assistant", "content": "I prefer the report summary to stay on page one."},
        {"role": "user", "content": "I prefer dark mode in the UI."},
    ]
    candidates = extractor.extract_conversation(messages)
    assert any(candidate["category"] == "preference" for candidate in candidates)
    # The same fact appears at most once even if repeated across messages.
    assert len(candidates) == len(extractor.dedupe_candidates(candidates))


def test_dedupe_candidates_collapses_near_identical():
    extractor = MemoryCandidateExtractor()
    candidates = [
        {"category": "preference", "content": "I prefer dark mode."},
        {"category": "preference", "content": "I prefer dark mode."},
        {"category": "work", "content": "Works on Jarvis."},
    ]
    deduped = extractor.dedupe_candidates(candidates)
    assert len(deduped) == 2