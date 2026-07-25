from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class InputType(str, Enum):
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    EXHIBIT_ID = "exhibit_id"


class UserInput(ContractModel):
    type: InputType = InputType.TEXT
    text: str | None = Field(default=None, max_length=4000)
    media_url: HttpUrl | None = None
    exhibit_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_payload(self) -> "UserInput":
        required = {
            InputType.TEXT: self.text,
            InputType.AUDIO: self.media_url,
            InputType.IMAGE: self.media_url,
            InputType.EXHIBIT_ID: self.exhibit_id,
        }
        if not required[self.type]:
            raise ValueError(f"input.type={self.type.value} 缺少对应内容")
        return self


class AudienceProfile(ContractModel):
    region: str = Field(default="global", max_length=64)
    age_band: Literal["child", "teen", "adult", "senior", "unspecified"] = "adult"
    knowledge_level: Literal["beginner", "general", "advanced", "expert"] = "general"
    style: Literal["concise", "story", "educational", "academic"] = "educational"


class QueryOptions(ContractModel):
    top_k: int = Field(default=5, ge=1, le=20)
    return_audio: bool = False
    include_graph_context: bool = True
    debug: bool = False


class GuideQueryRequest(ContractModel):
    request_id: str | None = Field(default=None, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    source_language: str = Field(default="auto", max_length=16)
    target_language: str = Field(default="zh-CN", max_length=16)
    input: UserInput
    audience: AudienceProfile = Field(default_factory=AudienceProfile)
    options: QueryOptions = Field(default_factory=QueryOptions)


class Citation(ContractModel):
    citation_id: str
    source_id: str
    title: str
    section: str | None = None
    uri: str | None = None
    excerpt: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)


class PipelineStep(ContractModel):
    module_id: str
    action: str
    status: Literal["ok", "degraded", "skipped", "failed"]
    duration_ms: int = Field(ge=0)


class AudioAsset(ContractModel):
    url: str
    mime_type: str = "audio/mpeg"
    voice: str | None = None


class GuideQueryResponse(ContractModel):
    contract_version: str
    trace_id: str
    request_id: str
    session_id: str
    answer: str
    detected_language: str
    target_language: str
    citations: list[Citation]
    audio: AudioAsset | None = None
    warnings: list[str] = Field(default_factory=list)
    pipeline: list[PipelineStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContentGenerateRequest(ContractModel):
    request_id: str | None = Field(default=None, max_length=128)
    topic: str = Field(min_length=1, max_length=500)
    target_language: str = Field(default="en", max_length=16)
    platform: Literal["short_video", "poster", "social", "event_intro"]
    audience: AudienceProfile = Field(default_factory=AudienceProfile)
    max_length: int = Field(default=500, ge=50, le=5000)


class ContentGenerateResponse(ContractModel):
    contract_version: str
    trace_id: str
    request_id: str
    content: str
    target_language: str
    platform: str
    citations: list[Citation]
    review_required: bool = True
    warnings: list[str] = Field(default_factory=list)


class KnowledgeDocument(ContractModel):
    source_id: str = Field(min_length=1, max_length=128)
    source_uri: str
    media_type: Literal["text", "image", "audio", "video", "document"]
    title: str = Field(min_length=1, max_length=300)
    authorization_status: Literal["authorized", "public", "restricted", "unknown"]
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeIngestRequest(ContractModel):
    request_id: str | None = Field(default=None, max_length=128)
    documents: list[KnowledgeDocument] = Field(min_length=1, max_length=100)
    publish: bool = False


class KnowledgeIngestResponse(ContractModel):
    contract_version: str
    trace_id: str
    request_id: str
    job_id: str
    status: Literal["accepted", "completed", "partial"]
    accepted_count: int
    warnings: list[str] = Field(default_factory=list)


class FeedbackRequest(ContractModel):
    request_id: str | None = Field(default=None, max_length=128)
    trace_id: str
    session_id: str
    rating: Literal["up", "down"] | None = None
    correction: str | None = Field(default=None, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)


class AckResponse(ContractModel):
    contract_version: str
    trace_id: str
    accepted: bool


class ErrorBody(ContractModel):
    code: str
    message: str
    trace_id: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)
