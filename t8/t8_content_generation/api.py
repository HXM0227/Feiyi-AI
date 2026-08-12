from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings
from .schemas import ContentGenerationRequest, ContentGenerationResponse, HealthResponse
from .service import ContentGenerationError, ContentGenerationService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    service = ContentGenerationService(settings)
    app = FastAPI(
        title="T8 多语种传播内容生成服务",
        version=settings.contract_version,
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "请求不符合 T8 契约",
                "details": jsonable_encoder(exc.errors()),
            },
        )

    @app.middleware("http")
    async def trace_headers(request: Request, call_next):
        response = await call_next(request)
        for header in ("X-Trace-ID", "X-Request-ID"):
            value = request.headers.get(header)
            if value:
                response.headers[header] = value
        return response

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok", mode=settings.mode)

    @app.get("/readyz", response_model=HealthResponse)
    async def readyz() -> HealthResponse:
        if not service.ready():
            raise HTTPException(
                status_code=503,
                detail="qwen mode requires DASHSCOPE_API_KEY",
            )
        return HealthResponse(status="ok", mode=settings.mode)

    @app.post(
        "/v1/content/generate",
        response_model=ContentGenerationResponse,
    )
    async def generate(
        body: ContentGenerationRequest,
        response: Response,
    ) -> ContentGenerationResponse:
        try:
            result = await service.generate(body)
            response.headers["X-T8-Generator-Mode"] = result.generator_mode
            return result
        except ContentGenerationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


app = create_app()
