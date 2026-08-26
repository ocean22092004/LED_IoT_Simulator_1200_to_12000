from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import CommandStatus, DesiredState
from backend.app.common.errors import APIError
from backend.app.db.models.command import LightCommand
from backend.app.db.models.location import Location
from backend.app.db.session import get_session_factory

IN_FLIGHT_COMMAND_STATUSES = (CommandStatus.PENDING, CommandStatus.SENT)


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


async def _enqueue_state_command(
    location_id: UUID,
    target_state: DesiredState,
    reason: str,
    now: datetime,
    session: AsyncSession,
) -> LightCommand:
    _require_aware(now, "now")
    normalized_reason = reason.strip()
    if not 1 <= len(normalized_reason) <= 64:
        raise ValueError("reason must contain between 1 and 64 characters")

    location = await session.scalar(
        select(Location)
        .where(Location.id == location_id)
        .with_for_update()
    )
    if location is None:
        raise APIError(404, "LOCATION_NOT_FOUND", f"Location {location_id} was not found")

    existing = await session.scalar(
        select(LightCommand)
        .where(
            LightCommand.location_id == location_id,
            LightCommand.target_state == target_state,
            LightCommand.status.in_(IN_FLIGHT_COMMAND_STATUSES),
        )
        .order_by(LightCommand.created_at.desc())
    )
    if existing is not None:
        return existing

    command = LightCommand(
        location_id=location.id,
        gateway_id=location.gateway_id,
        controller_id=location.controller_id,
        channel_number=location.channel_number,
        target_state=target_state,
        status=CommandStatus.PENDING,
        reason=normalized_reason,
        attempt_count=0,
        next_attempt_at=now,
    )
    session.add(command)
    await session.flush()
    return command


async def enqueue_state_command(
    location_id: UUID,
    target_state: DesiredState | str,
    reason: str,
    *,
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> LightCommand:
    try:
        normalized_target = DesiredState(target_state)
    except ValueError as error:
        raise ValueError("target_state must be ON or OFF") from error
    enqueue_time = now or datetime.now(UTC)

    if session is not None:
        return await _enqueue_state_command(
            location_id,
            normalized_target,
            reason,
            enqueue_time,
            session,
        )

    async with get_session_factory()() as owned_session:
        try:
            command = await _enqueue_state_command(
                location_id,
                normalized_target,
                reason,
                enqueue_time,
                owned_session,
            )
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return command
