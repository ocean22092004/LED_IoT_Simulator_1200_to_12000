from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.anniversaries.lunar import (
    LunarCalendarProvider,
    default_lunar_calendar,
)
from backend.app.anniversaries.service import BUSINESS_TIMEZONE
from backend.app.db.models.anniversary import AnniversaryRule

ANNIVERSARY_NAMESPACE = UUID("a034abbe-1cd7-54a2-a460-ed04830c4be7")
ANNIVERSARY_SEED_RATIO = 0.05


async def seed_anniversary_rules(
    session: AsyncSession,
    location_people: Sequence[tuple[UUID, UUID]],
    provider: LunarCalendarProvider = default_lunar_calendar,
) -> int:
    target_count = max(1, int(len(location_people) * ANNIVERSARY_SEED_RATIO))
    selected = location_people[:target_count]
    lunar_today = provider.from_solar(datetime.now(BUSINESS_TIMEZONE).date())
    rows = [
        {
            "id": uuid5(ANNIVERSARY_NAMESPACE, str(location_id)),
            "person_id": person_id,
            "location_id": location_id,
            "lunar_day": lunar_today.day,
            "lunar_month": lunar_today.month,
            "is_leap_month": lunar_today.is_leap_month,
            "is_enabled": True,
        }
        for location_id, person_id in selected
    ]
    if not rows:
        return 0
    excluded = postgresql_insert(AnniversaryRule).excluded
    statement = (
        postgresql_insert(AnniversaryRule)
        .values(rows)
        .on_conflict_do_update(
            index_elements=["location_id"],
            set_={
                "person_id": excluded.person_id,
                "lunar_day": excluded.lunar_day,
                "lunar_month": excluded.lunar_month,
                "is_leap_month": excluded.is_leap_month,
                "is_enabled": excluded.is_enabled,
            },
            where=AnniversaryRule.id == excluded.id,
        )
    )
    await session.execute(statement)
    return len(rows)
