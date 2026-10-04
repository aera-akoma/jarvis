from __future__ import annotations

import json
import math
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


class ExportImportManager:
    """Encrypted, validated, credential-free backup and restore for Jarvis data."""

    FORMAT = "jarvis-portable-backup"
    VERSION = 1
    MAGIC = b"JARVIS-BACKUP\x00"
    AAD = MAGIC + bytes([VERSION])
    HEADER_LENGTH = len(MAGIC) + 1 + 16 + 12
    MAX_BACKUP_BYTES = 100 * 1024 * 1024
    MAX_ITEMS = 250_000
    SAFE_SETTINGS = frozenset({"theme", "default_model", "voice_output", "voice_language"})
    SECRET_ASSIGNMENTS = re.compile(
        r"(?i)(['\"]?(?:api[_ -]?key|password|passwd|secret|token|credential|"
        r"authorization|client[_ -]?secret|access[_ -]?token|refresh[_ -]?token)"
        r"['\"]?\s*(?::|=|\bis\b)\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)"
    )
    URL_CREDENTIALS = re.compile(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@")
    PRIVATE_KEY = re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?"
        r"-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    )
    BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")
    PROVIDER_TOKEN = re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{16,}\b")
    AWS_TOKEN = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
    JWT_TOKEN = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
    GITHUB_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b")
    MEMORY_COLUMNS = ("id", "category", "content", "created_at", "updated_at", "source", "importance", "confidence")
    CONVERSATION_COLUMNS = ("id", "title", "created_at", "updated_at", "model_name", "project_path")

    def __init__(self, database_path: str | None = None, root: str | None = None) -> None:
        self.database_path = str(database_path) if database_path else None
        self.root = Path(root) if root is not None else Path.home() / "AppData" / "Roaming" / "Jarvis" / "exports"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _clone(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return json.loads(json.dumps(payload, ensure_ascii=False))
        except (TypeError, ValueError) as exc:
            raise ValueError("Backup data must contain JSON-compatible values.") from exc

    def export_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Deprecated in-memory compatibility helper; does not write plaintext files."""
        return self._clone(payload)

    def import_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Deprecated in-memory compatibility helper; use read_backup for files."""
        return self._clone(payload)

    def _table_exists(self, connection: sqlite3.Connection, table: str) -> bool:
        return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None

    def _rows(self, connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
        if not self._table_exists(connection, table):
            return []
        return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"').fetchall()]

    @classmethod
    def _redact_text(cls, value: str) -> tuple[str, int]:
        redacted = value
        count = 0
        for pattern, replacement in (
            (cls.SECRET_ASSIGNMENTS, lambda match: match.group(1) + '"[REDACTED]"'),
            (cls.URL_CREDENTIALS, r"\1[REDACTED]@"),
            (cls.PRIVATE_KEY, "[REDACTED_PRIVATE_KEY]"),
            (cls.BEARER_TOKEN, "Bearer [REDACTED]"),
            (cls.PROVIDER_TOKEN, "[REDACTED_TOKEN]"),
            (cls.AWS_TOKEN, "[REDACTED_TOKEN]"),
            (cls.JWT_TOKEN, "[REDACTED_TOKEN]"),
            (cls.GITHUB_TOKEN, "[REDACTED_TOKEN]"),
        ):
            redacted, matches = pattern.subn(replacement, redacted)
            count += matches
        return redacted, count

    @classmethod
    def _redact_fields(cls, item: dict[str, Any], fields: tuple[str, ...]) -> tuple[dict[str, Any], int]:
        count = 0
        for field in fields:
            value = item.get(field)
            if isinstance(value, str):
                item[field], redacted = cls._redact_text(value)
                count += redacted
        return item, count

    def build_backup(self) -> dict[str, Any]:
        if not self.database_path:
            raise ValueError("A Jarvis database path is required to export personal data.")
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        redacted_count = 0
        try:
            connection.execute("BEGIN")
            settings = {}
            for row in self._rows(connection, "settings"):
                if row.get("key") in self.SAFE_SETTINGS:
                    settings[row["key"]], count = self._redact_text(str(row["value"]))
                    redacted_count += count
            conversations = []
            for row in self._rows(connection, "conversations"):
                item = {key: row.get(key) for key in self.CONVERSATION_COLUMNS}
                item, count = self._redact_fields(item, ("title", "project_path"))
                redacted_count += count
                conversations.append(item)
            messages = []
            for row in self._rows(connection, "messages"):
                item = {key: row.get(key) for key in ("id", "conversation_id", "role", "content", "created_at")}
                item, count = self._redact_fields(item, ("content",))
                redacted_count += count
                messages.append(item)
            memories = []
            for row in self._rows(connection, "memory"):
                item = {key: row.get(key) for key in self.MEMORY_COLUMNS}
                item, count = self._redact_fields(item, ("content", "source"))
                redacted_count += count
                if not isinstance(item.get("importance"), (int, float)):
                    item["importance"] = 0.5
                if not isinstance(item.get("confidence"), (int, float)):
                    item["confidence"] = 0.8
                memories.append(item)
            workflows = []
            for row in self._rows(connection, "workflows"):
                item = {key: row.get(key) for key in ("id", "name", "steps", "created_at", "updated_at")}
                item, count = self._redact_fields(item, ("name", "steps"))
                redacted_count += count
                workflows.append(item)
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()
        payload = {
            "format": self.FORMAT,
            "version": self.VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data": {"settings": settings, "conversations": conversations, "messages": messages,
                     "memories": memories, "workflows": workflows},
            "notes": ["OS-stored credentials and secrets are excluded. Common credential strings in messages, memories, and workflow steps are redacted.",
                      "Workflow observation history is excluded.", "Absolute project and workflow paths may need adjustment on another PC."],
            "redacted_secret_count": redacted_count,
        }
        self.validate_payload(payload)
        return payload

    @staticmethod
    def _derive_key(passphrase: str, salt: bytes) -> bytes:
        # 64 MiB Scrypt cost balances offline-guessing resistance with a usable desktop restore time.
        return Scrypt(salt=salt, length=32, n=2**16, r=8, p=1).derive(passphrase.encode("utf-8"))

    @staticmethod
    def _validate_passphrase(passphrase: str) -> None:
        if not isinstance(passphrase, str) or len(passphrase) < 12:
            raise ValueError("Use a backup passphrase with at least 12 characters.")

    def write_backup(self, path: str | Path, passphrase: str) -> Path:
        self._validate_passphrase(passphrase)
        return self.write_payload_backup(path, passphrase, self.build_backup())

    def write_payload_backup(self, path: str | Path, passphrase: str, payload: dict[str, Any]) -> Path:
        self._validate_passphrase(passphrase)
        self.validate_payload(payload)
        plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(plaintext) > self.MAX_BACKUP_BYTES:
            raise ValueError("Jarvis backup exceeds the 100 MB limit.")
        salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
        ciphertext = AESGCM(self._derive_key(passphrase, salt)).encrypt(nonce, plaintext, self.AAD)
        output = Path(path).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".tmp")
        try:
            temporary.write_bytes(self.MAGIC + bytes([self.VERSION]) + salt + nonce + ciphertext)
            os.replace(temporary, output)
        finally:
            if temporary.exists():
                temporary.unlink()
        return output

    def read_backup(self, path: str | Path, passphrase: str) -> dict[str, Any]:
        self._validate_passphrase(passphrase)
        source = Path(path).expanduser()
        if not source.is_file():
            raise ValueError("Backup file was not found.")
        size = source.stat().st_size
        if size < self.HEADER_LENGTH + 16 or size > self.MAX_BACKUP_BYTES + self.HEADER_LENGTH + 16:
            raise ValueError("Backup file has an invalid size.")
        blob = source.read_bytes()
        magic_length = len(self.MAGIC)
        if blob[:magic_length] != self.MAGIC or blob[magic_length] != self.VERSION:
            raise ValueError("This is not a supported Jarvis encrypted backup.")
        cursor = magic_length + 1
        salt, nonce, ciphertext = blob[cursor:cursor + 16], blob[cursor + 16:cursor + 28], blob[cursor + 28:]
        try:
            plaintext = AESGCM(self._derive_key(passphrase, salt)).decrypt(nonce, ciphertext, self.AAD)
            payload = json.loads(plaintext.decode("utf-8"))
        except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("Could not unlock this backup. Check the passphrase and file integrity.") from exc
        self.validate_payload(payload)
        return payload

    def validate_payload(self, payload: Any) -> None:
        if not isinstance(payload, dict) or payload.get("format") != self.FORMAT or payload.get("version") != self.VERSION:
            raise ValueError("Backup format or version is not supported.")
        if not set(payload).issubset({"format", "version", "created_at", "data", "notes", "redacted_secret_count"}):
            raise ValueError("Backup contains unsupported top-level fields.")
        if not isinstance(payload.get("created_at"), str) or len(payload["created_at"]) > 100:
            raise ValueError("Backup contains invalid creation metadata.")
        if not isinstance(payload.get("redacted_secret_count", 0), int) or payload.get("redacted_secret_count", 0) < 0:
            raise ValueError("Backup contains invalid redaction metadata.")
        data = payload.get("data")
        try:
            if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > self.MAX_BACKUP_BYTES:
                raise ValueError("Backup payload exceeds the 100 MB limit.")
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc) == "Backup payload exceeds the 100 MB limit.":
                raise
            raise ValueError("Backup contains data that cannot be validated safely.") from exc
        required = {"settings", "conversations", "messages", "memories", "workflows"}
        if not isinstance(data, dict) or set(data) != required:
            raise ValueError("Backup is missing required data sections.")
        if not isinstance(data["settings"], dict) or not set(data["settings"]).issubset(self.SAFE_SETTINGS):
            raise ValueError("Backup contains an unsupported setting. Credentials and secret settings are never imported.")
        if any(not isinstance(value, str) or len(value) > 1000 for value in data["settings"].values()):
            raise ValueError("Backup contains an invalid setting value.")
        notes = payload.get("notes", [])
        if not isinstance(notes, list) or len(notes) > 50 or any(not isinstance(note, str) or len(note) > 1000 for note in notes):
            raise ValueError("Backup contains invalid metadata.")
        for key in ("conversations", "messages", "memories", "workflows"):
            if not isinstance(data[key], list) or len(data[key]) > self.MAX_ITEMS:
                raise ValueError(f"Backup section '{key}' is invalid or too large.")
        conversation_ids = set()
        for item in data["conversations"]:
            if not isinstance(item, dict) or not set(item).issubset(set(self.CONVERSATION_COLUMNS)) or not all(isinstance(item.get(key), str) for key in ("id", "title", "created_at", "updated_at")):
                raise ValueError("Backup contains an invalid conversation record.")
            if len(item["id"]) > 128 or len(item["title"]) > 500 or any(item.get(key) is not None and not isinstance(item.get(key), str) for key in ("model_name", "project_path")):
                raise ValueError("Backup contains an oversized or invalid conversation field.")
            if item["id"] in conversation_ids:
                raise ValueError("Backup contains duplicate conversation IDs.")
            conversation_ids.add(item["id"])
        message_ids = set()
        for item in data["messages"]:
            if not isinstance(item, dict) or not set(item).issubset({"id", "conversation_id", "role", "content", "created_at"}) or not all(isinstance(item.get(key), str) for key in ("id", "conversation_id", "role", "content", "created_at")):
                raise ValueError("Backup contains an invalid message record.")
            if len(item["id"]) > 128 or item["role"] not in {"user", "assistant", "system", "tool"} or len(item["content"]) > 1_000_000:
                raise ValueError("Backup contains an oversized or unsupported message.")
            if item["conversation_id"] not in conversation_ids:
                raise ValueError("Backup contains a message without a matching conversation.")
            if item["id"] in message_ids:
                raise ValueError("Backup contains duplicate message IDs.")
            message_ids.add(item["id"])
        memory_ids = set()
        for item in data["memories"]:
            if not isinstance(item, dict) or not set(item).issubset(set(self.MEMORY_COLUMNS)) or not all(isinstance(item.get(key), str) for key in ("id", "category", "content", "created_at", "updated_at")):
                raise ValueError("Backup contains an invalid memory record.")
            if len(item["content"]) > 2000:
                raise ValueError("Backup contains an oversized memory record.")
            for score_name in ("importance", "confidence"):
                score = item.get(score_name, 0.5 if score_name == "importance" else 0.8)
                if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Backup contains invalid memory metadata.")
            if item["id"] in memory_ids:
                raise ValueError("Backup contains duplicate memory IDs.")
            memory_ids.add(item["id"])
        workflow_ids = set()
        for item in data["workflows"]:
            if not isinstance(item, dict) or not set(item).issubset({"id", "name", "steps", "created_at", "updated_at"}) or not all(isinstance(item.get(key), str) for key in ("id", "name", "steps", "created_at", "updated_at")):
                raise ValueError("Backup contains an invalid workflow record.")
            if len(item["steps"]) > 100_000:
                raise ValueError("Backup contains an oversized workflow record.")
            if item["id"] in workflow_ids:
                raise ValueError("Backup contains duplicate workflow IDs.")
            workflow_ids.add(item["id"])

    @staticmethod
    def preview(payload: dict[str, Any]) -> dict[str, int]:
        data = payload["data"]
        return {key: len(data[key]) if isinstance(data[key], list) else len(data[key]) for key in
                ("conversations", "messages", "memories", "workflows", "settings")}

    def _ensure_restore_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, model_name TEXT, project_path TEXT);
            CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL,
                content TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(conversation_id) REFERENCES conversations(id));
            CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY, category TEXT NOT NULL, content TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, source TEXT, importance REAL NOT NULL DEFAULT 0.5,
                confidence REAL NOT NULL DEFAULT 0.8);
            CREATE TABLE IF NOT EXISTS workflows(id TEXT PRIMARY KEY, name TEXT NOT NULL, steps TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"""
        )
        memory_columns = {row[1] for row in connection.execute("PRAGMA table_info(memory)")}
        if "importance" not in memory_columns:
            connection.execute("ALTER TABLE memory ADD COLUMN importance REAL NOT NULL DEFAULT 0.5")
        if "confidence" not in memory_columns:
            connection.execute("ALTER TABLE memory ADD COLUMN confidence REAL NOT NULL DEFAULT 0.8")

    def restore_payload(self, payload: dict[str, Any], *, strategy: str = "merge") -> dict[str, int]:
        self.validate_payload(payload)
        if not self.database_path:
            raise ValueError("A Jarvis database path is required to restore personal data.")
        if strategy not in {"merge", "replace"}:
            raise ValueError("Restore strategy must be 'merge' or 'replace'.")
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        inserted = {key: 0 for key in ("settings", "conversations", "messages", "memories", "workflows")}
        try:
            self._ensure_restore_schema(connection)
            with connection:
                if strategy == "replace":
                    for table in ("messages", "conversations", "memory", "workflows"):
                        connection.execute(f'DELETE FROM "{table}"')
                    if self._table_exists(connection, "workflow_observations"):
                        connection.execute("DELETE FROM workflow_observations")
                    connection.executemany("DELETE FROM settings WHERE key=?", ((key,) for key in self.SAFE_SETTINGS))
                for key, value in payload["data"]["settings"].items():
                    existing_setting = connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
                    if existing_setting is None or existing_setting["value"] != str(value):
                        connection.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
                        inserted["settings"] += 1
                conversation_map: dict[str, str] = {}
                for item in payload["data"]["conversations"]:
                    existing = connection.execute("SELECT title,created_at,updated_at,model_name,project_path FROM conversations WHERE id=?", (item["id"],)).fetchone()
                    new_id = item["id"]
                    same_record = existing and all(existing[key] == item.get(key) for key in ("title", "created_at", "updated_at", "model_name", "project_path"))
                    if existing and not same_record:
                        new_id = uuid.uuid4().hex
                    conversation_map[item["id"]] = new_id
                    cursor = connection.execute(
                        "INSERT OR IGNORE INTO conversations(id,title,created_at,updated_at,model_name,project_path) VALUES(?,?,?,?,?,?)",
                        (new_id, item["title"], item["created_at"], item["updated_at"], item.get("model_name"), item.get("project_path")),
                    )
                    inserted["conversations"] += cursor.rowcount
                for item in payload["data"]["messages"]:
                    message_id = item["id"]
                    mapped_conversation_id = conversation_map[item["conversation_id"]]
                    existing_message = connection.execute("SELECT conversation_id,role,content,created_at FROM messages WHERE id=?", (message_id,)).fetchone()
                    if existing_message:
                        same_message = all(existing_message[key] == expected for key, expected in (
                            ("conversation_id", mapped_conversation_id), ("role", item["role"]),
                            ("content", item["content"]), ("created_at", item["created_at"]),
                        ))
                        if same_message:
                            continue
                        message_id = uuid.uuid4().hex
                    cursor = connection.execute(
                        "INSERT OR IGNORE INTO messages(id,conversation_id,role,content,created_at) VALUES(?,?,?,?,?)",
                        (message_id, mapped_conversation_id, item["role"], item["content"], item["created_at"]),
                    )
                    inserted["messages"] += cursor.rowcount
                for item in payload["data"]["memories"]:
                    duplicate = connection.execute("SELECT 1 FROM memory WHERE LOWER(category)=LOWER(?) AND LOWER(TRIM(content))=LOWER(TRIM(?)) LIMIT 1", (item["category"], item["content"])).fetchone()
                    if duplicate:
                        continue
                    memory_id = item["id"]
                    if connection.execute("SELECT 1 FROM memory WHERE id=?", (memory_id,)).fetchone():
                        memory_id = uuid.uuid4().hex
                    connection.execute(
                        "INSERT INTO memory(id,category,content,created_at,updated_at,source,importance,confidence) VALUES(?,?,?,?,?,?,?,?)",
                        (memory_id, item["category"], item["content"], item["created_at"], item["updated_at"], item.get("source"), item.get("importance", 0.5), item.get("confidence", 0.8)),
                    )
                    inserted["memories"] += 1
                for item in payload["data"]["workflows"]:
                    duplicate = connection.execute("SELECT 1 FROM workflows WHERE LOWER(name)=LOWER(?) AND steps=? LIMIT 1", (item["name"], item["steps"])).fetchone()
                    if duplicate:
                        continue
                    workflow_id = item["id"]
                    if connection.execute("SELECT 1 FROM workflows WHERE id=?", (workflow_id,)).fetchone():
                        workflow_id = uuid.uuid4().hex
                    connection.execute("INSERT INTO workflows(id,name,steps,created_at,updated_at) VALUES(?,?,?,?,?)",
                                       (workflow_id, item["name"], item["steps"], item["created_at"], item["updated_at"]))
                    inserted["workflows"] += 1
        finally:
            connection.close()
        return inserted

    def restore_backup(self, path: str | Path, passphrase: str, *, strategy: str = "merge") -> dict[str, int]:
        payload = self.read_backup(path, passphrase)
        return self.restore_payload(payload, strategy=strategy)
