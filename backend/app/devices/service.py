from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import (
    ActualState,
    ControllerOutputState,
    DeviceStatus,
    LampHealth,
)
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.session import get_session_factory


@dataclass(frozen=True)
class StaleDeviceSweepResult:
    gateways_marked_offline: int
    controllers_marked_offline: int
    locations_marked_unknown: int


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _mark_lamp_unknown(lamp: LampState, now: datetime) -> bool:
    changed = (
        lamp.actual_state is not ActualState.UNKNOWN
        or lamp.controller_output_state is not ControllerOutputState.UNKNOWN
        or lamp.lamp_health is not LampHealth.UNKNOWN
        or lamp.current_ma is not None
    )
    if lamp.actual_state is not ActualState.UNKNOWN:
        lamp.actual_changed_at = now
    lamp.actual_state = ActualState.UNKNOWN
    lamp.controller_output_state = ControllerOutputState.UNKNOWN
    lamp.lamp_health = LampHealth.UNKNOWN
    lamp.current_ma = None
    if changed:
        lamp.version += 1
    return changed


async def _sweep_stale_devices(
    now: datetime,
    offline_after_seconds: int,
    session: AsyncSession,
) -> StaleDeviceSweepResult:
    _require_aware(now, "now")
    if offline_after_seconds <= 0:
        raise ValueError("offline_after_seconds must be positive")
    cutoff = now - timedelta(seconds=offline_after_seconds)

    stale_gateways = list(
        await session.scalars(
            select(Gateway)
            .where(
                Gateway.status == DeviceStatus.ONLINE,
                or_(Gateway.last_seen_at.is_(None), Gateway.last_seen_at < cutoff),
            )
            .with_for_update(skip_locked=True)
        )
    )
    stale_gateway_ids = {gateway.id for gateway in stale_gateways}
    for gateway in stale_gateways:
        gateway.status = DeviceStatus.OFFLINE

    stale_controllers = list(
        await session.scalars(
            select(Controller)
            .where(
                Controller.status == DeviceStatus.ONLINE,
                or_(
                    Controller.gateway_id.in_(stale_gateway_ids),
                    Controller.last_seen_at.is_(None),
                    Controller.last_seen_at < cutoff,
                ),
            )
            .with_for_update(skip_locked=True)
        )
    )
    stale_controller_ids = {controller.id for controller in stale_controllers}
    for controller in stale_controllers:
        controller.status = DeviceStatus.OFFLINE

    if not stale_gateway_ids and not stale_controller_ids:
        return StaleDeviceSweepResult(0, 0, 0)
    lamps = list(
        await session.scalars(
            select(LampState)
            .join(Location, Location.id == LampState.location_id)
            .where(
                or_(
                    Location.gateway_id.in_(stale_gateway_ids),
                    Location.controller_id.in_(stale_controller_ids),
                )
            )
            .with_for_update(skip_locked=True)
        )
    )
    changed_locations = sum(_mark_lamp_unknown(lamp, now) for lamp in lamps)
    await session.flush()
    return StaleDeviceSweepResult(
        gateways_marked_offline=len(stale_gateways),
        controllers_marked_offline=len(stale_controllers),
        locations_marked_unknown=changed_locations,
    )


async def sweep_stale_devices(
    *,
    now: datetime | None = None,
    offline_after_seconds: int = 15,
    session: AsyncSession | None = None,
) -> StaleDeviceSweepResult:
    sweep_time = now or datetime.now(UTC)
    if session is not None:
        return await _sweep_stale_devices(
            sweep_time,
            offline_after_seconds,
            session,
        )

    async with get_session_factory()() as owned_session:
        try:
            result = await _sweep_stale_devices(
                sweep_time,
                offline_after_seconds,
                owned_session,
            )
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return result
