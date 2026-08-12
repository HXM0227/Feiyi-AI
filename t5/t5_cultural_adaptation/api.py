from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings
from .schemas import AdaptationRequest, AdaptationResponse, HealthResponse
from .service import AdaptationService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    service = AdaptationService.from_path(settings.policy_path)
    app = FastAPI(title="T5 跨文化适配与提示词策略服务", version=settings.contract_version)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "请求不符合 T5 契约",
                "details": jsonable_encoder(exc.errors()),
            },
        )

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(
            contract_version=settings.contract_version,
            policy_version=service.policy.policy_version,
        )

    @app.get("/readyz", response_model=HealthResponse)
    async def readyz() -> HealthResponse:
        return HealthResponse(
            contract_version=settings.contract_version,
            policy_version=service.policy.policy_version,
        )

    @app.post("/v1/adapt", response_model=AdaptationResponse)
    async def adapt(request: AdaptationRequest) -> AdaptationResponse:
        return service.adapt(request)

    return app


app = create_app()
