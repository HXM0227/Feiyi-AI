from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=False)


MediaType = Literal["text", "image", "audio", "video", "document"]
AuthorizationStatus = Literal["authorized", "public", "restricted", "unknown"]


class KnowledgeDocument(ContractModel):
    source_id: str = Field(min_length=1, max_length=128)
    source_uri: str = Field(min_length=1, max_length=4096)
    media_type: MediaType
    title: str = Field(min_length=1, max_length=300)
    authorization_status: AuthorizationStatus
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_id", "source_uri", "title")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class NormalizeRequest(ContractModel):
    documents: list[KnowledgeDocument] = Field(min_length=1, max_length=100)
    publish: bool = False


class Chunk(ContractModel):
    chunk_id: str
    text: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    section: str | None = None
    language: str | None = None


class NormalizedRecord(ContractModel):
    source_id: str
    title: str
    source_uri: str
    media_type: MediaType
    authorization_status: AuthorizationStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunks: list[Chunk] = Field(default_factory=list)


class RejectedDocument(ContractModel):
    source_id: str
    title: str
    code: str
    message: str


class NormalizeResponse(ContractModel):
    records: list[NormalizedRecord]
    rejected: list[RejectedDocument] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ErrorBody(ContractModel):
    code: str
    message: str
    trace_id: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
