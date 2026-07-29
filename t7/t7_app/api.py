from __future__ import annotations

import secrets
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .models import (
    ContentGenerateRequest,
    ContentStatus,
    ContentUpdateRequest,
    FeedbackRequest,
    GuideQueryRequest,
    KnowledgeIngestRequest,
)
from .store import ContentStore, StoreError
from .t0_client import HttpT0Client, T0Client, T0ClientError


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
ALLOWED_UPLOAD_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
}


def create_app(
    settings: Settings | None = None,
    *,
    t0_client: T0Client | None = None,
    store: ContentStore | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    client = t0_client or HttpT0Client(
        base_url=settings.t0_base_url,
        api_key=settings.t0_api_key,
        timeout_seconds=settings.request_timeout_seconds,
    )
    content_store = store or ContentStore(settings.database_path)

    app = FastAPI(
        title="非遗 AI 多语种智能解说 - T7 导览与内容管理",
        version="1.0.0",
        description="面向游客的扫码导览 H5 与面向运营人员的轻量内容管理 BFF。",
    )
    app.state.settings = settings
    app.state.t0_client = client
    app.state.content_store = content_store

    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")
    app.mount("/media", StaticFiles(directory=settings.upload_dir), name="media")

    def admin_guard(
        x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    ) -> None:
        if not settings.admin_token:
            raise HTTPException(status_code=503, detail="后台功能未配置管理员令牌")
        if not x_admin_token or not secrets.compare_digest(
            x_admin_token, settings.admin_token
        ):
            raise HTTPException(status_code=401, detail="管理员令牌无效")

    @app.exception_handler(T0ClientError)
    async def handle_t0_error(_: Request, exc: T0ClientError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.body)

    @app.exception_handler(StoreError)
    async def handle_store_error(_: Request, exc: StoreError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "code": "CONTENT_WORKFLOW_CONFLICT",
                "message": str(exc),
                "retryable": False,
                "details": {},
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "请求参数不符合 T7 接口契约",
                "retryable": False,
                "details": {"errors": errors},
            },
        )

    @app.get("/", include_in_schema=False)
    async def visitor_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/admin", include_in_schema=False)
    async def admin_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "admin.html")

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "manifest.webmanifest",
            media_type="application/manifest+json",
        )

    @app.get("/sw.js", include_in_schema=False)
    async def service_worker() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "sw.js",
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "module": "T7"}

    @app.get("/readyz", tags=["system"])
    async def readyz() -> JSONResponse:
        try:
            upstream = await client.get("/healthz")
            available = upstream.get("status") == "ok"
        except T0ClientError:
            available = False
        return JSONResponse(
            status_code=200 if available else 503,
            content={"ready": available, "dependencies": {"T0": available}},
        )

    @app.get("/api/config", tags=["visitor"])
    async def public_config() -> dict[str, Any]:
        fallback = {
            "contract_version": "1.0.0",
            "languages": ["zh-CN", "en"],
            "input_types": ["text", "audio", "image", "exhibit_id"],
            "routes": ["guide.query", "content.generate", "feedback"],
        }
        try:
            capabilities = await client.get("/v1/capabilities")
        except T0ClientError:
            capabilities = fallback
        return {
            "app_name": settings.app_name,
            "environment": settings.environment,
            "t0_available": capabilities is not fallback,
            "capabilities": capabilities,
        }

    @app.post("/api/media", tags=["visitor"])
    async def upload_media(
        request: Request,
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        suffix = ALLOWED_UPLOAD_TYPES.get(file.content_type or "")
        if not suffix:
            raise HTTPException(status_code=415, detail="仅支持常见图片和音频格式")
        data = await file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="上传文件超过大小限制")
        media_id = f"{uuid.uuid4().hex}{suffix}"
        target = settings.upload_dir / media_id
        target.write_bytes(data)
        base_url = settings.public_base_url or str(request.base_url).rstrip("/")
        return {
            "media_url": f"{base_url}/media/{media_id}",
            "mime_type": file.content_type,
            "size": len(data),
        }

    @app.post("/api/guide/query", tags=["visitor"])
    async def guide_query(
        body: GuideQueryRequest,
        idempotency_key: Annotated[
            str | None, Header(alias="Idempotency-Key", max_length=128)
        ] = None,
        x_request_id: Annotated[
            str | None, Header(alias="X-Request-ID", max_length=128)
        ] = None,
    ) -> dict[str, Any]:
        request_id = body.request_id or x_request_id or str(uuid.uuid4())
        payload = body.model_copy(update={"request_id": request_id}).model_dump(
            mode="json", exclude_none=True
        )
        return await client.post(
            "/v1/guide/query",
            payload,
            request_id=request_id,
            idempotency_key=idempotency_key or request_id,
        )

    @app.post("/api/feedback", tags=["visitor"])
    async def feedback(
        body: FeedbackRequest,
        x_request_id: Annotated[
            str | None, Header(alias="X-Request-ID", max_length=128)
        ] = None,
    ) -> dict[str, Any]:
        request_id = body.request_id or x_request_id or str(uuid.uuid4())
        payload = body.model_copy(update={"request_id": request_id}).model_dump(
            mode="json", exclude_none=True
        )
        return await client.post(
            "/v1/feedback",
            payload,
            request_id=request_id,
        )

    @app.get("/api/content/published", tags=["visitor"])
    async def published_content(
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> dict[str, Any]:
        return {
            "items": content_store.list(ContentStatus.PUBLISHED.value, limit=limit)
        }

    @app.post(
        "/api/admin/content/generate",
        dependencies=[Depends(admin_guard)],
        tags=["admin"],
    )
    async def generate_content(body: ContentGenerateRequest) -> dict[str, Any]:
        request_id = body.request_id or str(uuid.uuid4())
        payload = body.model_copy(update={"request_id": request_id}).model_dump(
            mode="json", exclude_none=True
        )
        response = await client.post(
            "/v1/content/generate",
            payload,
            request_id=request_id,
        )
        return content_store.create_from_t0(payload, response)

    @app.get(
        "/api/admin/content",
        dependencies=[Depends(admin_guard)],
        tags=["admin"],
    )
    async def list_content(
        status: ContentStatus | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> dict[str, Any]:
        return {
            "items": content_store.list(
                status.value if status is not None else None,
                limit=limit,
            )
        }

    @app.patch(
        "/api/admin/content/{content_id}",
        dependencies=[Depends(admin_guard)],
        tags=["admin"],
    )
    async def update_content(
        content_id: str, body: ContentUpdateRequest
    ) -> dict[str, Any]:
        return content_store.update(
            content_id,
            content=body.content,
            status=body.status.value if body.status is not None else None,
            note=body.note,
        )

    @app.get(
        "/api/admin/content/{content_id}/history",
        dependencies=[Depends(admin_guard)],
        tags=["admin"],
    )
    async def content_history(content_id: str) -> dict[str, Any]:
        return {"items": content_store.history(content_id)}

    @app.post(
        "/api/admin/knowledge/ingest",
        dependencies=[Depends(admin_guard)],
        tags=["admin"],
    )
    async def ingest_knowledge(body: KnowledgeIngestRequest) -> dict[str, Any]:
        request_id = body.request_id or str(uuid.uuid4())
        payload = body.model_copy(update={"request_id": request_id}).model_dump(
            mode="json", exclude_none=True
        )
        return await client.post(
            "/v1/knowledge/ingest",
            payload,
            request_id=request_id,
        )

    return app
