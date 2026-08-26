from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.activations.router import router as activation_router
from backend.app.anniversaries.router import router as anniversary_router
from backend.app.auth.router import router as auth_router
from backend.app.common.errors import (
    APIError,
    api_error_handler,
    request_validation_error_handler,
)
from backend.app.config import Settings, get_settings
from backend.app.db.session import database_is_ready
from backend.app.locations.router import person_router, zone_router
from backend.app.locations.router import router as location_router
from backend.app.simulator.router import router as simulator_router

ReadinessProbe = Callable[[], Awaitable[bool]]


def create_app(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    probe = readiness_probe or database_is_ready
    app = FastAPI(title="Memorial LED Control Simulator")
    app.state.settings = app_settings
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.include_router(auth_router)
    app.include_router(activation_router)
    app.include_router(anniversary_router)
    app.include_router(location_router)
    app.include_router(zone_router)
    app.include_router(person_router)
    app.include_router(simulator_router)

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", response_model=None)
    async def health_ready() -> dict[str, str] | JSONResponse:
        if await probe():
            return {"status": "ok"}
        return JSONResponse(status_code=503, content={"status": "unavailable"})

    return app
