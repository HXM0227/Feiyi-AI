from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings
from .ledger import Ledger
from .models import ErrorBody, NormalizeRequest, NormalizeResponse
from .processor import normalize_document

logger = logging.getLogger("t1")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_db_parent()
    ledger = Ledger(settings.db_path)
    app = FastAPI(title="T1 资料采集、清洗与元数据服务", version=settings.contract_version)
    app.state.settings = settings
    app.state.ledger = ledger

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

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID", str(uuid.uuid4())))
        code = "UNAUTHORIZED" if exc.status_code == 401 else "HTTP_ERROR"
        message = "未提供有效的访问令牌" if exc.status_code == 401 else str(exc.detail)
        body = ErrorBody(
            code=code,
            message=message,
            trace_id=trace_id,
            retryable=False,
            details={},
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID", str(uuid.uuid4())))
        details = {"errors": _safe_validation_errors(exc.errors())}
        body = ErrorBody(
            code="VALIDATION_ERROR",
            message="请求字段校验失败",
            trace_id=trace_id,
            retryable=False,
            details=details,
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID", str(uuid.uuid4())))
        logger.error("T1 internal error trace_id=%s", trace_id)
        body = ErrorBody(
            code="INTERNAL_ERROR",
            message="T1 内部处理失败",
            trace_id=trace_id,
            retryable=True,
            details={},
        )
        return JSONResponse(status_code=500, content=body.model_dump(mode="json"))

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "module": "T1", "contract_version": settings.contract_version}

    @app.get("/readyz")
    async def readyz() -> dict[str, Any]:
        try:
            ledger.check_ready()
        except Exception as exc:
            logger.error("T1 readiness check failed: %s", exc)
            return JSONResponse(
                status_code=503,
                content={
                    "ready": False,
                    "module": "T1",
                    "contract_version": settings.contract_version,
                    "code": "DATABASE_NOT_READY",
                    "message": "T1 资料台账不可用",
                },
            )
        return {"ready": True, "module": "T1", "contract_version": settings.contract_version}

    @app.get("/v1/capabilities")
    async def capabilities() -> dict[str, Any]:
        return {
            "module": "T1",
            "contract_version": settings.contract_version,
            "media_types": ["text", "document"],
            "pre_extracted_media_types": ["image", "audio", "video"],
            "max_documents": 100,
            "max_chunk_chars": settings.max_chunk_chars,
        }

    @app.get("/v1/sources")
    async def sources(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        _check_token(settings.api_token, authorization)
        return {"sources": ledger.list_sources()}

    @app.post("/v1/documents/normalize", response_model=NormalizeResponse)
    async def normalize_documents(
        payload: NormalizeRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> NormalizeResponse:
        _check_token(settings.api_token, authorization)
        trace_id = request.state.trace_id
        request_id = request.state.request_id
        records = []
        rejected = []
        warnings: list[str] = []
        for document in payload.documents:
            record, reject, cleaned, warning = normalize_document(
                document,
                max_chunk_chars=settings.max_chunk_chars,
                chunk_overlap=settings.chunk_overlap,
                publish=payload.publish,
            )
            if reject is not None:
                rejected.append(reject)
                continue
            assert record is not None and cleaned is not None
            records.append(record)
            ledger.upsert(
                source_id=record.source_id,
                source_uri=record.source_uri,
                title=record.title,
                media_type=record.media_type,
                authorization_status=record.authorization_status,
                metadata=record.metadata,
                content=cleaned,
                chunk_count=len(record.chunks),
                publish=payload.publish,
                trace_id=trace_id,
                request_id=request_id,
            )
            if payload.publish and record.authorization_status in {"restricted", "unknown"}:
                warning = "publish=true 未改变受限或未知授权状态"
            if warning:
                warnings.append(warning)
        return NormalizeResponse(records=records, rejected=rejected, warnings=warnings)

    return app


def _check_token(expected: str, authorization: str | None) -> None:
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")


def _safe_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for error in errors:
        safe.append({
            "loc": list(error.get("loc", [])),
            "type": error.get("type", "value_error"),
            "message": str(error.get("msg", "validation error")),
        })
    return safe
