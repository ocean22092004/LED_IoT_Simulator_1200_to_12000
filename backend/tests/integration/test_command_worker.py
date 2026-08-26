import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import CommandStatus, DesiredState
from backend.app.db.models.command import LightCommand
from backend.app.lights.commands import enqueue_state_command
from backend.app.workers.command_worker import process_due_commands
from backend.tests.integration.conftest import MappedTopology

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class PublishedMessage:
    topic: str
    payload: str
    qos: int
    retain: bool


@dataclass
class RecordingPublisher:
    messages: list[PublishedMessage] = field(default_factory=list)

    async def publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> None:
        self.messages.append(PublishedMessage(topic, payload, qos, retain))


@dataclass
class FailingPublisher:
    calls: int = 0

    async def publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> None:
        self.calls += 1
        raise ConnectionError("broker unavailable")


async def create_command(
    session: AsyncSession,
    mapped_topology: MappedTopology,
    now: datetime,
) -> LightCommand:
    location = await mapped_topology.create_location("WORKER-A250", 58)
    return await enqueue_state_command(
        location.id,
        DesiredState.ON,
        "VISIT",
        now=now,
        session=session,
    )


async def test_worker_publishes_pending_qos1_without_retain(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    command = await create_command(session, mapped_topology, now)
    publisher = RecordingPublisher()

    assert await process_due_commands(
        publisher,
        now=now,
        session=session,
    ) == 1

    assert command.status is CommandStatus.SENT
    assert command.attempt_count == 1
    assert command.sent_at == now
    assert command.next_attempt_at == now + timedelta(seconds=1)
    assert len(publisher.messages) == 1
    published = publisher.messages[0]
    assert published.topic == "memorial/v1/sites/SITE-TEST/gateways/GW-A/commands"
    assert published.qos == 1
    assert published.retain is False
    payload = json.loads(published.payload)
    assert payload == {
        "schema_version": 1,
        "command_id": str(command.id),
        "issued_at": command.created_at.isoformat().replace("+00:00", "Z"),
        "site_code": "SITE-TEST",
        "gateway_code": "GW-A",
        "controller_code": "CTRL-A-01",
        "channel": 58,
        "target_state": "ON",
        "location_code": "WORKER-A250",
        "reason": "VISIT",
    }


async def test_retry_reuses_command_id_and_fails_after_three_unacked_attempts(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    started_at = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    command = await create_command(session, mapped_topology, started_at)
    publisher = RecordingPublisher()

    for attempt_time in (
        started_at,
        started_at + timedelta(seconds=1),
        started_at + timedelta(seconds=3),
    ):
        assert await process_due_commands(
            publisher,
            now=attempt_time,
            session=session,
        ) == 1

    assert command.status is CommandStatus.SENT
    assert command.attempt_count == 3
    assert command.next_attempt_at == started_at + timedelta(seconds=8)
    assert {
        json.loads(message.payload)["command_id"] for message in publisher.messages
    } == {str(command.id)}
    assert len({message.payload for message in publisher.messages}) == 1

    assert await process_due_commands(
        publisher,
        now=started_at + timedelta(seconds=8),
        session=session,
    ) == 1
    assert command.status is CommandStatus.FAILED
    assert command.last_error == "ACK timeout after 3 publish attempts"
    assert len(publisher.messages) == 3


async def test_publish_error_retries_then_marks_command_failed(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    started_at = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    command = await create_command(session, mapped_topology, started_at)
    publisher = FailingPublisher()

    for attempt_time in (
        started_at,
        started_at + timedelta(seconds=1),
        started_at + timedelta(seconds=3),
    ):
        assert await process_due_commands(
            publisher,
            now=attempt_time,
            session=session,
        ) == 1

    assert publisher.calls == 3
    assert command.status is CommandStatus.FAILED
    assert command.attempt_count == 3
    assert command.sent_at is None
    assert command.last_error == "MQTT publish failed: broker unavailable"
