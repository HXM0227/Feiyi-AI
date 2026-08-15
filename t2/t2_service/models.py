from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AuthorizationStatus = Literal["authorized", "public", "restricted", "unknown"]
EntityType = Literal["craft", "person", "place", "tool", "symbol", "process", "concept"]
Predicate = Literal[
    "belongs_to",
    "related_to",
    "uses",
    "practiced_in",
    "includes",
    "has_symbol",
    "has_process",
    "has_tool",
    "adapted_for",
    "example_of",
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class ChunkInput(ContractModel):
    chunk_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1)
    sequence: int = Field(default=1, ge=1)
    section: str | None = Field(default=None, max_length=300)
    language: str | None = Field(default=None, max_length=32)

    _validate_text = field_validator("chunk_id", "text")(_non_blank)


class EntityInput(ContractModel):
    entity_id: str = Field(min_length=1, max_length=256)
    entity_type: EntityType
    canonical_name: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    language: str | None = Field(default=None, max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)

    _validate_text = field_validator("entity_id", "canonical_name")(_non_blank)

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            value = _non_blank(value)
            if value not in cleaned:
                cleaned.append(value)
        return cleaned


class RelationInput(ContractModel):
    relation_id: str = Field(min_length=1, max_length=256)
    subject_id: str = Field(min_length=1, max_length=256)
    predicate: Predicate
    object_id: str = Field(min_length=1, max_length=256)
    source_id: str | None = Field(default=None, max_length=128)
    chunk_id: str | None = Field(default=None, max_length=256)
    authorization_status: AuthorizationStatus | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    _validate_text = field_validator("relation_id", "subject_id", "object_id")(_non_blank)


class GraphRecord(ContractModel):
    source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    source_uri: str = Field(min_length=1, max_length=4096)
    media_type: Literal["text", "image", "audio", "video", "document"] = "text"
    authorization_status: AuthorizationStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunks: list[ChunkInput] = Field(default_factory=list, max_length=5000)
    entities: list[EntityInput] = Field(default_factory=list, max_length=1000)
    relations: list[RelationInput] = Field(default_factory=list, max_length=2000)

    _validate_text = field_validator("source_id", "title", "source_uri")(_non_blank)

    @model_validator(mode="after")
    def validate_relations(self) -> "GraphRecord":
        chunk_ids = {chunk.chunk_id for chunk in self.chunks}
        for relation in self.relations:
            if relation.source_id and relation.source_id != self.source_id:
                raise ValueError("relation source_id must match record source_id")
            if relation.chunk_id and relation.chunk_id not in chunk_ids:
                raise ValueError("relation chunk_id must reference a record chunk")
        return self


class UpsertRequest(ContractModel):
    records: list[GraphRecord] = Field(min_length=1, max_length=1000)
    publish: bool = False


class UpsertResponse(ContractModel):
    contract_version: str
    module: str = "T2"
    status: Literal["completed"] = "completed"
    accepted_count: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    relation_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class AuthorizationFilter(ContractModel):
    authorization_status: list[AuthorizationStatus] | None = None


class GraphQueryRequest(ContractModel):
    entity_id: str | None = Field(default=None, max_length=256)
    name: str | None = Field(default=None, max_length=300)
    alias: str | None = Field(default=None, max_length=300)
    entity_type: EntityType | None = None
    predicate: Predicate | None = None
    include_relations: bool = True
    filters: AuthorizationFilter | None = None
    limit: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def validate_query(self) -> "GraphQueryRequest":
        if not any((self.entity_id, self.name, self.alias, self.predicate)):
            raise ValueError("at least one query condition is required")
        for field_name in ("entity_id", "name", "alias"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(f"{field_name} must not be blank")
        return self


class SourceRef(ContractModel):
    source_id: str
    chunk_id: str | None = None
    title: str | None = None
    source_uri: str | None = None
    authorization_status: AuthorizationStatus


class EntityResult(ContractModel):
    entity_id: str
    entity_type: EntityType
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceRef] = Field(default_factory=list)


class RelationResult(ContractModel):
    relation_id: str
    subject_id: str
    predicate: Predicate
    object_id: str
    source_id: str
    chunk_id: str | None = None
    authorization_status: AuthorizationStatus
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphQueryResponse(ContractModel):
    contract_version: str
    module: str = "T2"
    entities: list[EntityResult] = Field(default_factory=list)
    relations: list[RelationResult] = Field(default_factory=list)


class EntityDetailResponse(ContractModel):
    contract_version: str
    module: str = "T2"
    entity: EntityResult | None = None
    relations: list[RelationResult] = Field(default_factory=list)


class ErrorBody(ContractModel):
    code: str
    message: str
    trace_id: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
