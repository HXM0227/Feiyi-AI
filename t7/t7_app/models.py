from __future__ import annotations

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


class FeedbackRequest(ContractModel):
    request_id: str | None = Field(default=None, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    rating: Literal["up", "down"] | None = None
    correction: str | None = Field(default=None, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_feedback_content(self) -> "FeedbackRequest":
        if not self.rating and not self.correction and not self.tags:
            raise ValueError("反馈至少需要 rating、correction 或 tags 之一")
        return self


class ContentGenerateRequest(ContractModel):
    request_id: str | None = Field(default=None, max_length=128)
    topic: str = Field(min_length=1, max_length=500)
    target_language: str = Field(default="en", max_length=16)
    platform: Literal["short_video", "poster", "social", "event_intro"]
    audience: AudienceProfile = Field(default_factory=AudienceProfile)
    max_length: int = Field(default=500, ge=50, le=5000)


class KnowledgeDocument(ContractModel):
    source_id: str = Field(min_length=1, max_length=128)
    source_uri: str = Field(min_length=1, max_length=2000)
    media_type: Literal["text", "image", "audio", "video", "document"]
    title: str = Field(min_length=1, max_length=300)
    authorization_status: Literal["authorized", "public", "restricted", "unknown"]
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeIngestRequest(ContractModel):
    request_id: str | None = Field(default=None, max_length=128)
    documents: list[KnowledgeDocument] = Field(min_length=1, max_length=100)
    publish: bool = False


class ContentStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ContentUpdateRequest(ContractModel):
    content: str | None = Field(default=None, min_length=1, max_length=10000)
    status: ContentStatus | None = None
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_update(self) -> "ContentUpdateRequest":
        if self.content is None and self.status is None and self.note is None:
            raise ValueError("至少提交 content、status 或 note 之一")
        return self
