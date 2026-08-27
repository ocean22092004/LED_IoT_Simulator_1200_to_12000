from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import ActivationReason, DesiredState
from backend.app.common.errors import APIError
from backend.app.db.models.activation import Activation
from backend.app.db.models.lamp_state import LampState
from backend.app.db.session import get_session_factory
from backend.app.realtime.events import publish_realtime_event


@dataclass(frozen=True)
class DesiredStateResult:
    desired_state: Literal["ON", "OFF"]
    active_reasons: tuple[str, ...]
    changed: bool


def calculate_desired_state(
    active_reasons: Iterable[ActivationReason],
    current_desired_state: DesiredState,
) -> DesiredStateResult:
    reason_values = tuple(sorted({reason.value for reason in active_reasons}))
    desired_state: Literal["ON", "OFF"] = "ON" if reason_values else "OFF"
    return DesiredStateResult(
        desired_state=desired_state,
        active_reasons=reason_values,
        changed=current_desired_state.value != desired_state,
    )


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


async def _resolve_desired_state(
    location_id: UUID,
    now: datetime,
    session: AsyncSession,
) -> DesiredStateResult:
    _require_aware(now, "now")
    lamp_state = await session.scalar(
        select(LampState)
        .where(LampState.location_id == location_id)
        .with_for_update()
    )
    if lamp_state is None:
        raise APIError(
            404,
            "LAMP_STATE_NOT_FOUND",
            f"Lamp state for location {location_id} was not found",
        )

    active_reasons = list(
        await session.scalars(
            select(Activation.reason).where(
                Activation.location_id == location_id,
                Activation.starts_at <= now,
                Activation.ended_at.is_(None),
                or_(Activation.expires_at.is_(None), Activation.expires_at > now),
            )
        )
    )
    result = calculate_desired_state(active_reasons, lamp_state.desired_state)
    if result.changed:
        lamp_state.desired_state = DesiredState(result.desired_state)
        lamp_state.desired_changed_at = now
        lamp_state.version += 1
        await session.flush()
        await publish_realtime_event(
            session,
            "location.state_changed",
            entity_type="location",
            entity_id=location_id,
            occurred_at=now,
            payload={
                "desired_state": lamp_state.desired_state.value,
                "actual_state": lamp_state.actual_state.value,
                "active_reasons": list(result.active_reasons),
                "version": lamp_state.version,
            },
        )
    return result


async def resolve_desired_state(
    location_id: UUID,
    now: datetime,
    *,
    session: AsyncSession | None = None,
) -> DesiredStateResult:
    if session is not None:
        return await _resolve_desired_state(location_id, now, session)

    async with get_session_factory()() as owned_session:
        try:
            result = await _resolve_desired_state(location_id, now, owned_session)
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return result
