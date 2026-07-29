from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextChunk(ContractModel):
    citation_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    section: str | None = Field(default=None, max_length=300)
    uri: str | None = Field(default=None, max_length=2000)
    excerpt: str = Field(min_length=1, max_length=6000)
    score: float | None = Field(default=None, ge=0, le=1)


class GenerationRequest(ContractModel):
    query: str = Field(min_length=1, max_length=4000)
    detected_language: str = Field(default="auto", max_length=16)
    target_language: str = Field(default="en", max_length=16)
    audience: dict[str, Any] = Field(default_factory=dict)
    context: list[ContextChunk] = Field(min_length=1, max_length=20)
    graph_context: dict[str, Any] | None = None
    adaptation: dict[str, Any] | None = None
    requirements: dict[str, Any] = Field(default_factory=dict)

    @field_validator("target_language")
    @classmethod
    def canonical_target(cls, value: str) -> str:
        normalized = value.strip().lower()
        aliases = {"zh": "zh-CN", "zh-cn": "zh-CN", "en": "en", "en-us": "en", "en-gb": "en"}
        if normalized not in aliases:
            raise ValueError("首期仅支持 zh-CN 与 en")
        return aliases[normalized]


class TerminologyCheck(ContractModel):
    passed: bool
    applicable_terms: list[str] = Field(default_factory=list)
    missing_terms: list[str] = Field(default_factory=list)


class GenerationResponse(ContractModel):
    answer: str
    used_citation_ids: list[str]
    detected_language: str
    target_language: str
    terminology_check: TerminologyCheck
    prompt_version: str
    generator_mode: Literal["mock", "qwen", "fallback_mock"]
    warnings: list[str] = Field(default_factory=list)
    fallback_used: bool = False


class HealthResponse(ContractModel):
    status: Literal["ok", "not_ready"]
    mode: str
