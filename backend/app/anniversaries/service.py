from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.anniversaries.lunar import (
    LunarCalendarProvider,
    LunarDate,
    default_lunar_calendar,
)
from backend.app.anniversaries.schemas import (
    AnniversariesTodayResponse,
    AnniversaryRuleResponse,
    AnniversaryRuleUpsert,
    AnniversaryTodayItem,
    LunarDateResponse,
)
from backend.app.common.enums import ActivationReason
from backend.app.common.errors import APIError
from backend.app.db.models.activation import Activation
from backend.app.db.models.anniversary import AnniversaryRule
from backend.app.db.models.audit_log import AuditLog
from backend.app.db.models.location import Location
from backend.app.db.models.person import DeceasedPerson
from backend.app.db.models.user import User
from backend.app.db.session import get_session_factory
from backend.app.lights.reconciliation import reconcile_location
from backend.app.lights.resolver import resolve_desired_state
from backend.app.realtime.events import publish_realtime_event

BUSINESS_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


class AnniversaryRuleLike(Protocol):
    lunar_day: int
    lunar_month: int
    is_leap_month: bool
    is_enabled: bool


def anniversary_matches(rule: AnniversaryRuleLike, lunar: LunarDate) -> bool:
    return (
        rule.is_enabled
        and rule.lunar_day == lunar.day
        and rule.lunar_month == lunar.month
        and rule.is_leap_month == lunar.is_leap_month
    )


def _rule_snapshot(rule: AnniversaryRule) -> dict[str, int | bool]:
    return {
        "lunar_day": rule.lunar_day,
        "lunar_month": rule.lunar_month,
        "is_leap_month": rule.is_leap_month,
        "is_enabled": rule.is_enabled,
    }


def _add_rule_audit(
    session: AsyncSession,
    *,
    location_id: UUID,
    user: User,
    before: dict[str, int | bool] | None,
    after: dict[str, int | bool] | None,
) -> None:
    session.add(
        AuditLog(
            user_id=user.id,
            action="ANNIVERSARY_RULE_CHANGED",
            entity_type="location",
            entity_id=location_id,
            metadata_json={"before": before, "after": after},
        )
    )


async def put_anniversary_rule(
    session: AsyncSession,
    location_id: UUID,
    payload: AnniversaryRuleUpsert,
    user: User,
) -> AnniversaryRuleResponse:
    location = await session.get(Location, location_id)
    if location is None:
        raise APIError(404, "LOCATION_NOT_FOUND", f"Location {location_id} was not found")
    if location.person_id is None:
        raise APIError(
            422,
            "ANNIVERSARY_PERSON_REQUIRED",
            "Location must have a deceased person before adding an anniversary rule",
        )

    rule = await session.scalar(
        select(AnniversaryRule).where(AnniversaryRule.location_id == location_id)
    )
    before = _rule_snapshot(rule) if rule else None
    if rule is None:
        rule = AnniversaryRule(
            person_id=location.person_id,
            location_id=location.id,
            **payload.model_dump(),
        )
        session.add(rule)
    else:
        rule.person_id = location.person_id
        for field, value in payload.model_dump().items():
            setattr(rule, field, value)
    await session.flush()
    _add_rule_audit(
        session,
        location_id=location.id,
        user=user,
        before=before,
        after=_rule_snapshot(rule),
    )
    await session.flush()
    return AnniversaryRuleResponse.model_validate(rule)


async def delete_anniversary_rule(
    session: AsyncSession,
    location_id: UUID,
    user: User,
) -> None:
    location = await session.get(Location, location_id)
    if location is None:
        raise APIError(404, "LOCATION_NOT_FOUND", f"Location {location_id} was not found")
    rule = await session.scalar(
        select(AnniversaryRule).where(AnniversaryRule.location_id == location_id)
    )
    if rule is None:
        raise APIError(
            404,
            "ANNIVERSARY_RULE_NOT_FOUND",
            f"Location {location_id} has no anniversary rule",
        )
    before = _rule_snapshot(rule)
    await session.delete(rule)
    _add_rule_audit(
        session,
        location_id=location_id,
        user=user,
        before=before,
        after=None,
    )
    await session.flush()


async def anniversaries_for_local_date(
    session: AsyncSession,
    local_date: date,
    provider: LunarCalendarProvider = default_lunar_calendar,
) -> AnniversariesTodayResponse:
    lunar = provider.from_solar(local_date)
    rows = (
        await session.execute(
            select(AnniversaryRule, Location, DeceasedPerson)
            .join(Location, Location.id == AnniversaryRule.location_id)
            .join(DeceasedPerson, DeceasedPerson.id == AnniversaryRule.person_id)
            .where(
                AnniversaryRule.is_enabled.is_(True),
                AnniversaryRule.lunar_day == lunar.day,
                AnniversaryRule.lunar_month == lunar.month,
                AnniversaryRule.is_leap_month == lunar.is_leap_month,
                Location.is_active.is_(True),
            )
            .order_by(Location.code)
        )
    ).all()
    return AnniversariesTodayResponse(
        local_date=local_date,
        lunar_date=LunarDateResponse(
            year=lunar.year,
            month=lunar.month,
            day=lunar.day,
            is_leap_month=lunar.is_leap_month,
        ),
        items=[
            AnniversaryTodayItem(
                location_id=location.id,
                location_code=location.code,
                person_id=person.id,
                person_name=person.full_name,
                rule_id=rule.id,
            )
            for rule, location, person in rows
        ],
    )


async def _sync_anniversaries(
    local_date: date,
    session: AsyncSession,
    provider: LunarCalendarProvider,
    now: datetime,
) -> int:
    lunar = provider.from_solar(local_date)
    location_ids = list(
        await session.scalars(
            select(AnniversaryRule.location_id)
            .join(Location, Location.id == AnniversaryRule.location_id)
            .where(
                AnniversaryRule.is_enabled.is_(True),
                AnniversaryRule.lunar_day == lunar.day,
                AnniversaryRule.lunar_month == lunar.month,
                AnniversaryRule.is_leap_month == lunar.is_leap_month,
                Location.is_active.is_(True),
            )
        )
    )
    if not location_ids:
        return 0

    starts_at = datetime.combine(local_date, time.min, BUSINESS_TIMEZONE).astimezone(UTC)
    expires_at = datetime.combine(
        local_date + timedelta(days=1),
        time.min,
        BUSINESS_TIMEZONE,
    ).astimezone(UTC)
    dedupe_key = f"anniversary:{local_date.isoformat()}"
    statement = (
        postgresql_insert(Activation)
        .values(
            [
                {
                    "id": uuid4(),
                    "location_id": location_id,
                    "reason": ActivationReason.ANNIVERSARY,
                    "starts_at": starts_at,
                    "expires_at": expires_at,
                    "dedupe_key": dedupe_key,
                    "metadata_json": {
                        "local_date": local_date.isoformat(),
                        "lunar_day": lunar.day,
                        "lunar_month": lunar.month,
                        "is_leap_month": lunar.is_leap_month,
                    },
                }
                for location_id in location_ids
            ]
        )
        .on_conflict_do_nothing(index_elements=["location_id", "dedupe_key"])
        .returning(Activation.id, Activation.location_id)
    )
    inserted_rows = list((await session.execute(statement)).tuples())
    for activation_id, location_id in inserted_rows:
        await publish_realtime_event(
            session,
            "activation.changed",
            entity_type="activation",
            entity_id=activation_id,
            occurred_at=now,
            payload={
                "action": "STARTED",
                "location_id": str(location_id),
                "reason": ActivationReason.ANNIVERSARY.value,
                "starts_at": starts_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
        )
    for location_id in location_ids:
        resolution = await resolve_desired_state(location_id, now, session=session)
        if resolution.changed:
            await reconcile_location(
                location_id,
                reason=ActivationReason.ANNIVERSARY.value,
                now=now,
                session=session,
            )
    return len(inserted_rows)


async def sync_anniversaries_for_local_date(
    local_date: date,
    *,
    session: AsyncSession | None = None,
    provider: LunarCalendarProvider = default_lunar_calendar,
    now: datetime | None = None,
) -> int:
    resolution_time = now or datetime.now(UTC)
    if session is not None:
        return await _sync_anniversaries(local_date, session, provider, resolution_time)

    async with get_session_factory()() as owned_session:
        try:
            inserted = await _sync_anniversaries(
                local_date,
                owned_session,
                provider,
                resolution_time,
            )
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return inserted
