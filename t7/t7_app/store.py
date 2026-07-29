from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ContentStatus


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    ContentStatus.DRAFT.value: {
        ContentStatus.IN_REVIEW.value,
        ContentStatus.ARCHIVED.value,
    },
    ContentStatus.IN_REVIEW.value: {
        ContentStatus.APPROVED.value,
        ContentStatus.REJECTED.value,
        ContentStatus.DRAFT.value,
    },
    ContentStatus.APPROVED.value: {
        ContentStatus.PUBLISHED.value,
        ContentStatus.DRAFT.value,
        ContentStatus.ARCHIVED.value,
    },
    ContentStatus.PUBLISHED.value: {
        ContentStatus.ARCHIVED.value,
    },
    ContentStatus.REJECTED.value: {
        ContentStatus.DRAFT.value,
        ContentStatus.ARCHIVED.value,
    },
    ContentStatus.ARCHIVED.value: {
        ContentStatus.DRAFT.value,
    },
}


class StoreError(Exception):
    pass


class ContentStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS content_items (
                    id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    target_language TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    audience_json TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    review_required INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    published_at TEXT
                );
                CREATE TABLE IF NOT EXISTS content_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(content_id) REFERENCES content_items(id)
                );
                CREATE INDEX IF NOT EXISTS idx_content_status_updated
                ON content_items(status, updated_at DESC);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["audience"] = json.loads(item.pop("audience_json"))
        item["citations"] = json.loads(item.pop("citations_json"))
        item["review_required"] = bool(item["review_required"])
        return item

    def create_from_t0(
        self,
        request: dict[str, Any],
        response: dict[str, Any],
    ) -> dict[str, Any]:
        content_id = str(uuid.uuid4())
        now = self._now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO content_items (
                    id, trace_id, request_id, topic, target_language, platform,
                    audience_json, content, citations_json, review_required,
                    status, created_at, updated_at, published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    content_id,
                    str(response["trace_id"]),
                    str(response["request_id"]),
                    request["topic"],
                    request["target_language"],
                    request["platform"],
                    json.dumps(request.get("audience", {}), ensure_ascii=False),
                    str(response["content"]),
                    json.dumps(response.get("citations", []), ensure_ascii=False),
                    int(bool(response.get("review_required", True))),
                    ContentStatus.DRAFT.value,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO content_audit
                (content_id, action, from_status, to_status, note, created_at)
                VALUES (?, 'generated', NULL, ?, ?, ?)
                """,
                (
                    content_id,
                    ContentStatus.DRAFT.value,
                    f"T0 trace_id={response['trace_id']}",
                    now,
                ),
            )
        return self.get(content_id)

    def list(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if status:
                rows = connection.execute(
                    """
                    SELECT * FROM content_items
                    WHERE status = ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM content_items ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get(self, content_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM content_items WHERE id = ?", (content_id,)
            ).fetchone()
        if row is None:
            raise StoreError("内容不存在")
        return self._row_to_dict(row)

    def update(
        self,
        content_id: str,
        *,
        content: str | None,
        status: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        current = self.get(content_id)
        current_status = current["status"]
        next_status = status or current_status
        if status and status != current_status:
            allowed = ALLOWED_TRANSITIONS.get(current_status, set())
            if status not in allowed:
                raise StoreError(f"不允许从 {current_status} 变更为 {status}")
        if content is not None and current_status == ContentStatus.PUBLISHED.value:
            raise StoreError("已发布内容不可直接修改，请先归档后创建新版本")
        now = self._now()
        published_at = (
            now if next_status == ContentStatus.PUBLISHED.value else current["published_at"]
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE content_items
                SET content = ?, status = ?, updated_at = ?, published_at = ?
                WHERE id = ?
                """,
                (
                    content if content is not None else current["content"],
                    next_status,
                    now,
                    published_at,
                    content_id,
                ),
            )
            action = "edited" if content is not None and status is None else "status_changed"
            connection.execute(
                """
                INSERT INTO content_audit
                (content_id, action, from_status, to_status, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (content_id, action, current_status, next_status, note, now),
            )
        return self.get(content_id)

    def history(self, content_id: str) -> list[dict[str, Any]]:
        self.get(content_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT action, from_status, to_status, note, created_at
                FROM content_audit
                WHERE content_id = ?
                ORDER BY id ASC
                """,
                (content_id,),
            ).fetchall()
        return [dict(row) for row in rows]
