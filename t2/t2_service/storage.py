from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import (
    AuthorizationStatus,
    EntityInput,
    EntityResult,
    GraphRecord,
    RelationInput,
    RelationResult,
    SourceRef,
)


VISIBLE_AUTHORIZATION: tuple[str, ...] = ("authorized", "public")


class GraphStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._uri = db_path == ":memory:"
        self._memory_connection: sqlite3.Connection | None = None
        if self._uri:
            self._memory_connection = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_connection.row_factory = sqlite3.Row
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = self._memory_connection or sqlite3.connect(
            self.db_path, timeout=10, check_same_thread=False
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


    def close(self) -> None:
        if self._memory_connection is not None:
            self._memory_connection.close()
            self._memory_connection = None

    def initialize(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    authorization_status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    section TEXT,
                    language TEXT
                );
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    language TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS entity_aliases (
                    entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
                    alias TEXT NOT NULL,
                    alias_norm TEXT NOT NULL,
                    PRIMARY KEY (entity_id, alias_norm)
                );
                CREATE INDEX IF NOT EXISTS idx_entity_aliases_norm ON entity_aliases(alias_norm);
                CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(canonical_name);
                CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
                CREATE TABLE IF NOT EXISTS entity_sources (
                    entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
                    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
                    chunk_id TEXT REFERENCES chunks(chunk_id) ON DELETE SET NULL,
                    PRIMARY KEY (entity_id, source_id, chunk_id)
                );
                CREATE TABLE IF NOT EXISTS relations (
                    relation_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
                    predicate TEXT NOT NULL,
                    object_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
                    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
                    chunk_id TEXT REFERENCES chunks(chunk_id) ON DELETE SET NULL,
                    authorization_status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_rel_subject ON relations(subject_id);
                CREATE INDEX IF NOT EXISTS idx_rel_object ON relations(object_id);
                CREATE INDEX IF NOT EXISTS idx_rel_predicate ON relations(predicate);
                """
            )
            connection.commit()
        finally:
            if self._memory_connection is None:
                connection.close()

    def check_ready(self) -> None:
        connection = self._connect()
        try:
            connection.execute("SELECT 1").fetchone()
        finally:
            if self._memory_connection is None:
                connection.close()

    def upsert(self, records: Iterable[GraphRecord]) -> tuple[int, int, list[str]]:
        connection = self._connect()
        entity_count = 0
        relation_count = 0
        warnings: list[str] = []
        try:
            for record in records:
                connection.execute(
                    """
                    INSERT INTO sources(source_id, title, source_uri, media_type,
                                        authorization_status, metadata_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(source_id) DO UPDATE SET
                        title=excluded.title,
                        source_uri=excluded.source_uri,
                        media_type=excluded.media_type,
                        authorization_status=excluded.authorization_status,
                        metadata_json=excluded.metadata_json,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        record.source_id,
                        record.title,
                        record.source_uri,
                        record.media_type,
                        record.authorization_status,
                        _json(record.metadata),
                    ),
                )
                for chunk in record.chunks:
                    connection.execute(
                        """
                        INSERT INTO chunks(chunk_id, source_id, text, sequence, section, language)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(chunk_id) DO UPDATE SET
                            source_id=excluded.source_id,
                            text=excluded.text,
                            sequence=excluded.sequence,
                            section=excluded.section,
                            language=excluded.language
                        """,
                        (
                            chunk.chunk_id,
                            record.source_id,
                            chunk.text,
                            chunk.sequence,
                            chunk.section,
                            chunk.language,
                        ),
                    )
                for entity in record.entities:
                    connection.execute(
                        """
                        INSERT INTO entities(entity_id, entity_type, canonical_name, language,
                                             metadata_json, updated_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(entity_id) DO UPDATE SET
                            entity_type=excluded.entity_type,
                            canonical_name=excluded.canonical_name,
                            language=excluded.language,
                            metadata_json=excluded.metadata_json,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                        (
                            entity.entity_id,
                            entity.entity_type,
                            entity.canonical_name,
                            entity.language,
                            _json(entity.metadata),
                        ),
                    )
                    for alias in entity.aliases:
                        connection.execute(
                            """
                            INSERT INTO entity_aliases(entity_id, alias, alias_norm)
                            VALUES (?, ?, ?)
                            ON CONFLICT(entity_id, alias_norm) DO UPDATE SET alias=excluded.alias
                            """,
                            (entity.entity_id, alias, _norm(alias)),
                        )
                    if record.chunks:
                        for chunk in record.chunks:
                            connection.execute(
                                """
                                INSERT OR IGNORE INTO entity_sources(entity_id, source_id, chunk_id)
                                VALUES (?, ?, ?)
                                """,
                                (entity.entity_id, record.source_id, chunk.chunk_id),
                            )
                    else:
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO entity_sources(entity_id, source_id, chunk_id)
                            VALUES (?, ?, NULL)
                            """,
                            (entity.entity_id, record.source_id),
                        )
                    if record.authorization_status in {"unknown", "restricted"}:
                        warnings.append(
                            f"source_id={record.source_id} has authorization_status={record.authorization_status}; graph queries filter it by default"
                        )
                    entity_count += 1
                entity_ids = {entity.entity_id for entity in record.entities}
                for relation in record.relations:
                    if relation.subject_id not in entity_ids and not self.entity_exists(connection, relation.subject_id):
                        raise ValueError(f"subject_id does not exist: {relation.subject_id}")
                    if relation.object_id not in entity_ids and not self.entity_exists(connection, relation.object_id):
                        raise ValueError(f"object_id does not exist: {relation.object_id}")
                    status = relation.authorization_status or record.authorization_status
                    if relation.chunk_id:
                        chunk_source = connection.execute(
                            "SELECT source_id FROM chunks WHERE chunk_id = ?", (relation.chunk_id,)
                        ).fetchone()
                        if not chunk_source or chunk_source["source_id"] != record.source_id:
                            raise ValueError(f"chunk_id does not belong to source_id: {relation.chunk_id}")
                    connection.execute(
                        """
                        INSERT INTO relations(relation_id, subject_id, predicate, object_id,
                                              source_id, chunk_id, authorization_status,
                                              metadata_json, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(relation_id) DO UPDATE SET
                            subject_id=excluded.subject_id,
                            predicate=excluded.predicate,
                            object_id=excluded.object_id,
                            source_id=excluded.source_id,
                            chunk_id=excluded.chunk_id,
                            authorization_status=excluded.authorization_status,
                            metadata_json=excluded.metadata_json,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                        (
                            relation.relation_id,
                            relation.subject_id,
                            relation.predicate,
                            relation.object_id,
                            record.source_id,
                            relation.chunk_id,
                            status,
                            _json(relation.metadata),
                        ),
                    )
                    relation_count += 1
            connection.commit()
            return entity_count, relation_count, sorted(set(warnings))
        except Exception:
            connection.rollback()
            raise
        finally:
            if self._memory_connection is None:
                connection.close()

    @staticmethod
    def entity_exists(connection: sqlite3.Connection, entity_id: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM entities WHERE entity_id = ?", (entity_id,)
        ).fetchone() is not None

    def query_entities(
        self,
        *,
        entity_id: str | None = None,
        name: str | None = None,
        alias: str | None = None,
        entity_type: str | None = None,
        authorization_status: list[str] | None = None,
        limit: int = 50,
    ) -> list[EntityResult]:
        allowed = _allowed_statuses(authorization_status)
        if not allowed:
            return []
        connection = self._connect()
        try:
            clauses: list[str] = []
            params: list[Any] = []
            if entity_id:
                clauses.append("e.entity_id = ?")
                params.append(entity_id)
            if name:
                clauses.append("lower(e.canonical_name) = lower(?)")
                params.append(name)
            if alias:
                clauses.append("EXISTS (SELECT 1 FROM entity_aliases ea2 WHERE ea2.entity_id=e.entity_id AND ea2.alias_norm=?)")
                params.append(_norm(alias))
            if entity_type:
                clauses.append("e.entity_type = ?")
                params.append(entity_type)
            clauses.append(
                "EXISTS (SELECT 1 FROM entity_sources es2 JOIN sources s2 ON s2.source_id=es2.source_id "
                f"WHERE es2.entity_id=e.entity_id AND s2.authorization_status IN ({','.join('?' for _ in allowed)}))"
            )
            params.extend(allowed)
            sql = "SELECT e.* FROM entities e WHERE " + " AND ".join(clauses) + " ORDER BY e.entity_id LIMIT ?"
            params.append(limit)
            rows = connection.execute(sql, params).fetchall()
            return [self._entity_result(connection, row, allowed) for row in rows]
        finally:
            if self._memory_connection is None:
                connection.close()

    def get_entity(self, entity_id: str, authorization_status: list[str] | None = None) -> EntityResult | None:
        result = self.query_entities(entity_id=entity_id, authorization_status=authorization_status, limit=1)
        return result[0] if result else None

    def query_relations(
        self,
        *,
        entity_id: str | None = None,
        subject_id: str | None = None,
        object_id: str | None = None,
        predicate: str | None = None,
        authorization_status: list[str] | None = None,
        limit: int = 50,
    ) -> list[RelationResult]:
        allowed = _allowed_statuses(authorization_status)
        if not allowed:
            return []
        connection = self._connect()
        try:
            clauses = [
                f"r.authorization_status IN ({','.join('?' for _ in allowed)})",
                f"s.authorization_status IN ({','.join('?' for _ in allowed)})",
            ]
            params: list[Any] = [*allowed, *allowed]
            if entity_id:
                clauses.append("(r.subject_id = ? OR r.object_id = ?)")
                params.extend([entity_id, entity_id])
            if subject_id:
                clauses.append("r.subject_id = ?")
                params.append(subject_id)
            if object_id:
                clauses.append("r.object_id = ?")
                params.append(object_id)
            if predicate:
                clauses.append("r.predicate = ?")
                params.append(predicate)
            rows = connection.execute(
                "SELECT r.*, s.authorization_status AS current_authorization_status FROM relations r "
                "JOIN sources s ON s.source_id = r.source_id WHERE " + " AND ".join(clauses) + " "
                "ORDER BY r.relation_id LIMIT ?",
                [*params, limit],
            ).fetchall()
            return [self._relation_result(row) for row in rows]
        finally:
            if self._memory_connection is None:
                connection.close()

    def counts(self) -> tuple[int, int]:
        connection = self._connect()
        try:
            entity_count = connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            relation_count = connection.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
            return int(entity_count), int(relation_count)
        finally:
            if self._memory_connection is None:
                connection.close()

    def _entity_result(self, connection: sqlite3.Connection, row: sqlite3.Row, allowed: tuple[str, ...]) -> EntityResult:
        aliases = [item[0] for item in connection.execute(
            "SELECT alias FROM entity_aliases WHERE entity_id = ? ORDER BY alias_norm", (row["entity_id"],)
        ).fetchall()]
        source_rows = connection.execute(
            """
            SELECT es.source_id, es.chunk_id, s.title, s.source_uri, s.authorization_status
            FROM entity_sources es JOIN sources s ON s.source_id = es.source_id
            WHERE es.entity_id = ? AND s.authorization_status IN ({})
            ORDER BY es.source_id, es.chunk_id
            """.format(",".join("?" for _ in allowed)),
            [row["entity_id"], *allowed],
        ).fetchall()
        sources = [SourceRef(
            source_id=item["source_id"], chunk_id=item["chunk_id"], title=item["title"],
            source_uri=item["source_uri"], authorization_status=item["authorization_status"]
        ) for item in source_rows]
        return EntityResult(
            entity_id=row["entity_id"], entity_type=row["entity_type"], canonical_name=row["canonical_name"],
            aliases=aliases, language=row["language"], metadata=_parse_json(row["metadata_json"]), sources=sources
        )

    @staticmethod
    def _relation_result(row: sqlite3.Row) -> RelationResult:
        return RelationResult(
            relation_id=row["relation_id"], subject_id=row["subject_id"], predicate=row["predicate"],
            object_id=row["object_id"], source_id=row["source_id"], chunk_id=row["chunk_id"],
            authorization_status=row["current_authorization_status"] if "current_authorization_status" in row.keys() else row["authorization_status"],
            metadata=_parse_json(row["metadata_json"])
        )


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _allowed_statuses(values: list[str] | None) -> tuple[str, ...]:
    if values is None:
        return VISIBLE_AUTHORIZATION
    requested = tuple(dict.fromkeys(values))
    return tuple(value for value in requested if value in VISIBLE_AUTHORIZATION)
