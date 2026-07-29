from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from .config import Settings
from .schemas import GenerationRequest, GenerationResponse, HealthResponse
from .service import GenerationError, GenerationService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    service = GenerationService(settings)
    app = FastAPI(title="T4 多语种理解、翻译与生成服务", version=settings.contract_version)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR", "message": "请求不符合 T4 契约", "details": jsonable_encoder(exc.errors())})

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok", mode=settings.mode)

    @app.get("/readyz", response_model=HealthResponse)
    async def readyz() -> HealthResponse:
        if not service.ready():
            raise HTTPException(status_code=503, detail="qwen mode requires DASHSCOPE_API_KEY")
        return HealthResponse(status="ok", mode=settings.mode)

    @app.post("/v1/generate", response_model=GenerationResponse)
    async def generate(request: GenerationRequest) -> GenerationResponse:
        try:
            return await service.generate(request)
        except GenerationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


app = create_app()
