from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AudienceProfile(ContractModel):
    region: str = Field(default="global", max_length=64)
    age_band: Literal["child", "teen", "adult", "senior", "unspecified"] = "adult"
    knowledge_level: Literal["beginner", "general", "advanced", "expert"] = "general"
    style: Literal["concise", "story", "educational", "academic"] = "educational"


class ContextChunk(ContractModel):
    citation_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    section: str | None = Field(default=None, max_length=300)
    uri: str | None = Field(default=None, max_length=2000)
    excerpt: str = Field(min_length=1, max_length=6000)
    score: float | None = Field(default=None, ge=0, le=1)


class GenerationRequirements(ContractModel):
    human_review: Literal[True] = True
    preserve_citations: Literal[True] = True


class ContentGenerationRequest(ContractModel):
    topic: str = Field(min_length=1, max_length=500)
    target_language: str = Field(default="en", max_length=16)
    platform: Literal["short_video", "poster", "social", "event_intro"]
    audience: AudienceProfile = Field(default_factory=AudienceProfile)
    max_length: int = Field(default=500, ge=50, le=5000)
    context: list[ContextChunk] = Field(min_length=1, max_length=20)
    requirements: GenerationRequirements = Field(default_factory=GenerationRequirements)

    @field_validator("target_language")
    @classmethod
    def canonical_target_language(cls, value: str) -> str:
        normalized = value.strip().lower()
        aliases = {
            "zh": "zh-CN",
            "zh-cn": "zh-CN",
            "en": "en",
            "en-us": "en",
            "en-gb": "en",
        }
        if normalized not in aliases:
            raise ValueError("首期仅支持 zh-CN 与 en")
        return aliases[normalized]


class ContentGenerationResponse(ContractModel):
    content: str
    used_citation_ids: list[str]
    review_required: Literal[True] = True
    target_language: str
    platform: str
    template_version: str
    generator_mode: Literal["mock", "qwen", "fallback_mock"]
    warnings: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    length: int = Field(ge=1)


class HealthResponse(ContractModel):
    status: Literal["ok", "not_ready"]
    mode: str


class ErrorResponse(ContractModel):
    code: str
    message: str
    details: Any | None = None
