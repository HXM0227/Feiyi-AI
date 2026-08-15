from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from .config import Settings
from .models import (
    EntityDetailResponse,
    EntityResult,
    ErrorBody,
    GraphQueryRequest,
    GraphQueryResponse,
    Predicate,
    RelationResult,
    UpsertRequest,
    UpsertResponse,
)
from .storage import GraphStore

logger = logging.getLogger("t2")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_db_parent()
    store = GraphStore(settings.db_path)
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        store.close()

    app = FastAPI(
        title="T2 ??????????",
        version=settings.contract_version,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.store = store

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
        status = exc.status_code
        body = ErrorBody(
            code="UNAUTHORIZED" if status == 401 else "HTTP_ERROR",
            message="未提供有效的访问令牌" if status == 401 else str(exc.detail),
            trace_id=trace_id,
            retryable=False,
        )
        return JSONResponse(status_code=status, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID", str(uuid.uuid4())))
        body = ErrorBody(
            code="VALIDATION_ERROR",
            message="请求字段校验失败",
            trace_id=trace_id,
            retryable=False,
            details={"errors": _safe_validation_errors(exc.errors())},
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError):
        trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID", str(uuid.uuid4())))
        body = ErrorBody(
            code="INVALID_GRAPH_DATA",
            message=str(exc),
            trace_id=trace_id,
            retryable=False,
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID", str(uuid.uuid4())))
        logger.exception("T2 internal error trace_id=%s", trace_id)
        body = ErrorBody(
            code="INTERNAL_ERROR",
            message="T2 内部处理失败",
            trace_id=trace_id,
            retryable=True,
        )
        return JSONResponse(status_code=500, content=body.model_dump(mode="json"))

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "module": "T2", "contract_version": settings.contract_version}

    @app.get("/readyz", response_model=None, tags=["system"])
    async def readyz() -> JSONResponse | dict[str, Any]:
        try:
            store.check_ready()
        except Exception as exc:
            logger.error("T2 readiness check failed: %s", exc)
            return JSONResponse(
                status_code=503,
                content={
                    "ready": False,
                    "module": "T2",
                    "contract_version": settings.contract_version,
                    "code": "DATABASE_NOT_READY",
                    "message": "T2 知识图谱存储不可用",
                },
            )
        return {"ready": True, "module": "T2", "contract_version": settings.contract_version}

    @app.get("/v1/capabilities", tags=["system"])
    async def capabilities() -> dict[str, Any]:
        return {
            "module": "T2",
            "contract_version": settings.contract_version,
            "storage": "sqlite",
            "mode": "mvp",
            "entity_types": ["craft", "person", "place", "tool", "symbol", "process", "concept"],
            "predicates": [
                "belongs_to", "related_to", "uses", "practiced_in", "includes",
                "has_symbol", "has_process", "has_tool", "adapted_for", "example_of",
            ],
            "authorization_default": ["authorized", "public"],
            "routes": [
                "/v1/graph/upsert", "/v1/graph/query",
                "/v1/graph/entities/{entity_id}", "/v1/graph/relations",
            ],
        }

    @app.post("/v1/graph/upsert", response_model=UpsertResponse, tags=["graph"])
    async def upsert_graph(
        payload: UpsertRequest,
        authorization: str | None = Header(default=None),
    ) -> UpsertResponse:
        _check_token(settings.api_token, authorization)
        if len(payload.records) > settings.max_records:
            raise HTTPException(status_code=422, detail=f"records must be <= {settings.max_records}")
        for record in payload.records:
            if len(record.entities) > settings.max_entities_per_record:
                raise HTTPException(status_code=422, detail="too many entities in record")
            if len(record.relations) > settings.max_relations_per_record:
                raise HTTPException(status_code=422, detail="too many relations in record")
        entity_count, relation_count, warnings = store.upsert(payload.records)
        return UpsertResponse(
            contract_version=settings.contract_version,
            accepted_count=len(payload.records),
            entity_count=entity_count,
            relation_count=relation_count,
            warnings=warnings,
        )

    @app.post("/v1/graph/query", response_model=GraphQueryResponse, tags=["graph"])
    async def query_graph(
        payload: GraphQueryRequest,
        authorization: str | None = Header(default=None),
    ) -> GraphQueryResponse:
        _check_token(settings.api_token, authorization)
        statuses = payload.filters.authorization_status if payload.filters else None
        entities = store.query_entities(
            entity_id=payload.entity_id,
            name=payload.name,
            alias=payload.alias,
            entity_type=payload.entity_type,
            authorization_status=statuses,
            limit=payload.limit,
        )
        relations: list[RelationResult] = []
        if payload.include_relations:
            relation_entity_ids = {entity.entity_id for entity in entities}
            if payload.entity_id:
                relation_entity_ids.add(payload.entity_id)
            for entity_id in sorted(relation_entity_ids):
                relations.extend(store.query_relations(
                    entity_id=entity_id,
                    predicate=payload.predicate,
                    authorization_status=statuses,
                    limit=payload.limit,
                ))
            if payload.predicate and not relation_entity_ids:
                relations = store.query_relations(
                    predicate=payload.predicate,
                    authorization_status=statuses,
                    limit=payload.limit,
                )
        elif payload.predicate:
            relations = store.query_relations(
                predicate=payload.predicate,
                authorization_status=statuses,
                limit=payload.limit,
            )
        relations = _dedupe_relations(relations)[: payload.limit]
        return GraphQueryResponse(
            contract_version=settings.contract_version,
            entities=entities,
            relations=relations,
        )

    @app.get("/v1/graph/entities/{entity_id}", response_model=EntityDetailResponse, tags=["graph"])
    async def entity_detail(
        entity_id: str,
        include_relations: bool = True,
        authorization: str | None = Header(default=None),
    ) -> EntityDetailResponse:
        _check_token(settings.api_token, authorization)
        entity = store.get_entity(entity_id)
        relations = store.query_relations(entity_id=entity_id) if include_relations else []
        return EntityDetailResponse(
            contract_version=settings.contract_version,
            entity=entity,
            relations=relations,
        )

    @app.get("/v1/graph/relations", response_model=GraphQueryResponse, tags=["graph"])
    async def relations(
        entity_id: str | None = None,
        subject_id: str | None = None,
        object_id: str | None = None,
        predicate: Predicate | None = None,
        limit: int = 50,
        authorization: str | None = Header(default=None),
    ) -> GraphQueryResponse:
        _check_token(settings.api_token, authorization)
        relations_result = store.query_relations(
            entity_id=entity_id,
            subject_id=subject_id,
            object_id=object_id,
            predicate=predicate,
            limit=limit,
        )
        return GraphQueryResponse(contract_version=settings.contract_version, relations=relations_result)

    return app


def _check_token(expected: str, authorization: str | None) -> None:
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")


def _dedupe_relations(values: list[RelationResult]) -> list[RelationResult]:
    result: list[RelationResult] = []
    seen: set[str] = set()
    for value in values:
        if value.relation_id not in seen:
            seen.add(value.relation_id)
            result.append(value)
    return result


def _safe_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "loc": list(error.get("loc", [])),
            "type": error.get("type", "value_error"),
            "message": str(error.get("msg", "validation error")),
        }
        for error in errors
    ]
