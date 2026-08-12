from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from .schemas import AdaptationRequest, AdaptationResponse


class PolicyLoadError(ValueError):
    """Raised when the versioned policy document cannot be loaded safely."""


class PolicyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str
    base_instructions: list[str]
    target_language: dict[str, str]
    age_band: dict[str, str]
    knowledge_level: dict[str, str]
    style: dict[str, str]
    region: dict[str, str]
    blocked_terms: dict[str, list[str]]

    @model_validator(mode="after")
    def required_rule_keys(self) -> "PolicyDocument":
        required = {
            "target_language": {"zh-CN", "en"},
            "age_band": {"child", "teen", "adult", "senior", "unspecified"},
            "knowledge_level": {"beginner", "general", "advanced", "expert"},
            "style": {"concise", "story", "educational", "academic"},
            "region": {"global", "specified"},
            "blocked_terms": {"zh-CN", "en"},
        }
        for field_name, expected in required.items():
            actual = set(getattr(self, field_name))
            missing = expected - actual
            if missing:
                raise ValueError(f"{field_name} missing policy keys: {sorted(missing)}")
            unexpected = actual - expected
            if unexpected:
                raise ValueError(
                    f"{field_name} has unknown policy keys: {sorted(unexpected)}"
                )
        if not self.policy_version.strip() or not self.base_instructions:
            raise ValueError("policy_version and base_instructions must not be empty")

        instruction_groups = [
            self.base_instructions,
            *(
                list(getattr(self, field_name).values())
                for field_name in (
                    "target_language",
                    "age_band",
                    "knowledge_level",
                    "style",
                    "region",
                )
            ),
        ]
        for instructions in instruction_groups:
            if any(not instruction.strip() for instruction in instructions):
                raise ValueError("policy instructions must not be blank")

        for language, terms in self.blocked_terms.items():
            normalized = [term.strip().casefold() for term in terms]
            if not normalized or any(not term for term in normalized):
                raise ValueError(f"blocked_terms[{language}] must not be empty")
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"blocked_terms[{language}] contains duplicates")
        return self


def load_policy(path: Path) -> PolicyDocument:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return PolicyDocument.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise PolicyLoadError(f"无法加载 T5 策略文件：{path}") from exc


class AdaptationService:
    def __init__(self, policy: PolicyDocument) -> None:
        self.policy = policy

    @classmethod
    def from_path(cls, path: Path) -> "AdaptationService":
        return cls(load_policy(path))

    def adapt(self, request: AdaptationRequest) -> AdaptationResponse:
        instructions: list[str] = []
        for instruction in self.policy.base_instructions:
            self._append_unique(instructions, instruction)

        audience = request.audience
        selected = [
            self.policy.target_language[request.target_language],
            self.policy.age_band[audience.age_band],
            self.policy.knowledge_level[audience.knowledge_level],
            self.policy.style[audience.style],
            self.policy.region[
                "global" if audience.region.casefold() == "global" else "specified"
            ],
        ]
        for instruction in selected:
            self._append_unique(instructions, instruction)

        blocked_terms = list(self.policy.blocked_terms[request.target_language])
        blocked_instruction = (
            "避免采用这些容易造成贬损或刻板印象的表达："
            + "、".join(blocked_terms)
            + "。如资料原文出现，应明确说明它是被引用或被讨论的表述，而不是采用该观点。"
        )
        self._append_unique(instructions, blocked_instruction)

        return AdaptationResponse(
            policy_version=self.policy.policy_version,
            instructions=instructions,
            blocked_terms=blocked_terms,
        )

    @staticmethod
    def _append_unique(items: list[str], value: str) -> None:
        normalized = value.strip()
        if normalized and normalized not in items:
            items.append(normalized)
