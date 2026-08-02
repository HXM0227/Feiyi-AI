from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


AuthorizationStatus = Literal["authorized", "public", "restricted", "unknown"]


class ChunkInput(ContractModel):
    chunk_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1)
    sequence: int = Field(default=1, ge=1)
    section: str | None = None
    language: str | None = None

    @field_validator("text")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class IndexRecord(ContractModel):
    source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    source_uri: str = Field(min_length=1)
    media_type: Literal["text", "image", "audio", "video", "document"]
    authorization_status: AuthorizationStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunks: list[ChunkInput] = Field(default_factory=list)

    @field_validator("source_id", "title", "source_uri")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class UpsertRequest(ContractModel):
    records: list[IndexRecord] = Field(default_factory=list, max_length=1000)
    publish: bool = False


class UpsertResponse(ContractModel):
    contract_version: str
    status: Literal["completed"] = "completed"
    accepted_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class RetrieveFilters(ContractModel):
    authorization_status: list[AuthorizationStatus] | None = None


class RetrieveRequest(ContractModel):
    query: str = Field(min_length=1, max_length=1000)
    language: str | None = Field(default=None, max_length=32)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: RetrieveFilters | None = None

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class Citation(ContractModel):
    citation_id: str
    source_id: str
    title: str
    section: str | None = None
    uri: str | None = None
    excerpt: str
    score: float = Field(ge=0, le=1)


class RetrieveResponse(ContractModel):
    chunks: list[Citation] = Field(default_factory=list)


class ErrorBody(ContractModel):
    code: str
    message: str
    trace_id: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
