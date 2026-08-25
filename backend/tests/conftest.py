from collections.abc import Callable

import pytest
from fastapi import FastAPI

from backend.app.config import Settings
from backend.app.main import ReadinessProbe, create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture
def app_factory(settings: Settings) -> Callable[[ReadinessProbe], FastAPI]:
    def factory(readiness_probe: ReadinessProbe) -> FastAPI:
        return create_app(settings=settings, readiness_probe=readiness_probe)

    return factory
