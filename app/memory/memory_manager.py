from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MEMORY_CATEGORIES = ("profile", "preference", "work", "project", "habit", "workflow", "instruction")
_STOP_WORDS = {"about", "after", "also", "and", "are", "can", "could", "for", "from", "have", "into", "just", "like", "make", "myself", "not", "please", "that", "the", "this", "was", "what", "when", "with", "would", "your", "jarvis", "remember"}
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(password|passcode|api[_ -]?key|secret|access token|refresh token)\b"),
    re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
)
_TOKEN_PATTERN = re.compile(r"[\w'-]{2,}", re.UNICODE)


class MemoryManager:
    """Inspectable, user-controlled durable memory backed by SQLite."""

    def __init__(self, database_path: str | None = None) -> None:
        if database_path is None:
            database_path = str(Path.home() / "AppData" / "Roaming" / "Jarvis" / "jarvis.db")
        self.database_path = str(Path(database_path))
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS memory (
                id TEXT PRIMARY KEY, category TEXT NOT NULL, content TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, source TEXT,
                importance REAL NOT NULL DEFAULT 0.5,
                confidence REAL NOT NULL DEFAULT 0.8
            )"""
        )
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(memory)")}
        if "importance" not in columns:
            self.connection.execute("ALTER TABLE memory ADD COLUMN importance REAL NOT NULL DEFAULT 0.5")
        if "confidence" not in columns:
            self.connection.execute("ALTER TABLE memory ADD COLUMN confidence REAL NOT NULL DEFAULT 0.8")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_memory_category ON memory(category)")
        self.connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_category(category: str) -> str:
        value = (category or "").strip().lower().rstrip("s")
        aliases = {"preferences": "preference", "instructions": "instruction", "projects": "project", "habits": "habit", "workflows": "workflow"}
        value = aliases.get(value, value)
        if value not in MEMORY_CATEGORIES:
            raise ValueError(f"Category must be one of: {', '.join(MEMORY_CATEGORIES)}")
        return value

    @staticmethod
    def _validate_content(content: str) -> str:
        value = (content or "").strip()
        if not value:
            raise ValueError("Memory content cannot be empty.")
        if len(value) > 2000:
            raise ValueError("Memory content is limited to 2,000 characters.")
        if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
            raise ValueError("This looks like a secret or personal contact detail; Jarvis will not store it as memory.")
        return value

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def add_memory(self, category: str, content: str, source: str | None = None,
                   importance: float = 0.5, confidence: float = 0.8) -> dict[str, Any]:
        category = self._normalize_category(category)
        content = self._validate_content(content)
        importance = max(0.0, min(1.0, float(importance)))
        confidence = max(0.0, min(1.0, float(confidence)))
        now = self._now()
        existing = self._find_duplicate(category, content)
        if existing:
            self.connection.execute(
                "UPDATE memory SET updated_at=?, source=COALESCE(?, source), importance=MAX(importance, ?), confidence=MAX(confidence, ?) WHERE id=?",
                (now, source, importance, confidence, existing["id"]),
            )
            self.connection.commit()
            return self._row(self.connection.execute("SELECT * FROM memory WHERE id=?", (existing["id"],)).fetchone())
        memory_id = uuid.uuid4().hex
        self.connection.execute(
            "INSERT INTO memory(id, category, content, created_at, updated_at, source, importance, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (memory_id, category, content, now, now, source, importance, confidence),
        )
        self.connection.commit()
        return self._row(self.connection.execute("SELECT * FROM memory WHERE id=?", (memory_id,)).fetchone())

    def _find_duplicate(self, category: str, content: str) -> sqlite3.Row | None:
        normalized = " ".join(_TOKEN_PATTERN.findall(content.lower()))
        rows = self.connection.execute("SELECT * FROM memory WHERE LOWER(category)=?", (category,)).fetchall()
        candidate_tokens = set(normalized.split())
        for row in rows:
            stored = " ".join(_TOKEN_PATTERN.findall(row["content"].lower()))
            if normalized == stored:
                return row
            stored_tokens = set(stored.split())
            if min(len(candidate_tokens), len(stored_tokens)) >= 5:
                similarity = len(candidate_tokens & stored_tokens) / max(1, len(candidate_tokens | stored_tokens))
                if similarity >= 0.9:
                    return row
        return None

    def update_memory(self, memory_id: str, category: str, content: str, *, importance: float = 0.5,
                      confidence: float = 0.8, source: str | None = None) -> dict[str, Any] | None:
        category = self._normalize_category(category)
        content = self._validate_content(content)
        self.connection.execute(
            "UPDATE memory SET category=?, content=?, updated_at=?, importance=?, confidence=?, source=? WHERE id=?",
            (category, content, self._now(), max(0.0, min(1.0, float(importance))), max(0.0, min(1.0, float(confidence))), source, memory_id),
        )
        self.connection.commit()
        row = self.connection.execute("SELECT * FROM memory WHERE id=?", (memory_id,)).fetchone()
        return self._row(row) if row else None

    def search(self, term: str) -> list[dict[str, Any]]:
        term = (term or "").strip()
        if not term:
            return self.list_memories()
        query = f"%{term.lower()}%"
        rows = self.connection.execute(
            "SELECT * FROM memory WHERE LOWER(content) LIKE ? OR LOWER(category) LIKE ? ORDER BY importance DESC, updated_at DESC",
            (query, query),
        ).fetchall()
        return [self._row(row) for row in rows]

    def retrieve_relevant(self, text: str, limit: int = 8) -> list[dict[str, Any]]:
        terms = {word.lower() for word in _TOKEN_PATTERN.findall(text or "") if len(word) >= 3 and word.lower() not in _STOP_WORDS}
        if not terms:
            return []
        memories = self.list_memories()
        corpus = []
        for item in memories:
            tokens = [word.lower() for word in _TOKEN_PATTERN.findall(item["content"]) if len(word) >= 3 and word.lower() not in _STOP_WORDS]
            corpus.append((item, tokens, set(tokens)))
        document_frequency = {term: sum(term in token_set for _item, _tokens, token_set in corpus) for term in terms}
        scored = []
        for item, tokens, token_set in corpus:
            matched = terms & token_set
            if not matched:
                continue
            # BM25-style term relevance with modest user-controlled quality boosts.
            length_norm = len(tokens) / max(1, sum(len(entry[1]) for entry in corpus) / max(1, len(corpus)))
            lexical = sum(
                (1 + (len(corpus) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
                * (2.2 / (1.2 + 1.2 * (0.25 + 0.75 * length_norm)))
                for term in matched
            )
            phrase_bonus = 1.0 if len(terms) > 1 and all(term in token_set for term in terms) else 0.0
            quality = float(item["importance"]) * 0.25 + float(item["confidence"]) * 0.1
            scored.append((lexical + phrase_bonus + quality, item))
        return [item for _score, item in sorted(scored, key=lambda pair: (pair[0], pair[1]["updated_at"]), reverse=True)[:max(0, limit)]]

    def list_memories(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM memory ORDER BY updated_at DESC").fetchall()
        return [self._row(row) for row in rows]

    def delete_memory(self, memory_id: str) -> None:
        self.connection.execute("DELETE FROM memory WHERE id = ?", (memory_id,))
        self.connection.commit()


class MemoryCandidateExtractor:
    """Conservative memory classifier; candidate proposals never persist by themselves."""

    _EXPLICIT = re.compile(r"(?i)^remember(?: that)?\s+(.+)$")
    _CLASSIFIERS = (
        ("preference", re.compile(r"(?i)^(?:i prefer|i like|i love|i dislike|i hate|my preference is)\s+(.+)$"), 0.82, 0.72),
        ("instruction", re.compile(r"(?i)^(?:from now on,?|when i ask|please always|please never|always|never)\s+(.+)$"), 0.78, 0.8),
        ("workflow", re.compile(r"(?i)^(?:my workflow|my routine|my usual process)\s+(?:is|for .+ is)\s+(.+)$"), 0.78, 0.75),
        ("habit", re.compile(r"(?i)^(?:i usually|i often|i typically|i tend to|every (?:day|week|month))\s+(.+)$"), 0.68, 0.62),
        ("project", re.compile(r"(?i)^(?:i am working on|i'm working on|my project is|the project is)\s+(.+)$"), 0.72, 0.65),
        ("work", re.compile(r"(?i)^(?:i work as|i work at|my job is|i teach|i study)\s+(.+)$"), 0.74, 0.68),
        ("profile", re.compile(r"(?i)^(?:i am a|i'm a|i am an|i'm an|i live in|my role is)\s+(.+)$"), 0.68, 0.6),
    )

    @classmethod
    def _classify(cls, sentence: str, explicitly_requested: bool) -> dict[str, Any] | None:
        value = sentence.strip().rstrip(".!? ")
        if not value:
            return None
        if explicitly_requested:
            value = cls._EXPLICIT.sub(r"\1", value).strip().rstrip(".!? ")
        for category, pattern, confidence, importance in cls._CLASSIFIERS:
            match = pattern.match(value)
            if match:
                content = match.group(0).strip().rstrip(".!? ")
                break
        else:
            if not explicitly_requested:
                return None
            category, confidence, importance = "profile", 0.55, 0.65
            content = value
        try:
            content = MemoryManager._validate_content(content)
        except ValueError:
            return None
        return {"category": category, "content": content, "source": "conversation", "importance": importance,
                "confidence": confidence + (0.12 if explicitly_requested else 0.0)}

    def extract_many(self, text: str) -> list[dict[str, Any]]:
        candidates = []
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", (text or "").strip()):
            explicit_match = self._EXPLICIT.match(sentence.strip())
            candidate = self._classify(sentence, explicitly_requested=bool(explicit_match))
            if candidate and not any(
                current["category"] == candidate["category"] and
                " ".join(_TOKEN_PATTERN.findall(current["content"].lower())) == " ".join(_TOKEN_PATTERN.findall(candidate["content"].lower()))
                for current in candidates
            ):
                candidates.append(candidate)
        return candidates

    def extract(self, text: str) -> dict[str, Any] | None:
        """Backward-compatible helper returning the first candidate, if any."""
        candidates = self.extract_many(text)
        return candidates[0] if candidates else None
