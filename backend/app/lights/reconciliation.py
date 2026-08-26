from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import ActualState, DesiredState, DeviceStatus
from backend.app.common.errors import APIError
from backend.app.db.models.command import LightCommand
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.session import get_session_factory
from backend.app.lights.commands import enqueue_state_command


def command_is_needed(
    desired_state: DesiredState,
    actual_state: ActualState,
    gateway_status: DeviceStatus,
    controller_status: DeviceStatus,
) -> bool:
    if desired_state.value == actual_state.value:
        return False
    if actual_state is ActualState.UNKNOWN:
        return (
            gateway_status is DeviceStatus.ONLINE
            and controller_status is DeviceStatus.ONLINE
        )
    return True


async def _reconcile_location(
    location_id: UUID,
    reason: str,
    now: datetime,
    session: AsyncSession,
) -> LightCommand | None:
    row = (
        await session.execute(
            select(Location, LampState, Gateway, Controller)
            .join(LampState, LampState.location_id == Location.id)
            .join(Gateway, Gateway.id == Location.gateway_id)
            .join(Controller, Controller.id == Location.controller_id)
            .where(Location.id == location_id)
        )
    ).one_or_none()
    if row is None:
        raise APIError(
            404,
            "LOCATION_STATE_NOT_FOUND",
            f"Location state {location_id} was not found",
        )
    location, lamp_state, gateway, controller = row
    if not location.is_active or not controller.is_active:
        return None
    if not command_is_needed(
        lamp_state.desired_state,
        lamp_state.actual_state,
        gateway.status,
        controller.status,
    ):
        return None
    return await enqueue_state_command(
        location.id,
        lamp_state.desired_state,
        reason,
        now=now,
        session=session,
    )


async def reconcile_location(
    location_id: UUID,
    *,
    reason: str = "RECONCILIATION",
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> LightCommand | None:
    reconciliation_time = now or datetime.now(UTC)
    if session is not None:
        return await _reconcile_location(
            location_id,
            reason,
            reconciliation_time,
            session,
        )

    async with get_session_factory()() as owned_session:
        try:
            command = await _reconcile_location(
                location_id,
                reason,
                reconciliation_time,
                owned_session,
            )
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return command


async def _reconcile_all(
    limit: int,
    now: datetime,
    session: AsyncSession,
) -> int:
    if limit <= 0:
        raise ValueError("limit must be positive")
    location_ids = list(
        await session.scalars(
            select(LampState.location_id)
            .join(Location, Location.id == LampState.location_id)
            .join(Gateway, Gateway.id == Location.gateway_id)
            .join(Controller, Controller.id == Location.controller_id)
            .where(
                Location.is_active.is_(True),
                Controller.is_active.is_(True),
                cast(LampState.desired_state, String)
                != cast(LampState.actual_state, String),
                or_(
                    LampState.actual_state != ActualState.UNKNOWN,
                    and_(
                        Gateway.status == DeviceStatus.ONLINE,
                        Controller.status == DeviceStatus.ONLINE,
                    ),
                ),
            )
            .order_by(LampState.location_id)
            .limit(limit)
        )
    )
    reconciled = 0
    for location_id in location_ids:
        command = await _reconcile_location(
            location_id,
            "RECONCILIATION",
            now,
            session,
        )
        if command is not None:
            reconciled += 1
    return reconciled


async def reconcile_all(
    limit: int = 500,
    *,
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> int:
    reconciliation_time = now or datetime.now(UTC)
    if session is not None:
        return await _reconcile_all(limit, reconciliation_time, session)

    async with get_session_factory()() as owned_session:
        try:
            reconciled = await _reconcile_all(
                limit,
                reconciliation_time,
                owned_session,
            )
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return reconciled
