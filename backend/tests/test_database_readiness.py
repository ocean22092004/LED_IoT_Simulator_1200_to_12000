import asyncio

from backend.app.db import session as session_module


class SlowConnection:
    async def execute(self, _statement):
        await asyncio.sleep(1)


class SlowConnectionContext:
    async def __aenter__(self):
        return SlowConnection()

    async def __aexit__(self, _exc_type, _exc_value, _traceback):
        return None


class SlowEngine:
    def connect(self):
        return SlowConnectionContext()


async def test_database_readiness_times_out_stalled_connection(monkeypatch):
    monkeypatch.setattr(
        session_module,
        "get_engine",
        lambda: SlowEngine(),
    )
    monkeypatch.setattr(session_module, "DATABASE_READY_TIMEOUT_SECONDS", 0.01)

    result = await session_module.database_is_ready()

    assert result is False


def test_engine_uses_bounded_driver_connect_timeout(monkeypatch):
    captured_connect_args = None

    def capture_engine(_url, **kwargs):
        nonlocal captured_connect_args
        captured_connect_args = kwargs["connect_args"]
        return object()

    monkeypatch.setattr(session_module, "create_async_engine", capture_engine)
    session_module.get_engine.cache_clear()

    try:
        session_module.get_engine()
    finally:
        session_module.get_engine.cache_clear()

    assert captured_connect_args == {
        "timeout": session_module.DATABASE_READY_TIMEOUT_SECONDS,
    }
