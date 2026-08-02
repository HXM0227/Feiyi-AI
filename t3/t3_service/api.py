from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings
from .index import retrieve
from .models import ErrorBody, RetrieveRequest, UpsertRequest, UpsertResponse, RetrieveResponse
from .storage import SQLiteIndex

logger = logging.getLogger("t3")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_db_parent()
    index = SQLiteIndex(settings.db_path)
    app = FastAPI(title="T3 资料索引与检索服务", version=settings.contract_version)
    app.state.settings = settings
    app.state.index = index

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
        body = ErrorBody(code=code, message=message, trace_id=trace_id)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID", str(uuid.uuid4())))
        body = ErrorBody(
            code="VALIDATION_ERROR",
            message="请求字段校验失败",
            trace_id=trace_id,
            details={"errors": _safe_validation_errors(exc.errors())},
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID", str(uuid.uuid4())))
        logger.exception("T3 internal error trace_id=%s", trace_id)
        body = ErrorBody(
            code="INTERNAL_ERROR",
            message="T3 内部处理失败",
            trace_id=trace_id,
            retryable=True,
        )
        return JSONResponse(status_code=500, content=body.model_dump(mode="json"))

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "module": "T3", "contract_version": settings.contract_version}

    @app.get("/readyz")
    async def readyz() -> dict[str, Any]:
        try:
            index.check_ready()
        except Exception as exc:
            logger.error("T3 readiness check failed: %s", exc)
            return JSONResponse(
                status_code=503,
                content={
                    "ready": False,
                    "module": "T3",
                    "contract_version": settings.contract_version,
                    "code": "DATABASE_NOT_READY",
                    "message": "T3 索引存储不可用",
                },
            )
        return {"ready": True, "module": "T3", "contract_version": settings.contract_version}

    @app.get("/v1/capabilities")
    async def capabilities() -> dict[str, Any]:
        return {
            "module": "T3",
            "contract_version": settings.contract_version,
            "storage": "sqlite",
            "retrieval": "deterministic_keyword",
            "max_top_k": settings.max_top_k,
            "authorization_default": ["authorized", "public"],
        }

    @app.post("/v1/index/upsert", response_model=UpsertResponse)
    async def upsert(payload: UpsertRequest, request: Request, authorization: str | None = Header(default=None)) -> UpsertResponse:
        _check_token(settings.api_token, authorization)
        records = [record.model_dump(mode="json") for record in payload.records]
        warnings: list[str] = []
        for record in records:
            if record["authorization_status"] in {"unknown", "restricted"}:
                warnings.append(
                    f"source_id={record['source_id']} has authorization_status={record['authorization_status']}; retrieval will filter it by default"
                )
            if not record["chunks"]:
                warnings.append(f"source_id={record['source_id']} contains no chunks and was accepted without indexed content")
        indexed_count = index.upsert(records)
        return UpsertResponse(
            contract_version=settings.contract_version,
            accepted_count=len(records),
            indexed_count=indexed_count,
            warnings=warnings,
        )

    @app.post("/v1/retrieve", response_model=RetrieveResponse)
    async def retrieve_chunks(payload: RetrieveRequest, request: Request, authorization: str | None = Header(default=None)) -> RetrieveResponse:
        _check_token(settings.api_token, authorization)
        if payload.top_k > settings.max_top_k:
            raise HTTPException(status_code=422, detail=f"top_k must be <= {settings.max_top_k}")
        chunks = retrieve(
            index.all_chunks(),
            query=payload.query,
            language=payload.language,
            top_k=payload.top_k,
            authorization_status=payload.filters.authorization_status if payload.filters is not None else None,
            max_excerpt_chars=settings.max_excerpt_chars,
        )
        return RetrieveResponse(chunks=chunks)

    return app


def _check_token(expected: str, authorization: str | None) -> None:
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")


def _safe_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for error in errors:
        safe.append(
            {
                "loc": list(error.get("loc", [])),
                "type": error.get("type", "value_error"),
                "message": str(error.get("msg", "validation error")),
            }
        )
    return safe
