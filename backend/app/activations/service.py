from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.service import record_audit
from backend.app.common.enums import ActivationReason
from backend.app.common.errors import APIError
from backend.app.db.models.activation import Activation
from backend.app.db.models.location import Location
from backend.app.db.models.user import User
from backend.app.db.session import get_session_factory
from backend.app.lights.reconciliation import reconcile_location
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
            resolution = await resolve_desired_state(location_id, now, session=session)
            if resolution.changed:
                await reconcile_location(
                    location_id,
                    reason=existing.reason.value,
                    now=now,
                    session=session,
                )
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
    resolution = await resolve_desired_state(location_id, now, session=session)
    if resolution.changed:
        await reconcile_location(
            location_id,
            reason=reason.value,
            now=now,
            session=session,
        )
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
    resolution = await resolve_desired_state(
        activation.location_id,
        ended_at,
        session=session,
    )
    if resolution.changed:
        await reconcile_location(
            activation.location_id,
            reason=activation.reason.value,
            now=ended_at,
            session=session,
        )
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


async def _expire_activations(
    now: datetime,
    limit: int,
    session: AsyncSession,
) -> int:
    _require_aware(now, "now")
    if limit <= 0:
        raise ValueError("limit must be positive")
    activations = list(
        await session.scalars(
            select(Activation)
            .where(
                Activation.ended_at.is_(None),
                Activation.expires_at.is_not(None),
                Activation.expires_at <= now,
            )
            .order_by(Activation.expires_at, Activation.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    location_ids = {activation.location_id for activation in activations}
    for activation in activations:
        activation.ended_at = now
    await session.flush()
    for location_id in location_ids:
        resolution = await resolve_desired_state(location_id, now, session=session)
        if resolution.changed:
            await reconcile_location(
                location_id,
                reason="EXPIRY",
                now=now,
                session=session,
            )
    return len(activations)


async def expire_activations(
    *,
    now: datetime | None = None,
    limit: int = 500,
    session: AsyncSession | None = None,
) -> int:
    expiry_time = now or datetime.now(UTC)
    if session is not None:
        return await _expire_activations(expiry_time, limit, session)

    async with get_session_factory()() as owned_session:
        try:
            expired = await _expire_activations(expiry_time, limit, owned_session)
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return expired


async def start_visit(
    session: AsyncSession,
    *,
    location_id: UUID,
    duration_minutes: int | None,
    actor: User,
    idempotency_key: str | None = None,
    now: datetime | None = None,
) -> tuple[Activation, bool]:
    started_at = now or datetime.now(UTC)
    _require_aware(started_at, "now")
    location = await session.scalar(
        select(Location).where(Location.id == location_id).with_for_update()
    )
    if location is None:
        raise APIError(404, "LOCATION_NOT_FOUND", f"Location {location_id} was not found")

    normalized_key = idempotency_key.strip() if idempotency_key is not None else None
    if normalized_key:
        existing = await session.scalar(
            select(Activation)
            .where(
                Activation.location_id == location_id,
                Activation.reason == ActivationReason.VISIT,
                Activation.created_by_user_id == actor.id,
                Activation.created_at >= started_at - timedelta(hours=24),
                Activation.metadata_json["idempotency_key"].as_string() == normalized_key,
            )
            .order_by(Activation.created_at.desc())
        )
        if existing is not None:
            return existing, False

    expires_at = (
        started_at + timedelta(minutes=duration_minutes)
        if duration_minutes is not None
        else None
    )
    dedupe_key = None
    if normalized_key:
        key_hash = sha256(normalized_key.encode()).hexdigest()[:32]
        dedupe_key = f"visit:{actor.id}:{started_at.date().isoformat()}:{key_hash}"
    activation = await create_activation(
        location_id,
        ActivationReason.VISIT,
        starts_at=started_at,
        expires_at=expires_at,
        actor=actor,
        metadata={
            "duration_minutes": duration_minutes,
            **({"idempotency_key": normalized_key} if normalized_key else {}),
        },
        dedupe_key=dedupe_key,
        now=started_at,
        session=session,
    )
    await record_audit(
        session,
        user=actor,
        action="VISIT_STARTED",
        entity_type="activation",
        entity_id=activation.id,
        metadata={
            "location_id": str(location_id),
            "duration_minutes": duration_minutes,
        },
    )
    return activation, True


async def end_visit(
    session: AsyncSession,
    *,
    activation_id: UUID,
    actor: User,
    now: datetime | None = None,
) -> tuple[Activation, bool]:
    ended_at = now or datetime.now(UTC)
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
    if activation.reason is not ActivationReason.VISIT:
        raise APIError(422, "ACTIVATION_NOT_VISIT", "Only VISIT activations can be ended here")
    if activation.ended_at is not None:
        return activation, False
    activation = await end_activation(
        activation.id,
        actor,
        ended_at=ended_at,
        session=session,
    )
    await record_audit(
        session,
        user=actor,
        action="VISIT_ENDED",
        entity_type="activation",
        entity_id=activation.id,
        metadata={"location_id": str(activation.location_id)},
    )
    return activation, True


async def start_manual_on(
    session: AsyncSession,
    *,
    location_id: UUID,
    actor: User,
    now: datetime | None = None,
) -> tuple[Activation, bool]:
    started_at = now or datetime.now(UTC)
    location = await session.scalar(
        select(Location).where(Location.id == location_id).with_for_update()
    )
    if location is None:
        raise APIError(404, "LOCATION_NOT_FOUND", f"Location {location_id} was not found")
    existing = await session.scalar(
        select(Activation)
        .where(
            Activation.location_id == location_id,
            Activation.reason == ActivationReason.MANUAL_ON,
            Activation.starts_at <= started_at,
            Activation.ended_at.is_(None),
            or_(Activation.expires_at.is_(None), Activation.expires_at > started_at),
        )
        .order_by(Activation.created_at.desc())
    )
    if existing is not None:
        return existing, False
    activation = await create_activation(
        location_id,
        ActivationReason.MANUAL_ON,
        starts_at=started_at,
        actor=actor,
        now=started_at,
        session=session,
    )
    await record_audit(
        session,
        user=actor,
        action="MANUAL_ON_STARTED",
        entity_type="activation",
        entity_id=activation.id,
        metadata={"location_id": str(location_id)},
    )
    return activation, True


async def end_manual_on(
    session: AsyncSession,
    *,
    location_id: UUID,
    actor: User,
    now: datetime | None = None,
) -> Activation:
    ended_at = now or datetime.now(UTC)
    if await session.get(Location, location_id) is None:
        raise APIError(404, "LOCATION_NOT_FOUND", f"Location {location_id} was not found")
    activation = await session.scalar(
        select(Activation)
        .where(
            Activation.location_id == location_id,
            Activation.reason == ActivationReason.MANUAL_ON,
            Activation.starts_at <= ended_at,
            Activation.ended_at.is_(None),
            or_(Activation.expires_at.is_(None), Activation.expires_at > ended_at),
        )
        .order_by(Activation.created_at.desc())
        .with_for_update()
    )
    if activation is None:
        raise APIError(
            404,
            "MANUAL_ACTIVATION_NOT_FOUND",
            f"Location {location_id} has no active manual activation",
        )
    activation = await end_activation(
        activation.id,
        actor,
        ended_at=ended_at,
        session=session,
    )
    await record_audit(
        session,
        user=actor,
        action="MANUAL_ON_ENDED",
        entity_type="activation",
        entity_id=activation.id,
        metadata={"location_id": str(location_id)},
    )
    return activation
