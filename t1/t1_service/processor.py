from __future__ import annotations

from typing import Any

from .models import KnowledgeDocument, NormalizedRecord, RejectedDocument
from .chunker import chunk_text
from .normalizer import normalize_text


_PASSTHROUGH_METADATA = {
    "language",
    "version",
    "reviewer",
    "reviewed_at",
    "section",
    "audience",
    "scenario",
    "difficulty",
}


def normalize_document(
    document: KnowledgeDocument,
    *,
    max_chunk_chars: int,
    chunk_overlap: int,
    publish: bool = False,
) -> tuple[NormalizedRecord | None, RejectedDocument | None, str | None, str | None]:
    metadata = dict(document.metadata)
    raw_text = metadata.get("text")
    if raw_text is not None and not isinstance(raw_text, str):
        return None, RejectedDocument(
            source_id=document.source_id,
            title=document.title,
            code="VALIDATION_ERROR",
            message="metadata.text must be a string",
        ), None, None

    if document.media_type not in {"text", "document"}:
        if not raw_text or not raw_text.strip():
            return None, RejectedDocument(
                source_id=document.source_id,
                title=document.title,
                code="UNSUPPORTED_MEDIA_FOR_MVP",
                message=f"media_type={document.media_type} requires pre-extracted metadata.text",
            ), None, None

    if not raw_text or not raw_text.strip():
        return None, RejectedDocument(
            source_id=document.source_id,
            title=document.title,
            code="MISSING_TEXT",
            message="metadata.text is required for T1 MVP normalization",
        ), None, None

    cleaned = normalize_text(raw_text)
    chunks = chunk_text(cleaned, max_chars=max_chunk_chars, overlap=chunk_overlap)
    if not chunks:
        return None, RejectedDocument(
            source_id=document.source_id,
            title=document.title,
            code="EMPTY_TEXT",
            message="metadata.text is empty after normalization",
        ), None, None

    language = _optional_string(metadata.get("language"))
    section = _optional_string(metadata.get("section"))
    chunk_models = [
        {
            "chunk_id": f"{document.source_id}-{index:04d}",
            "text": value,
            "sequence": index,
            "section": section,
            "language": language,
        }
        for index, value in enumerate(chunks, start=1)
    ]
    output_metadata = {
        key: value for key, value in metadata.items() if key in _PASSTHROUGH_METADATA and key != "text"
    }
    record = NormalizedRecord(
        source_id=document.source_id,
        title=document.title,
        source_uri=document.source_uri,
        media_type=document.media_type,
        authorization_status=document.authorization_status,
        metadata=output_metadata,
        chunks=chunk_models,
    )
    warning_parts: list[str] = []
    if document.authorization_status in {"restricted", "unknown"}:
        warning_parts.append(
            f"source_id={document.source_id} has authorization_status="
            f"{document.authorization_status}; downstream retrieval must filter it"
        )
        if publish:
            warning_parts.append("publish=true does not change authorization_status")
    return record, None, cleaned, " | ".join(warning_parts) or None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
