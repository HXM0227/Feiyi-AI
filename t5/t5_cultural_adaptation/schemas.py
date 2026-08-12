from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AudienceProfile(ContractModel):
    region: str = Field(default="global", min_length=1, max_length=64)
    age_band: Literal["child", "teen", "adult", "senior", "unspecified"] = "adult"
    knowledge_level: Literal["beginner", "general", "advanced", "expert"] = "general"
    style: Literal["concise", "story", "educational", "academic"] = "educational"

    @field_validator("region")
    @classmethod
    def non_blank_region(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("region must not be blank")
        return value


class RetrievalContextItem(ContractModel):
    citation_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    section: str | None = Field(default=None, max_length=300)
    uri: str | None = Field(default=None, max_length=2000)
    excerpt: str | None = Field(default=None, max_length=6000)
    score: float | None = Field(default=None, ge=0, le=1)

    @field_validator("citation_id", "source_id", "title")
    @classmethod
    def non_blank_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("citation identity fields must not be blank")
        return value


class AdaptationRequest(ContractModel):
    query: str = Field(min_length=1, max_length=4000)
    target_language: str = Field(default="zh-CN", max_length=16)
    audience: AudienceProfile = Field(default_factory=AudienceProfile)
    graph_context: dict[str, Any] = Field(default_factory=dict)
    retrieval_context: list[RetrievalContextItem] = Field(min_length=1, max_length=20)

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value

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


class AdaptationResponse(ContractModel):
    policy_version: str
    instructions: list[str] = Field(min_length=1)
    blocked_terms: list[str] = Field(default_factory=list)


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"
    contract_version: str
    policy_version: str
