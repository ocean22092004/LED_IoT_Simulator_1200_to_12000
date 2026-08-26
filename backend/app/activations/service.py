from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import ActivationReason
from backend.app.common.errors import APIError
from backend.app.db.models.activation import Activation
from backend.app.db.models.location import Location
from backend.app.db.models.user import User
from backend.app.db.session import get_session_factory
from backend.app.lights.resolver import resolve_desired_state


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


async def _create_activation(
    location_id: UUID,
    reason: ActivationReason,
    *,
    starts_at: datetime,
    expires_at: datetime | None,
    actor: User | None,
    metadata: dict[str, Any] | None,
    dedupe_key: str | None,
    now: datetime,
    session: AsyncSession,
) -> Activation:
    _require_aware(starts_at, "starts_at")
    _require_aware(now, "now")
    if expires_at is not None:
        _require_aware(expires_at, "expires_at")
        if expires_at <= starts_at:
            raise ValueError("expires_at must be later than starts_at")
    if await session.get(Location, location_id) is None:
        raise APIError(404, "LOCATION_NOT_FOUND", f"Location {location_id} was not found")

    if dedupe_key is not None:
        existing = await session.scalar(
            select(Activation).where(
                Activation.location_id == location_id,
                Activation.dedupe_key == dedupe_key,
            )
        )
        if existing is not None:
            await resolve_desired_state(location_id, now, session=session)
            return existing

    activation = Activation(
        location_id=location_id,
        reason=reason,
        starts_at=starts_at,
        expires_at=expires_at,
        created_by_user_id=actor.id if actor else None,
        metadata_json=dict(metadata or {}),
        dedupe_key=dedupe_key,
    )
    session.add(activation)
    await session.flush()
    await resolve_desired_state(location_id, now, session=session)
    return activation


async def create_activation(
    location_id: UUID,
    reason: ActivationReason,
    *,
    starts_at: datetime,
    expires_at: datetime | None = None,
    actor: User | None = None,
    metadata: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> Activation:
    resolution_time = now or datetime.now(UTC)
    if session is not None:
        return await _create_activation(
            location_id,
            reason,
            starts_at=starts_at,
            expires_at=expires_at,
            actor=actor,
            metadata=metadata,
            dedupe_key=dedupe_key,
            now=resolution_time,
            session=session,
        )

    async with get_session_factory()() as owned_session:
        try:
            activation = await _create_activation(
                location_id,
                reason,
                starts_at=starts_at,
                expires_at=expires_at,
                actor=actor,
                metadata=metadata,
                dedupe_key=dedupe_key,
                now=resolution_time,
                session=owned_session,
            )
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return activation


async def _end_activation(
    activation_id: UUID,
    actor: User | None,
    ended_at: datetime,
    session: AsyncSession,
) -> Activation:
    _require_aware(ended_at, "ended_at")
    activation = await session.scalar(
        select(Activation)
        .where(Activation.id == activation_id)
        .with_for_update()
    )
    if activation is None:
        raise APIError(
            404,
            "ACTIVATION_NOT_FOUND",
            f"Activation {activation_id} was not found",
        )
    if activation.ended_at is None:
        activation.ended_at = ended_at
        if actor is not None:
            activation.metadata_json = {
                **activation.metadata_json,
                "ended_by_user_id": str(actor.id),
            }
        await session.flush()
    await resolve_desired_state(activation.location_id, ended_at, session=session)
    return activation


async def end_activation(
    activation_id: UUID,
    actor: User | None,
    *,
    ended_at: datetime | None = None,
    session: AsyncSession | None = None,
) -> Activation:
    resolution_time = ended_at or datetime.now(UTC)
    if session is not None:
        return await _end_activation(activation_id, actor, resolution_time, session)

    async with get_session_factory()() as owned_session:
        try:
            activation = await _end_activation(
                activation_id,
                actor,
                resolution_time,
                owned_session,
            )
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return activation
