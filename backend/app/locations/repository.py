from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import ActivationReason
from backend.app.db.models.activation import Activation
from backend.app.db.models.anniversary import AnniversaryRule
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.models.person import DeceasedPerson
from backend.app.db.models.zone import Zone


@dataclass(frozen=True)
class LocationRecord:
    location: Location
    zone: Zone
    person: DeceasedPerson | None
    gateway: Gateway
    controller: Controller
    anniversary: AnniversaryRule | None
    lamp_state: LampState | None


def _location_select() -> Select[
    tuple[Location, Zone, DeceasedPerson, Gateway, Controller, LampState]
]:
    return (
        select(Location, Zone, DeceasedPerson, Gateway, Controller, LampState)
        .join(Zone, Zone.id == Location.zone_id)
        .outerjoin(DeceasedPerson, DeceasedPerson.id == Location.person_id)
        .join(Gateway, Gateway.id == Location.gateway_id)
        .join(Controller, Controller.id == Location.controller_id)
        .outerjoin(LampState, LampState.location_id == Location.id)
    )


def _to_record(row: Any) -> LocationRecord:
    location = cast(Location, row[0])
    zone = cast(Zone, row[1])
    person = cast(DeceasedPerson | None, row[2])
    gateway = cast(Gateway, row[3])
    controller = cast(Controller, row[4])
    lamp_state = cast(LampState | None, row[5])
    return LocationRecord(
        location=location,
        zone=zone,
        person=person,
        gateway=gateway,
        controller=controller,
        anniversary=None,
        lamp_state=lamp_state,
    )


async def get_location_record(
    session: AsyncSession,
    location_id: UUID,
) -> LocationRecord | None:
    statement = (
        select(
            Location,
            Zone,
            DeceasedPerson,
            Gateway,
            Controller,
            AnniversaryRule,
            LampState,
        )
        .join(Zone, Zone.id == Location.zone_id)
        .outerjoin(DeceasedPerson, DeceasedPerson.id == Location.person_id)
        .join(Gateway, Gateway.id == Location.gateway_id)
        .join(Controller, Controller.id == Location.controller_id)
        .outerjoin(AnniversaryRule, AnniversaryRule.location_id == Location.id)
        .outerjoin(LampState, LampState.location_id == Location.id)
        .where(Location.id == location_id)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    location, zone, person, gateway, controller, anniversary, lamp_state = row
    return LocationRecord(
        location=location,
        zone=zone,
        person=person,
        gateway=gateway,
        controller=controller,
        anniversary=anniversary,
        lamp_state=lamp_state,
    )


async def list_location_records(
    session: AsyncSession,
    *,
    search: str | None,
    site_id: UUID | None,
    zone_id: UUID | None,
    controller_id: UUID | None,
    page: int,
    page_size: int,
) -> tuple[list[LocationRecord], int]:
    filters = []
    normalized_search = search.strip() if search else None
    if normalized_search:
        pattern = f"%{normalized_search}%"
        filters.append(
            or_(
                Location.code.ilike(pattern),
                DeceasedPerson.full_name.ilike(pattern),
            )
        )
    if site_id is not None:
        filters.append(Location.site_id == site_id)
    if zone_id is not None:
        filters.append(Location.zone_id == zone_id)
    if controller_id is not None:
        filters.append(Location.controller_id == controller_id)

    statement = _location_select().where(*filters)
    if normalized_search:
        statement = statement.order_by(
            case(
                (func.lower(Location.code) == normalized_search.lower(), 0),
                else_=1,
            ),
            Zone.sort_order,
            Location.code,
        )
    else:
        statement = statement.order_by(Zone.sort_order, Location.code)
    statement = statement.offset((page - 1) * page_size).limit(page_size)

    count_statement = (
        select(func.count())
        .select_from(Location)
        .outerjoin(DeceasedPerson, DeceasedPerson.id == Location.person_id)
        .where(*filters)
    )
    rows = (await session.execute(statement)).all()
    total = await session.scalar(count_statement)
    return [_to_record(row) for row in rows], int(total or 0)


async def get_active_reasons(
    session: AsyncSession,
    location_id: UUID,
    now: datetime | None = None,
) -> list[ActivationReason]:
    current_time = now or datetime.now(UTC)
    reasons = await session.scalars(
        select(Activation.reason)
        .where(
            Activation.location_id == location_id,
            Activation.starts_at <= current_time,
            Activation.ended_at.is_(None),
            or_(Activation.expires_at.is_(None), Activation.expires_at > current_time),
        )
        .distinct()
    )
    return sorted(set(reasons), key=lambda reason: reason.value)
