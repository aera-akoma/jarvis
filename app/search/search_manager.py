from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable


class SearchManager:
    """Modular search across Jarvis knowledge, local files, chat, memory, and the web."""

    SUPPORTED_SOURCES = frozenset({"knowledge", "files", "conversations", "memory", "web"})
    TEXT_SUFFIXES = frozenset({".txt", ".md", ".rst", ".py", ".json", ".yaml", ".yml", ".toml", ".ini", ".csv", ".log", ".html", ".htm", ".xml", ".sql", ".ps1", ".bat", ".sh"})
    SKIP_DIRS = frozenset({".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "AppData"})

    def __init__(self, database_path: str | Path | None = None, *, web_provider: Callable[[str, int], list[dict[str, Any]]] | None = None) -> None:
        self.database_path = str(database_path) if database_path else None
        self.web_provider = web_provider
        self.index = {
            "Jarvis": "A local desktop AI assistant built with Python and PySide6.",
            "desktop": "A native Windows desktop interface for personal AI tasks.",
            "OpenCode": "A runtime layer for model access and AI orchestration.",
            "memory": "Durable local memory stores user preferences and recurring tasks.",
            "workflow": "Saved local steps for common repetitive actions.",
        }

    @staticmethod
    def _terms(query: str) -> list[str]:
        return list(dict.fromkeys(term.lower() for term in re.findall(r"[\w'-]{2,}", query or "")))

    @staticmethod
    def _score(text: str, terms: list[str]) -> int:
        lowered = text.lower()
        return sum(lowered.count(term) for term in terms)

    def search(self, query: str, *, sources: set[str] | list[str] | tuple[str, ...] | None = None,
               project_path: str | Path | None = None, limit: int = 30) -> list[dict[str, Any]]:
        terms = self._terms(query)
        if not terms:
            return []
        selected = set(sources or {"knowledge", "files", "conversations", "memory"})
        unknown = selected - self.SUPPORTED_SOURCES
        if unknown:
            raise ValueError(f"Unsupported search source(s): {', '.join(sorted(unknown))}")
        maximum = max(1, min(int(limit), 100))
        results: list[dict[str, Any]] = []
        if "knowledge" in selected:
            for title, snippet in self.index.items():
                score = self._score(f"{title} {snippet}", terms)
                if score:
                    results.append({"source": "Jarvis knowledge", "title": title, "snippet": snippet, "score": score})
        if "files" in selected and project_path:
            results.extend(self._search_files(Path(project_path), terms, maximum))
        if {"conversations", "memory"} & selected and self.database_path:
            results.extend(self._search_database(terms, selected, maximum))
        if "web" in selected:
            try:
                for item in self._search_web(query, maximum):
                    results.append(item)
            except Exception as exc:
                results.append({"source": "Web search", "title": "Search unavailable", "snippet": str(exc), "score": 0, "error": True})
        results.sort(key=lambda item: (item.get("score", 0), item.get("source") == "Jarvis knowledge"), reverse=True)
        return results[:maximum]

    def _search_files(self, root: Path, terms: list[str], limit: int) -> list[dict[str, Any]]:
        root = root.expanduser()
        if not root.exists() or not root.is_dir():
            return [{"source": "Project files", "title": "Folder unavailable", "snippet": str(root), "score": 0, "error": True}]
        results = []
        visited = 0
        try:
            for directory, child_dirs, filenames in os.walk(root, topdown=True):
                child_dirs[:] = [name for name in child_dirs if name not in self.SKIP_DIRS]
                for filename in filenames:
                    if visited >= 2000 or len(results) >= limit:
                        break
                    path = Path(directory) / filename
                    try:
                        if path.suffix.lower() not in self.TEXT_SUFFIXES or path.stat().st_size > 512_000:
                            continue
                        visited += 1
                        content = path.read_text(encoding="utf-8", errors="ignore")
                    except (OSError, ValueError):
                        continue
                    best = (self._score(path.name, terms), f"File name: {path.name}" if self._score(path.name, terms) else "")
                    for line in content.splitlines():
                        score = self._score(line, terms)
                        if score > best[0]:
                            best = (score, line.strip())
                    if best[0]:
                        results.append({"source": "Project file", "title": str(path), "snippet": best[1][:500], "score": best[0]})
                if visited >= 2000 or len(results) >= limit:
                    break
        except OSError:
            return [{"source": "Project files", "title": "Could not scan folder", "snippet": str(root), "score": 0, "error": True}]
        return results

    def _search_database(self, terms: list[str], sources: set[str], limit: int) -> list[dict[str, Any]]:
        results = []
        try:
            connection = sqlite3.connect(self.database_path)
            connection.row_factory = sqlite3.Row
            try:
                if "conversations" in sources:
                    rows = connection.execute("SELECT c.title, c.id, m.role, m.content, m.created_at FROM messages m JOIN conversations c ON c.id=m.conversation_id ORDER BY m.created_at DESC LIMIT 5000").fetchall()
                    for row in rows:
                        score = self._score(row["content"], terms)
                        if score:
                            results.append({"source": "Conversation", "title": row["title"], "snippet": f"{row['role']}: {row['content'][:500]}", "conversation_id": row["id"], "created_at": row["created_at"], "score": score})
                if "memory" in sources:
                    try:
                        rows = connection.execute("SELECT category, content, updated_at FROM memory ORDER BY updated_at DESC LIMIT 2000").fetchall()
                    except sqlite3.OperationalError:
                        rows = []
                    for row in rows:
                        score = self._score(f"{row['category']} {row['content']}", terms)
                        if score:
                            results.append({"source": "Memory", "title": row["category"], "snippet": row["content"][:500], "updated_at": row["updated_at"], "score": score})
            finally:
                connection.close()
        except sqlite3.Error as exc:
            return [{"source": "Local search", "title": "Database unavailable", "snippet": str(exc), "score": 0, "error": True}]
        return results[:limit * 2]

    def _search_web(self, query: str, limit: int) -> list[dict[str, Any]]:
        provider = self.web_provider
        if provider is None:
            try:
                from ddgs import DDGS
            except ImportError as exc:
                raise RuntimeError("Web search requires the optional ddgs dependency. Install project requirements and retry.") from exc
            provider = lambda term, count: DDGS(timeout=8).text(term, max_results=count, backend="auto")
        results = []
        for item in provider(query, min(limit, 10)):
            title = str(item.get("title", "Web result"))
            body = str(item.get("body", item.get("snippet", "")))
            url = str(item.get("href", item.get("url", "")))
            results.append({"source": "Web search", "title": title, "snippet": body[:500], "url": url, "score": self._score(title + " " + body, self._terms(query))})
        return results
