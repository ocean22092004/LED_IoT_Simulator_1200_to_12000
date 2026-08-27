import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from backend.app.auth.service import create_access_token
from backend.app.common.enums import ActualState, DeviceStatus, UserRole
from backend.app.config import Settings
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.user import User
from backend.app.main import create_app
from backend.app.mqtt import consumer
from backend.app.mqtt.consumer import handle_heartbeat
from backend.app.mqtt.schemas import ControllerHeartbeat, HeartbeatMessage
from backend.app.realtime.events import RealtimeEvent, publish_realtime_event
from backend.app.realtime.websocket import PostgresRealtimeListener, RealtimeHub
from backend.tests.integration.conftest import MappedTopology

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 27, 4, 0, tzinfo=UTC)


async def test_device_changes_emit_deltas_without_heartbeat_spam(
    session: AsyncSession,
    mapped_topology: MappedTopology,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location = await mapped_topology.create_location(f"RT-HEARTBEAT-{uuid4().hex[:8]}", 8)
    lamp = LampState(location_id=location.id, actual_state=ActualState.ON)
    session.add(lamp)
    await session.flush()
    events: list[RealtimeEvent] = []

    async def record_event(
        _session: AsyncSession,
        event_type: str,
        *,
        entity_type: str,
        entity_id: object = None,
        payload: dict[str, object] | None = None,
        occurred_at: datetime | None = None,
    ) -> RealtimeEvent:
        event = RealtimeEvent(
            type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
            occurred_at=occurred_at or NOW,
        )
        events.append(event)
        return event

    monkeypatch.setattr(consumer, "publish_realtime_event", record_event)
    heartbeat = HeartbeatMessage(
        gateway_code=mapped_topology.gateway.code,
        occurred_at=NOW,
        uptime_s=10,
        controllers=[
            ControllerHeartbeat(
                code=mapped_topology.controller.code,
                status=DeviceStatus.OFFLINE,
            )
        ],
    )

    await handle_heartbeat(
        heartbeat,
        site_code=mapped_topology.site.code,
        received_at=NOW,
        session=session,
    )
    first_event_count = len(events)
    await handle_heartbeat(
        heartbeat.model_copy(update={"occurred_at": NOW.replace(second=5)}),
        site_code=mapped_topology.site.code,
        received_at=NOW.replace(second=5),
        session=session,
    )

    assert {event.type for event in events[:first_event_count]} == {
        "gateway.status_changed",
        "controller.status_changed",
        "location.state_changed",
    }
    assert len(events) == first_event_count


async def test_websocket_pushes_authenticated_realtime_event(
    session: AsyncSession,
) -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        jwt_secret=SecretStr("realtime-test-secret-long-enough"),
    )
    admin = await session.scalar(
        select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
    )
    assert admin is not None
    token = create_access_token(user_id=admin.id, role=admin.role, settings=settings)
    app = create_app(settings=settings)
    event = RealtimeEvent(
        type="location.state_changed",
        entity_type="location",
        entity_id=uuid4(),
        occurred_at=NOW,
        payload={"actual_state": "ON"},
    )

    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/ws/events?token={token}") as websocket:
            for _ in range(100):
                if app.state.realtime_hub.subscriber_count == 1:
                    break
                await asyncio.sleep(0.01)
            app.state.realtime_hub.broadcast(event)
            message = websocket.receive_json()

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/v1/ws/events?token=invalid"):
                pass

    assert message == event.model_dump(mode="json")


async def test_postgres_notification_bridges_worker_event_to_api_hub(
    session: AsyncSession,
) -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    hub = RealtimeHub()
    listener = PostgresRealtimeListener(settings.database_url, hub)
    listener.start()
    try:
        await listener.wait_until_ready()
        async with hub.subscribe() as queue:
            expected = await publish_realtime_event(
                session,
                "activation.changed",
                entity_type="activation",
                entity_id=uuid4(),
                occurred_at=NOW,
                payload={"action": "STARTED"},
            )
            await session.commit()
            received = await asyncio.wait_for(queue.get(), timeout=2)
    finally:
        await listener.stop()

    assert received == expected
