from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.app.config import Settings, get_settings
from backend.app.db.session import database_is_ready

ReadinessProbe = Callable[[], Awaitable[bool]]


def create_app(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    probe = readiness_probe or database_is_ready
    app = FastAPI(title="Memorial LED Control Simulator")
    app.state.settings = app_settings

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", response_model=None)
    async def health_ready() -> dict[str, str] | JSONResponse:
        if await probe():
            return {"status": "ok"}
        return JSONResponse(status_code=503, content={"status": "unavailable"})

    return app
