from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings
from .schemas import (
    HealthResponse,
    NormalizeRequest,
    NormalizeResponse,
    SynthesizeRequest,
    SynthesizeResponse,
)
from .service import (
    AsrUnavailableError,
    InputMediaService,
    InputNormalizationError,
    TtsUnavailableError,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    service = InputMediaService(settings)
    app = FastAPI(title="T6 输入规范化与语音合成服务", version=settings.contract_version)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "请求不符合 T6 契约",
                "details": jsonable_encoder(exc.errors()),
            },
        )

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(mode=settings.mode, contract_version=settings.contract_version)

    @app.get("/readyz", response_model=HealthResponse)
    async def readyz() -> HealthResponse:
        return HealthResponse(mode=settings.mode, contract_version=settings.contract_version)

    @app.post("/v1/input/normalize", response_model=NormalizeResponse)
    async def normalize(request: NormalizeRequest) -> NormalizeResponse:
        try:
            return service.normalize(request)

        except AsrUnavailableError as exc:
            raise HTTPException(
                status_code=502,
                detail=str(exc),
            ) from exc

        except InputNormalizationError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

    @app.post("/v1/audio/synthesize", response_model=SynthesizeResponse)
    async def synthesize(request: SynthesizeRequest) -> SynthesizeResponse:
        try:
            return service.synthesize(request)
        except TtsUnavailableError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except InputNormalizationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


app = create_app()
