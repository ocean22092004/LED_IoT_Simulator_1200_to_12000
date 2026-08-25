from collections.abc import Callable

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.app.main import ReadinessProbe


async def request(app: FastAPI, path: str):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.get(path)


async def test_liveness(app_factory: Callable[[ReadinessProbe], FastAPI]):
    async def ready() -> bool:
        return True

    response = await request(app_factory(ready), "/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_succeeds_when_database_probe_succeeds(
    app_factory: Callable[[ReadinessProbe], FastAPI],
):
    async def ready() -> bool:
        return True

    response = await request(app_factory(ready), "/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_is_unavailable_when_database_probe_fails(
    app_factory: Callable[[ReadinessProbe], FastAPI],
):
    async def unavailable() -> bool:
        return False

    response = await request(app_factory(unavailable), "/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
