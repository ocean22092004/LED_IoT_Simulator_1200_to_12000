import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from threading import Lock

import asyncpg  # type: ignore[import-untyped]
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.app.auth.service import InvalidTokenError, decode_access_token
from backend.app.config import Settings
from backend.app.db.models.user import User
from backend.app.db.session import get_session_factory
from backend.app.realtime.events import REALTIME_CHANNEL, RealtimeEvent

SUBSCRIBER_QUEUE_SIZE = 100
RECONNECT_SECONDS = 1.0


class RealtimeHub:
    def __init__(self) -> None:
        self._subscribers: dict[
            asyncio.Queue[RealtimeEvent],
            asyncio.AbstractEventLoop,
        ] = {}
        self._lock = Lock()

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[RealtimeEvent]]:
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(
            maxsize=SUBSCRIBER_QUEUE_SIZE
        )
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers[queue] = loop
        try:
            yield queue
        finally:
            with self._lock:
                self._subscribers.pop(queue, None)

    @staticmethod
    def _offer(queue: asyncio.Queue[RealtimeEvent], event: RealtimeEvent) -> None:
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(event)

    def broadcast(self, event: RealtimeEvent) -> None:
        with self._lock:
            subscribers = list(self._subscribers.items())
        for queue, loop in subscribers:
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(self._offer, queue, event)


def asyncpg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class PostgresRealtimeListener:
    def __init__(self, database_url: str, hub: RealtimeHub) -> None:
        self._dsn = asyncpg_dsn(database_url)
        self._hub = hub
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()

    def _notification(
        self,
        connection: asyncpg.Connection,
        process_id: int,
        channel: str,
        payload: str,
    ) -> None:
        del connection, process_id, channel
        try:
            event = RealtimeEvent.model_validate_json(payload)
        except ValueError:
            return
        self._hub.broadcast(event)

    async def _run(self) -> None:
        while True:
            connection: asyncpg.Connection | None = None
            try:
                connection = await asyncpg.connect(self._dsn)
                disconnected = asyncio.Event()
                connection.add_termination_listener(
                    lambda _, event=disconnected: event.set()
                )
                await connection.add_listener(REALTIME_CHANNEL, self._notification)
                self._ready.set()
                await disconnected.wait()
            except asyncio.CancelledError:
                raise
            except (OSError, asyncpg.PostgresError):
                await asyncio.sleep(RECONNECT_SECONDS)
            finally:
                self._ready.clear()
                if connection is not None and not connection.is_closed():
                    await connection.close()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def wait_until_ready(self) -> None:
        async with asyncio.timeout(5.0):
            await self._ready.wait()

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None


router = APIRouter(prefix="/api/v1/ws", tags=["realtime"])


def _bearer_token(websocket: WebSocket, query_token: str | None) -> str | None:
    if query_token:
        return query_token
    authorization = websocket.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token
    return None


async def _authenticated(websocket: WebSocket, token: str | None) -> bool:
    if token is None:
        return False
    settings: Settings = websocket.app.state.settings
    try:
        claims = decode_access_token(token, settings)
    except InvalidTokenError:
        return False
    async with get_session_factory()() as session:
        user = await session.get(User, claims.user_id)
        return bool(user is not None and user.is_active and user.role == claims.role)


@router.websocket("/events")
async def websocket_events(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    if not await _authenticated(websocket, _bearer_token(websocket, token)):
        await websocket.close(code=4401, reason="Authentication required")
        return
    hub: RealtimeHub = websocket.app.state.realtime_hub
    async with hub.subscribe() as queue:
        await websocket.accept()
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event.model_dump(mode="json"))
        except WebSocketDisconnect:
            return
