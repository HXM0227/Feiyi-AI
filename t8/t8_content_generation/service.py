from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .schemas import ContentGenerationRequest, ContentGenerationResponse
from .templates import PlatformTemplates


CITATION_RE = re.compile(r"\[([A-Za-z0-9_-]+)\]")


class ContentGenerationError(Exception):
    """Safe error that can be returned to an API caller."""


def detect_language(text: str) -> str:
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if chinese > latin * 0.25:
        return "zh-CN"
    if latin:
        return "en"
    return "unknown"


def fit_with_citation(text: str, citation_id: str, max_length: int) -> str:
    """Fit Unicode text without ever cutting the required citation marker."""
    marker = f"[{citation_id}]"
    text_without_marker = text.replace(marker, "").strip()
    separator = " " if text_without_marker else ""
    budget = max_length - len(marker) - len(separator)
    if budget < 1:
        raise ContentGenerationError("max_length is too small for a citation")
    if len(text_without_marker) > budget:
        ellipsis = "…"
        if budget <= len(ellipsis):
            text_without_marker = text_without_marker[:budget]
        else:
            take = budget - len(ellipsis)
            text_without_marker = text_without_marker[:take].rstrip() + ellipsis
    return f"{text_without_marker}{separator}{marker}"


class MockGenerator:
    def __init__(self, templates: PlatformTemplates) -> None:
        self.templates = templates

    async def generate(self, request: ContentGenerationRequest) -> str:
        source_language = detect_language(request.context[0].excerpt)
        if source_language not in {"unknown", request.target_language}:
            if request.target_language == "en":
                draft = (
                    "Source-backed material is available for this topic, but the offline draft "
                    "cannot translate it safely. Human translation and review are required before publication. "
                    f"[{request.context[0].citation_id}]"
                )
            else:
                draft = (
                    "该主题已有可引用资料，但离线草稿无法安全完成跨语言转换。"
                    "发布前必须完成人工翻译与审核。"
                    f"[{request.context[0].citation_id}]"
                )
        else:
            draft = self.templates.render(request)
        return fit_with_citation(
            draft,
            request.context[0].citation_id,
            request.max_length,
        )


class QwenGenerator:
    def __init__(self, settings: Settings, template_version: str) -> None:
        self.settings = settings
        self.template_version = template_version

    async def generate(self, request: ContentGenerationRequest) -> str:
        if not self.settings.qwen_api_key:
            raise ContentGenerationError("T8_MODE=qwen requires DASHSCOPE_API_KEY")
        system = (
            "You are T8, a bilingual cultural-heritage communication content service. "
            "Write only in the requested target language. Use only the supplied context for factual claims. "
            "Include citation IDs exactly in [CIT-ID] form next to supported claims. "
            "Never invent a citation or fact. Respect the Unicode character limit, including citations. "
            "Return content text only; do not return JSON or commentary. Human review remains mandatory."
        )
        user = json.dumps(
            {
                "topic": request.topic,
                "target_language": request.target_language,
                "platform": request.platform,
                "audience": request.audience.model_dump(mode="json"),
                "max_unicode_characters": request.max_length,
                "template_version": self.template_version,
                "context": [item.model_dump(mode="json") for item in request.context],
            },
            ensure_ascii=False,
        )
        payload = {
            "model": self.settings.qwen_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.settings.qwen_temperature,
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.qwen_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.qwen_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.qwen_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ContentGenerationError("Qwen returned empty content")
            return content.strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ContentGenerationError(
                f"Qwen invocation failed: {type(exc).__name__}"
            ) from exc


class AuditWriter:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def write(
        self,
        request: ContentGenerationRequest,
        response: ContentGenerationResponse,
    ) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "template_version": response.template_version,
            "generator_mode": response.generator_mode,
            "fallback_used": response.fallback_used,
            "topic": request.topic[:500],
            "target_language": request.target_language,
            "platform": request.platform,
            "max_length": request.max_length,
            "content_length": response.length,
            "source_ids": [item.source_id for item in request.context],
            "used_citation_ids": response.used_citation_ids,
            "review_required": response.review_required,
        }
        path = self.directory / "content_generation_audit.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class ContentGenerationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.templates = PlatformTemplates(settings.template_path)
        self.mock = MockGenerator(self.templates)
        self.qwen = QwenGenerator(settings, self.templates.version)
        self.audit = AuditWriter(settings.audit_dir)

    def ready(self) -> bool:
        return self.settings.mode == "mock" or bool(self.settings.qwen_api_key)

    async def generate(
        self, request: ContentGenerationRequest
    ) -> ContentGenerationResponse:
        warnings: list[str] = []
        fallback_used = False
        mode = self.settings.mode
        try:
            content = await (
                self.qwen.generate(request)
                if mode == "qwen"
                else self.mock.generate(request)
            )
            used = self._validate_output(content, request)
            if mode == "qwen":
                self._validate_language(content, request.target_language)
        except ContentGenerationError as exc:
            if mode != "qwen":
                raise
            content = await self.mock.generate(request)
            used = self._validate_output(content, request)
            mode = "fallback_mock"
            fallback_used = True
            warnings.append(f"千问调用或输出校验失败，已使用有据模板降级：{exc}")

        if mode in {"mock", "fallback_mock"}:
            source_languages = {detect_language(item.excerpt) for item in request.context}
            source_languages.discard("unknown")
            if source_languages and request.target_language not in source_languages:
                warnings.append(
                    "确定性模板未执行跨语言翻译，已返回目标语言的待人工翻译提示"
                )

        response = ContentGenerationResponse(
            content=content,
            used_citation_ids=used,
            review_required=True,
            target_language=request.target_language,
            platform=request.platform,
            template_version=self.templates.version,
            generator_mode=mode,  # type: ignore[arg-type]
            warnings=warnings,
            fallback_used=fallback_used,
            length=len(content),
        )
        self.audit.write(request, response)
        return response

    @staticmethod
    def _validate_output(
        content: str, request: ContentGenerationRequest
    ) -> list[str]:
        if not content.strip():
            raise ContentGenerationError("generated content is empty")
        if len(content) > request.max_length:
            raise ContentGenerationError(
                f"generated content exceeds max_length: {len(content)} > {request.max_length}"
            )
        allowed = {item.citation_id for item in request.context}
        used = CITATION_RE.findall(content)
        if not used:
            raise ContentGenerationError("generated content has no source citation")
        unknown = set(used) - allowed
        if unknown:
            raise ContentGenerationError(
                f"generated content used unknown citation IDs: {sorted(unknown)}"
            )
        return list(dict.fromkeys(used))

    @staticmethod
    def _validate_language(content: str, target_language: str) -> None:
        detected = detect_language(content)
        if detected != target_language:
            raise ContentGenerationError(
                f"generated content language mismatch: expected {target_language}, got {detected}"
            )
