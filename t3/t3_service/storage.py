from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class SQLiteIndex:
    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    text TEXT NOT NULL,
                    section TEXT,
                    language TEXT,
                    version TEXT,
                    authorization_status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    sequence INTEGER NOT NULL
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_auth ON chunks(authorization_status)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id)"
            )

    def check_ready(self) -> None:
        with self._lock:
            self._connection.execute("SELECT 1").fetchone()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def upsert(self, records: list[dict[str, Any]]) -> int:
        indexed_count = 0
        with self._lock, self._connection:
            for record in records:
                metadata = dict(record.get("metadata") or {})
                version = metadata.get("version")
                for chunk in record.get("chunks") or []:
                    self._connection.execute(
                        """
                        INSERT INTO chunks (
                            chunk_id, source_id, title, source_uri, media_type, text,
                            section, language, version, authorization_status,
                            metadata_json, sequence
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(chunk_id) DO UPDATE SET
                            source_id=excluded.source_id,
                            title=excluded.title,
                            source_uri=excluded.source_uri,
                            media_type=excluded.media_type,
                            text=excluded.text,
                            section=excluded.section,
                            language=excluded.language,
                            version=excluded.version,
                            authorization_status=excluded.authorization_status,
                            metadata_json=excluded.metadata_json,
                            sequence=excluded.sequence
                        """,
                        (
                            chunk["chunk_id"],
                            record["source_id"],
                            record["title"],
                            record["source_uri"],
                            record["media_type"],
                            chunk["text"],
                            chunk.get("section") or metadata.get("section"),
                            chunk.get("language") or metadata.get("language"),
                            version,
                            record["authorization_status"],
                            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                            chunk["sequence"],
                        ),
                    )
                    indexed_count += 1
        return indexed_count

    def all_chunks(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM chunks ORDER BY chunk_id ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()
        return int(row["count"])
