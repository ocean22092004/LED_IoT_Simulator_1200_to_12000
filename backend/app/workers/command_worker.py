import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import CommandStatus
from backend.app.config import get_settings
from backend.app.db.models.command import LightCommand
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.location import Location
from backend.app.db.models.site import Site
from backend.app.db.session import get_session_factory
from backend.app.mqtt.publisher import MQTTPublisher, PahoMQTTPublisher
from backend.app.mqtt.schemas import LightCommandMessage
from backend.app.mqtt.topics import command_topic
from backend.app.realtime.events import publish_realtime_event

BACKOFF_SECONDS = (1, 2, 5)
MAX_PUBLISH_ATTEMPTS = len(BACKOFF_SECONDS)
DEFAULT_POLL_INTERVAL_SECONDS = 0.25


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


async def _command_message(
    command: LightCommand,
    session: AsyncSession,
) -> LightCommandMessage:
    mapping = (
        await session.execute(
            select(Site.code, Gateway.code, Controller.code, Location.code)
            .select_from(Location)
            .join(Site, Site.id == Location.site_id)
            .join(Gateway, Gateway.id == command.gateway_id)
            .join(Controller, Controller.id == command.controller_id)
            .where(Location.id == command.location_id)
        )
    ).one()
    return LightCommandMessage(
        command_id=command.id,
        issued_at=command.created_at,
        site_code=mapping[0],
        gateway_code=mapping[1],
        controller_code=mapping[2],
        channel=command.channel_number,
        target_state=command.target_state,
        location_code=mapping[3],
        reason=command.reason,
    )


async def _process_due_commands(
    publisher: MQTTPublisher,
    now: datetime,
    limit: int,
    session: AsyncSession,
) -> int:
    _require_aware(now, "now")
    if limit <= 0:
        raise ValueError("limit must be positive")

    commands = list(
        await session.scalars(
            select(LightCommand)
            .where(
                LightCommand.status.in_((CommandStatus.PENDING, CommandStatus.SENT)),
                LightCommand.next_attempt_at <= now,
            )
            .order_by(LightCommand.next_attempt_at, LightCommand.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for command in commands:
        if command.attempt_count >= MAX_PUBLISH_ATTEMPTS:
            command.status = CommandStatus.FAILED
            command.last_error = "ACK timeout after 3 publish attempts"
            await publish_realtime_event(
                session,
                "command.failed",
                entity_type="command",
                entity_id=command.id,
                occurred_at=now,
                payload={
                    "location_id": str(command.location_id),
                    "error": command.last_error,
                    "attempt_count": command.attempt_count,
                },
            )
            continue

        message = await _command_message(command, session)
        try:
            await publisher.publish(
                command_topic(message.site_code, message.gateway_code),
                message.model_dump_json(),
                qos=1,
                retain=False,
            )
        except Exception as error:
            command.attempt_count += 1
            command.last_error = f"MQTT publish failed: {error}"
            if command.attempt_count >= MAX_PUBLISH_ATTEMPTS:
                command.status = CommandStatus.FAILED
                await publish_realtime_event(
                    session,
                    "command.failed",
                    entity_type="command",
                    entity_id=command.id,
                    occurred_at=now,
                    payload={
                        "location_id": str(command.location_id),
                        "error": command.last_error,
                        "attempt_count": command.attempt_count,
                    },
                )
            else:
                command.status = CommandStatus.PENDING
                command.next_attempt_at = now + timedelta(
                    seconds=BACKOFF_SECONDS[command.attempt_count - 1]
                )
        else:
            command.attempt_count += 1
            command.status = CommandStatus.SENT
            command.sent_at = command.sent_at or now
            command.last_error = None
            command.next_attempt_at = now + timedelta(
                seconds=BACKOFF_SECONDS[command.attempt_count - 1]
            )
    await session.flush()
    return len(commands)


async def process_due_commands(
    publisher: MQTTPublisher,
    *,
    now: datetime | None = None,
    limit: int = 100,
    session: AsyncSession | None = None,
) -> int:
    processing_time = now or datetime.now(UTC)
    if session is not None:
        return await _process_due_commands(publisher, processing_time, limit, session)

    async with get_session_factory()() as owned_session:
        try:
            processed = await _process_due_commands(
                publisher,
                processing_time,
                limit,
                owned_session,
            )
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return processed


async def run_command_worker() -> None:
    publisher = PahoMQTTPublisher(get_settings())
    try:
        await publisher.start()
        while True:
            processed = await process_due_commands(publisher)
            if processed == 0:
                await asyncio.sleep(DEFAULT_POLL_INTERVAL_SECONDS)
    finally:
        await publisher.close()


def main() -> None:
    asyncio.run(run_command_worker())


if __name__ == "__main__":
    main()
