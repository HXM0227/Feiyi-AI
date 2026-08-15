from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings
from .errors import T0Error
from .models import (
    AckResponse,
    ContentGenerateRequest,
    ContentGenerateResponse,
    ErrorBody,
    FeedbackRequest,
    GuideQueryRequest,
    GuideQueryResponse,
    KnowledgeIngestRequest,
    KnowledgeIngestResponse,
)
from .orchestrator import Orchestrator
from .registry import build_registry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    orchestrator = Orchestrator(settings, build_registry(settings))
    app = FastAPI(
        title="非遗 AI 多语种智能解说 - T0 集成 API",
        version=settings.contract_version,
        description="T7 的统一入口；编排 T1-T9，提供追踪、降级与 Mock 联调。",
    )
    app.state.orchestrator = orchestrator
    app.state.settings = settings

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.trace_id = trace_id
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Request-ID"] = request_id
        return response

    async def authorize(
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> None:
        if settings.api_key and x_api_key != settings.api_key:
            raise T0Error(
                code="UNAUTHORIZED",
                message="X-API-Key 无效或缺失",
                status_code=401,
                retryable=False,
            )

    @app.exception_handler(T0Error)
    async def handle_t0_error(request: Request, exc: T0Error) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID", str(uuid.uuid4())))
        body = ErrorBody(
            code=exc.code,
            message=exc.message,
            trace_id=trace_id,
            retryable=exc.retryable,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID", str(uuid.uuid4())))
        errors = [
            {
                "field": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in exc.errors()
        ]
        body = ErrorBody(
            code="VALIDATION_ERROR",
            message="请求参数不符合接口契约",
            trace_id=trace_id,
            retryable=False,
            details={"errors": errors},
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["system"])
    async def readyz() -> JSONResponse:
        result = await orchestrator.readiness()
        return JSONResponse(status_code=200 if result["ready"] else 503, content=result)

    @app.get("/v1/capabilities", dependencies=[Depends(authorize)], tags=["system"])
    async def capabilities() -> dict[str, object]:
        return {
            "contract_version": settings.contract_version,
            "mode": settings.mode,
            "languages": ["zh-CN", "en"],
            "input_types": ["text", "audio", "image", "exhibit_id"],
            "routes": ["guide.query", "content.generate", "knowledge.ingest", "feedback"],
        }

    @app.post(
        "/v1/guide/query",
        response_model=GuideQueryResponse,
        dependencies=[Depends(authorize)],
        tags=["guide"],
    )
    async def guide_query(
        body: GuideQueryRequest,
        idempotency_key: Annotated[
            str | None, Header(alias="Idempotency-Key", max_length=128)
        ] = None,
        x_request_id: Annotated[
            str | None, Header(alias="X-Request-ID", max_length=128)
        ] = None,
    ) -> GuideQueryResponse:
        if x_request_id and not body.request_id:
            body = body.model_copy(update={"request_id": x_request_id})
        return await orchestrator.guide_query(body, idempotency_key=idempotency_key)

    @app.post(
        "/v1/content/generate",
        response_model=ContentGenerateResponse,
        dependencies=[Depends(authorize)],
        tags=["content"],
    )
    async def generate_content(
        body: ContentGenerateRequest,
        x_request_id: Annotated[
            str | None, Header(alias="X-Request-ID", max_length=128)
        ] = None,
    ) -> ContentGenerateResponse:
        if x_request_id and not body.request_id:
            body = body.model_copy(update={"request_id": x_request_id})
        return await orchestrator.generate_content(body)

    @app.post(
        "/v1/knowledge/ingest",
        response_model=KnowledgeIngestResponse,
        dependencies=[Depends(authorize)],
        tags=["knowledge"],
    )
    async def ingest_knowledge(
        body: KnowledgeIngestRequest,
        x_request_id: Annotated[
            str | None, Header(alias="X-Request-ID", max_length=128)
        ] = None,
    ) -> KnowledgeIngestResponse:
        if x_request_id and not body.request_id:
            body = body.model_copy(update={"request_id": x_request_id})
        return await orchestrator.ingest_knowledge(body)

    @app.post(
        "/v1/feedback",
        response_model=AckResponse,
        dependencies=[Depends(authorize)],
        tags=["feedback"],
    )
    async def feedback(
        body: FeedbackRequest,
        x_request_id: Annotated[
            str | None, Header(alias="X-Request-ID", max_length=128)
        ] = None,
    ) -> AckResponse:
        if x_request_id and not body.request_id:
            body = body.model_copy(update={"request_id": x_request_id})
        return await orchestrator.submit_feedback(body)

    return app
