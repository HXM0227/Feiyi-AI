from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from .config import Settings
from .errors import ModuleCallError, T0Error
from .models import (
    AckResponse,
    AudioAsset,
    Citation,
    ContentGenerateRequest,
    ContentGenerateResponse,
    FeedbackRequest,
    GuideQueryRequest,
    GuideQueryResponse,
    KnowledgeIngestRequest,
    KnowledgeIngestResponse,
    PipelineStep,
)
from .registry import ModuleRegistry


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    value: Any


@dataclass(slots=True)
class Orchestrator:
    settings: Settings
    registry: ModuleRegistry
    _idempotency_cache: dict[str, _CacheEntry] = field(default_factory=dict)

    @staticmethod
    def _ids(request_id: str | None) -> tuple[str, str]:
        return request_id or str(uuid.uuid4()), str(uuid.uuid4())

    async def _timed_call(
        self,
        module_id: str,
        path: str,
        payload: dict[str, Any],
        *,
        trace_id: str,
        request_id: str,
        action: str,
        pipeline: list[PipelineStep] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = await self.registry.get(module_id).call(
                path, payload, trace_id=trace_id, request_id=request_id
            )
        except Exception:
            if pipeline is not None:
                pipeline.append(
                    PipelineStep(
                        module_id=module_id,
                        action=action,
                        status="failed",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
            raise
        if pipeline is not None:
            pipeline.append(
                PipelineStep(
                    module_id=module_id,
                    action=action,
                    status="ok",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
        return result

    @staticmethod
    def _mark_degraded(
        pipeline: list[PipelineStep], module_id: str, action: str
    ) -> None:
        for step in reversed(pipeline):
            if step.module_id == module_id and step.action == action:
                step.status = "degraded"
                return

    async def guide_query(
        self, request: GuideQueryRequest, *, idempotency_key: str | None = None
    ) -> GuideQueryResponse:
        cache_key = (
            f"guide:{request.session_id}:{idempotency_key}" if idempotency_key else None
        )
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached:
                return cached

        request_id, trace_id = self._ids(request.request_id)
        pipeline: list[PipelineStep] = []
        warnings: list[str] = []

        normalized = await self._timed_call(
            "T6",
            "/v1/input/normalize",
            {
                "input": request.input.model_dump(mode="json"),
                "source_language": request.source_language,
            },
            trace_id=trace_id,
            request_id=request_id,
            action="normalize_input",
            pipeline=pipeline,
        )
        query = normalized.get("query")
        if not isinstance(query, str) or not query.strip():
            raise T0Error(
                code="INVALID_MODULE_RESPONSE",
                message="T6 未返回 query",
                status_code=502,
                details={"module_id": "T6"},
            )

        retrieval_task = asyncio.create_task(
            self._timed_call(
                "T3",
                "/v1/retrieve",
                {
                    "query": query,
                    "language": normalized.get("detected_language", request.source_language),
                    "top_k": request.options.top_k,
                    "filters": {"authorization_status": ["authorized", "public"]},
                },
                trace_id=trace_id,
                request_id=request_id,
                action="retrieve",
                pipeline=pipeline,
            )
        )
        graph_task = None
        if request.options.include_graph_context:
            graph_task = asyncio.create_task(
                self._timed_call(
                    "T2",
                    "/v1/graph/context",
                    {"query": query, "exhibit_id": request.input.exhibit_id},
                    trace_id=trace_id,
                    request_id=request_id,
                    action="graph_context",
                    pipeline=pipeline,
                )
            )

        try:
            retrieval = await retrieval_task
        except Exception:
            if graph_task:
                graph_task.cancel()
                await asyncio.gather(graph_task, return_exceptions=True)
            raise
        graph: dict[str, Any] = {}
        if graph_task:
            try:
                graph = await graph_task
            except ModuleCallError:
                warnings.append("T2 知识图谱暂不可用，已退化为仅使用 T3 检索上下文。")
                self._mark_degraded(pipeline, "T2", "graph_context")

        chunks = retrieval.get("chunks", [])
        if not isinstance(chunks, list):
            raise T0Error(
                code="INVALID_MODULE_RESPONSE",
                message="T3 返回的 chunks 必须是数组",
                status_code=502,
                details={"module_id": "T3"},
            )
        if not chunks:
            raise T0Error(
                code="NO_GROUNDED_CONTEXT",
                message="未检索到可引用的知识片段，系统拒绝无依据生成",
                status_code=422,
                retryable=False,
            )
        citations = self._validate_citations(chunks)

        try:
            adaptation = await self._timed_call(
                "T5",
                "/v1/adapt",
                {
                    "query": query,
                    "target_language": request.target_language,
                    "audience": request.audience.model_dump(mode="json"),
                    "graph_context": graph,
                    "retrieval_context": chunks,
                },
                trace_id=trace_id,
                request_id=request_id,
                action="adapt",
                pipeline=pipeline,
            )
        except ModuleCallError:
            adaptation = {
                "policy_version": "t0-safe-default",
                "instructions": ["只陈述检索上下文支持的事实", "文化类比必须标明为类比"],
            }
            warnings.append("T5 跨文化适配暂不可用，已使用 T0 安全默认策略。")
            self._mark_degraded(pipeline, "T5", "adapt")

        generated = await self._timed_call(
            "T4",
            "/v1/generate",
            {
                "query": query,
                "detected_language": normalized.get("detected_language", "unknown"),
                "target_language": request.target_language,
                "audience": request.audience.model_dump(mode="json"),
                "context": chunks,
                "graph_context": graph,
                "adaptation": adaptation,
                "requirements": {
                    "citation_format": "[citation_id]",
                    "must_use_context": True,
                    "separate_fact_and_analogy": True,
                },
            },
            trace_id=trace_id,
            request_id=request_id,
            action="generate",
            pipeline=pipeline,
        )
        answer = generated.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise T0Error(
                code="INVALID_MODULE_RESPONSE",
                message="T4 未返回 answer",
                status_code=502,
                details={"module_id": "T4"},
            )

        audio: AudioAsset | None = None
        if request.options.return_audio:
            try:
                audio_payload = await self._timed_call(
                    "T6",
                    "/v1/audio/synthesize",
                    {"text": answer, "language": request.target_language},
                    trace_id=trace_id,
                    request_id=request_id,
                    action="synthesize_audio",
                    pipeline=pipeline,
                )
                audio = AudioAsset.model_validate(audio_payload)
            except (ModuleCallError, ValueError):
                warnings.append("语音合成暂不可用，已返回文本讲解。")
                self._mark_degraded(pipeline, "T6", "synthesize_audio")

        response = GuideQueryResponse(
            contract_version=self.settings.contract_version,
            trace_id=trace_id,
            request_id=request_id,
            session_id=request.session_id,
            answer=answer,
            detected_language=normalized.get("detected_language", "unknown"),
            target_language=request.target_language,
            citations=citations,
            audio=audio,
            warnings=warnings,
            pipeline=pipeline if request.options.debug else [],
        )
        asyncio.create_task(
            self._emit_event(
                "guide.query.completed",
                {
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "session_id": request.session_id,
                    "target_language": request.target_language,
                    "citation_count": len(citations),
                    "warning_count": len(warnings),
                },
            )
        )
        if cache_key:
            self._cache_put(cache_key, response)
        return response

    async def generate_content(
        self, request: ContentGenerateRequest
    ) -> ContentGenerateResponse:
        request_id, trace_id = self._ids(request.request_id)
        retrieval = await self._timed_call(
            "T3",
            "/v1/retrieve",
            {
                "query": request.topic,
                "language": request.target_language,
                "top_k": 6,
                "filters": {"authorization_status": ["authorized", "public"]},
            },
            trace_id=trace_id,
            request_id=request_id,
            action="retrieve_for_content",
        )
        chunks = retrieval.get("chunks", [])
        if not isinstance(chunks, list):
            raise T0Error(
                code="INVALID_MODULE_RESPONSE",
                message="T3 返回的 chunks 必须是数组",
                status_code=502,
                details={"module_id": "T3"},
            )
        if not chunks:
            raise T0Error(
                code="NO_GROUNDED_CONTEXT",
                message="未检索到传播内容所需的可引用资料",
                status_code=422,
            )
        result = await self._timed_call(
            "T8",
            "/v1/content/generate",
            {
                "topic": request.topic,
                "target_language": request.target_language,
                "platform": request.platform,
                "audience": request.audience.model_dump(mode="json"),
                "max_length": request.max_length,
                "context": chunks,
                "requirements": {"human_review": True, "preserve_citations": True},
            },
            trace_id=trace_id,
            request_id=request_id,
            action="generate_content",
        )
        content = result.get("content")
        if not isinstance(content, str) or not content.strip():
            raise T0Error(
                code="INVALID_MODULE_RESPONSE",
                message="T8 未返回 content",
                status_code=502,
                details={"module_id": "T8"},
            )
        return ContentGenerateResponse(
            contract_version=self.settings.contract_version,
            trace_id=trace_id,
            request_id=request_id,
            content=content,
            target_language=request.target_language,
            platform=request.platform,
            citations=self._validate_citations(chunks),
            review_required=result.get("review_required", True),
        )

    async def ingest_knowledge(
        self, request: KnowledgeIngestRequest
    ) -> KnowledgeIngestResponse:
        request_id, trace_id = self._ids(request.request_id)
        normalized = await self._timed_call(
            "T1",
            "/v1/documents/normalize",
            {
                "documents": [item.model_dump(mode="json") for item in request.documents],
                "publish": request.publish,
            },
            trace_id=trace_id,
            request_id=request_id,
            action="normalize_documents",
        )
        records = normalized.get("records", [])
        if not isinstance(records, list):
            raise T0Error(
                code="INVALID_MODULE_RESPONSE",
                message="T1 返回的 records 必须是数组",
                status_code=502,
                details={"module_id": "T1"},
            )
        if not records:
            raise T0Error(
                code="NO_VALID_DOCUMENTS",
                message="T1 未返回可入库记录",
                status_code=422,
            )
        warnings: list[str] = []
        index_task = asyncio.create_task(
            self._timed_call(
                "T3",
                "/v1/index/upsert",
                {"records": records, "publish": request.publish},
                trace_id=trace_id,
                request_id=request_id,
                action="index_documents",
            )
        )
        graph_task = asyncio.create_task(
            self._timed_call(
                "T2",
                "/v1/graph/upsert",
                {"records": records, "publish": request.publish},
                trace_id=trace_id,
                request_id=request_id,
                action="upsert_graph",
            )
        )
        try:
            await index_task
        except Exception:
            graph_task.cancel()
            await asyncio.gather(graph_task, return_exceptions=True)
            raise
        try:
            await graph_task
        except ModuleCallError:
            warnings.append("T2 图谱写入失败；T3 索引已完成，可稍后重放图谱任务。")
        return KnowledgeIngestResponse(
            contract_version=self.settings.contract_version,
            trace_id=trace_id,
            request_id=request_id,
            job_id=f"JOB-{uuid.uuid4().hex[:12].upper()}",
            status="partial" if warnings else "completed",
            accepted_count=len(records),
            warnings=warnings,
        )

    async def submit_feedback(self, request: FeedbackRequest) -> AckResponse:
        request_id = request.request_id or str(uuid.uuid4())
        result = await self._timed_call(
            "T9",
            "/v1/feedback",
            request.model_dump(mode="json"),
            trace_id=request.trace_id,
            request_id=request_id,
            action="submit_feedback",
        )
        accepted = result.get("accepted")
        if not isinstance(accepted, bool):
            raise T0Error(
                code="INVALID_MODULE_RESPONSE",
                message="T9 未返回布尔类型 accepted",
                status_code=502,
                details={"module_id": "T9"},
            )
        return AckResponse(
            contract_version=self.settings.contract_version,
            trace_id=request.trace_id,
            accepted=accepted,
        )

    async def readiness(self) -> dict[str, Any]:
        checks = await asyncio.gather(
            *(client.health() for client in self.registry.clients.values())
        )
        modules = dict(zip(self.registry.clients.keys(), checks, strict=True))
        critical_ready = all(modules.get(mid, False) for mid in ("T3", "T4", "T6"))
        return {"ready": critical_ready, "mode": self.settings.mode, "modules": modules}

    async def _emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        try:
            await self.registry.get("T9").call(
                "/v1/events",
                {"event_type": event_type, "data": data},
                trace_id=data["trace_id"],
                request_id=data["request_id"],
            )
        except Exception:
            return

    def _cache_get(self, key: str) -> Any | None:
        entry = self._idempotency_cache.get(key)
        if not entry:
            return None
        if entry.expires_at <= time.monotonic():
            self._idempotency_cache.pop(key, None)
            return None
        return entry.value

    def _cache_put(self, key: str, value: Any) -> None:
        now = time.monotonic()
        expired = [
            cache_key
            for cache_key, entry in self._idempotency_cache.items()
            if entry.expires_at <= now
        ]
        for cache_key in expired:
            self._idempotency_cache.pop(cache_key, None)
        self._idempotency_cache[key] = _CacheEntry(
            expires_at=now + self.settings.idempotency_ttl_seconds,
            value=value,
        )

    @staticmethod
    def _validate_citations(chunks: list[Any]) -> list[Citation]:
        try:
            return [Citation.model_validate(chunk) for chunk in chunks]
        except (ValidationError, TypeError) as exc:
            raise T0Error(
                code="INVALID_MODULE_RESPONSE",
                message="T3 返回的引用字段不符合契约",
                status_code=502,
                details={"module_id": "T3"},
            ) from exc
