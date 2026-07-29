from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .schemas import GenerationRequest, GenerationResponse, TerminologyCheck

PROMPT_VERSION = "t4-grounded-bilingual-1.0"
CITATION_RE = re.compile(r"\[([A-Za-z0-9_-]+)\]")


class GenerationError(Exception):
    """A safe, user-facing generation error."""


class Terminology:
    def __init__(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.version = payload["version"]
        self.terms: list[dict[str, Any]] = payload["terms"]

    def applicable(self, request: GenerationRequest) -> list[dict[str, Any]]:
        text = request.query + "\n" + "\n".join(chunk.excerpt for chunk in request.context)
        return [item for item in self.terms if item["zh"] in text or item["en"].lower() in text.lower()]

    def check(self, answer: str, request: GenerationRequest) -> TerminologyCheck:
        applicable = self.applicable(request)
        missing: list[str] = []
        for item in applicable:
            expected = item["en"] if request.target_language == "en" else item["zh"]
            if expected.lower() not in answer.lower():
                missing.append(expected)
        return TerminologyCheck(
            passed=not missing,
            applicable_terms=[item["en"] if request.target_language == "en" else item["zh"] for item in applicable],
            missing_terms=missing,
        )


def detect_language(text: str) -> str:
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if chinese > latin * 0.15:
        return "zh-CN"
    if latin:
        return "en"
    return "unknown"


class MockGenerator:
    async def generate(self, request: GenerationRequest, terms: list[dict[str, Any]]) -> str:
        citations = " ".join(f"[{chunk.citation_id}]" for chunk in request.context)
        excerpt = request.context[0].excerpt.strip()
        term_text = "; ".join(
            f"{term['en']}" if request.target_language == "en" else term["zh"]
            for term in terms
        ) or ("intangible cultural heritage" if request.target_language == "en" else "非物质文化遗产")
        if request.target_language == "en":
            return (
                f"Based on the supplied sources, {term_text} can be explained through this point: {excerpt} "
                f"This is a factual, source-grounded explanation. A comparison used to help understanding is only an analogy, not a historical fact. {citations}"
            )
        return (
            f"依据提供的资料，{term_text}可从以下内容理解：{excerpt}"
            f"以上为有来源支撑的事实性说明；如使用帮助理解的类比，应明确它只是类比而非史实。{citations}"
        )


class QwenGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, request: GenerationRequest, terms: list[dict[str, Any]]) -> str:
        if not self.settings.qwen_api_key:
            raise GenerationError("T4_MODE=qwen requires DASHSCOPE_API_KEY")
        context = [chunk.model_dump() for chunk in request.context]
        glossary = [{"zh": term["zh"], "en": term["en"], "note": term["note"]} for term in terms]
        instructions = (request.adaptation or {}).get("instructions", [])
        constraints = (request.graph_context or {}).get("constraints", [])
        system = (
            "You are T4, a bilingual Chinese-English museum interpretation service. "
            "Use only supplied context for factual claims. Every factual explanation must include supplied citation IDs in [CIT-ID] form. "
            "Keep terminology exactly as the glossary specifies; if an English proper name preserves Chinese, include it at first mention. "
            "Clearly label any analogy as an analogy, never as fact. Return only the answer text."
        )
        user = json.dumps({
            "target_language": request.target_language,
            "question": request.query,
            "audience": request.audience,
            "adaptation_instructions": instructions,
            "graph_constraints": constraints,
            "glossary": glossary,
            "context": context,
        }, ensure_ascii=False)
        payload = {
            "model": self.settings.qwen_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
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
            answer = data["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise GenerationError("Qwen returned an empty answer")
            return answer.strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise GenerationError(f"Qwen invocation failed: {type(exc).__name__}") from exc


class AuditWriter:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def write(self, request: GenerationRequest, response: GenerationResponse) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt_version": response.prompt_version,
            "mode": response.generator_mode,
            "fallback_used": response.fallback_used,
            "query": request.query[:500],
            "target_language": request.target_language,
            "context": [{"citation_id": item.citation_id, "source_id": item.source_id, "excerpt": item.excerpt[:500]} for item in request.context],
            "used_citation_ids": response.used_citation_ids,
            "terminology_check": response.terminology_check.model_dump(),
        }
        with (self.directory / "generation_audit.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class GenerationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.terminology = Terminology(settings.terminology_path)
        self.mock = MockGenerator()
        self.qwen = QwenGenerator(settings)
        self.audit = AuditWriter(settings.audit_dir)

    def ready(self) -> bool:
        return self.settings.mode == "mock" or bool(self.settings.qwen_api_key)

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        detected = detect_language(request.query) if request.detected_language == "auto" else request.detected_language
        terms = self.terminology.applicable(request)
        warnings: list[str] = []
        fallback = False
        mode = self.settings.mode
        try:
            answer = await (self.qwen.generate(request, terms) if mode == "qwen" else self.mock.generate(request, terms))
            used = self._validate_citations(answer, request)
            check = self.terminology.check(answer, request)
            if not check.passed:
                raise GenerationError("terminology validation failed")
        except GenerationError as exc:
            if mode != "qwen":
                raise
            answer = await self.mock.generate(request, terms)
            used = self._validate_citations(answer, request)
            check = self.terminology.check(answer, request)
            mode, fallback = "fallback_mock", True
            warnings.append(f"千问调用或输出校验失败，已使用受限 Mock 降级：{exc}")
        response = GenerationResponse(
            answer=answer,
            used_citation_ids=used,
            detected_language=detected,
            target_language=request.target_language,
            terminology_check=check,
            prompt_version=PROMPT_VERSION,
            generator_mode=mode,  # type: ignore[arg-type]
            warnings=warnings,
            fallback_used=fallback,
        )
        self.audit.write(request, response)
        return response

    @staticmethod
    def _validate_citations(answer: str, request: GenerationRequest) -> list[str]:
        allowed = {chunk.citation_id for chunk in request.context}
        used = CITATION_RE.findall(answer)
        if not used:
            raise GenerationError("answer has no source citation")
        unknown = set(used) - allowed
        if unknown:
            raise GenerationError(f"answer used unknown citation IDs: {sorted(unknown)}")
        return list(dict.fromkeys(used))
