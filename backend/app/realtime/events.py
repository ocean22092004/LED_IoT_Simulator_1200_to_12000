from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

REALTIME_CHANNEL = "memorial_realtime_events"
POSTGRES_NOTIFY_MAX_BYTES = 8_000
RealtimeEventType = Literal[
    "location.state_changed",
    "gateway.status_changed",
    "controller.status_changed",
    "command.failed",
    "lamp.health_changed",
    "activation.changed",
]


class RealtimeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    type: RealtimeEventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


async def publish_realtime_event(
    session: AsyncSession,
    event_type: RealtimeEventType,
    *,
    entity_type: str,
    entity_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> RealtimeEvent:
    event = RealtimeEvent(
        type=event_type,
        occurred_at=occurred_at or datetime.now(UTC),
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
    )
    encoded = event.model_dump_json()
    if len(encoded.encode()) >= POSTGRES_NOTIFY_MAX_BYTES:
        raise ValueError("realtime event exceeds PostgreSQL NOTIFY payload limit")
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": REALTIME_CHANNEL, "payload": encoded},
    )
    return event
