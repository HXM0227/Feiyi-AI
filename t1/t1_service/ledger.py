from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_ledger (
    source_id TEXT PRIMARY KEY,
    source_uri TEXT NOT NULL,
    title TEXT NOT NULL,
    media_type TEXT NOT NULL,
    authorization_status TEXT NOT NULL,
    language TEXT,
    version TEXT,
    reviewer TEXT,
    content_hash TEXT NOT NULL,
    chunk_count INTEGER NOT NULL,
    publish INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    trace_id TEXT,
    request_id TEXT
)
"""


class Ledger:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def upsert(
        self,
        *,
        source_id: str,
        source_uri: str,
        title: str,
        media_type: str,
        authorization_status: str,
        metadata: dict[str, Any],
        content: str,
        chunk_count: int,
        publish: bool,
        trace_id: str | None,
        request_id: str | None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str)
        language = _string_value(metadata.get("language"))
        version = _string_value(metadata.get("version"))
        reviewer = _string_value(metadata.get("reviewer"))
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO source_ledger (
                    source_id, source_uri, title, media_type, authorization_status,
                    language, version, reviewer, content_hash, chunk_count, publish,
                    metadata_json, created_at, updated_at, trace_id, request_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_uri=excluded.source_uri,
                    title=excluded.title,
                    media_type=excluded.media_type,
                    authorization_status=excluded.authorization_status,
                    language=excluded.language,
                    version=excluded.version,
                    reviewer=excluded.reviewer,
                    content_hash=excluded.content_hash,
                    chunk_count=excluded.chunk_count,
                    publish=excluded.publish,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at,
                    trace_id=excluded.trace_id,
                    request_id=excluded.request_id
                """,
                (
                    source_id,
                    source_uri,
                    title,
                    media_type,
                    authorization_status,
                    language,
                    version,
                    reviewer,
                    content_hash,
                    chunk_count,
                    int(publish),
                    metadata_json,
                    now,
                    now,
                    trace_id,
                    request_id,
                ),
            )
            conn.commit()

    def check_ready(self) -> None:
        """Raise when the SQLite ledger cannot execute a basic query."""
        with closing(self._connect()) as conn:
            conn.execute("SELECT 1").fetchone()

    def list_sources(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM source_ledger ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
