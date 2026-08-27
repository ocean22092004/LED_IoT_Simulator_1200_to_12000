from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import ActualState, DesiredState, LampHealth
from backend.app.common.errors import APIError
from backend.app.db.models.activation import Activation
from backend.app.db.models.audit_log import AuditLog
from backend.app.db.models.command import LightCommand
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.device_event import DeviceEvent
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.models.person import DeceasedPerson
from backend.app.db.models.site import Site
from backend.app.db.models.user import User
from backend.app.db.models.zone import Zone
from backend.app.locations.repository import (
    LocationRecord,
    get_active_reasons,
    get_location_record,
    list_location_records,
)
from backend.app.locations.schemas import (
    ActiveActivationBrief,
    AnniversaryBrief,
    HardwareBrief,
    LightBrief,
    LocationCommandBrief,
    LocationCreate,
    LocationDetail,
    LocationEventBrief,
    LocationListLightBrief,
    LocationSummary,
    LocationUpdate,
    PaginatedLocations,
    PersonBrief,
    PersonCreate,
    PersonResponse,
    PersonUpdate,
    ZoneBrief,
)

MAPPING_FIELDS = {
    "site_id",
    "zone_id",
    "gateway_id",
    "controller_id",
    "channel_number",
}


def _mapping_error(message: str, **details: Any) -> APIError:
    return APIError(422, "LOCATION_MAPPING_INVALID", message, details)


async def _validate_mapping(
    session: AsyncSession,
    *,
    site_id: UUID,
    zone_id: UUID,
    gateway_id: UUID,
    controller_id: UUID,
    channel_number: int,
    person_id: UUID | None,
    exclude_location_id: UUID | None = None,
) -> None:
    site = await session.get(Site, site_id)
    zone = await session.get(Zone, zone_id)
    gateway = await session.get(Gateway, gateway_id)
    controller = await session.get(Controller, controller_id)
    person = await session.get(DeceasedPerson, person_id) if person_id else None

    if site is None:
        raise _mapping_error("Site does not exist", site_id=str(site_id))
    if zone is None or zone.site_id != site_id or not zone.is_active:
        raise _mapping_error("Zone is not active in the selected site", zone_id=str(zone_id))
    if (
        gateway is None
        or gateway.site_id != site_id
        or (gateway.zone_id is not None and gateway.zone_id != zone_id)
    ):
        raise _mapping_error(
            "Gateway does not belong to the selected site and zone",
            gateway_id=str(gateway_id),
        )
    if controller is None or controller.gateway_id != gateway_id or not controller.is_active:
        raise _mapping_error(
            "Controller is not active on the selected gateway",
            controller_id=str(controller_id),
        )
    if channel_number > controller.channel_capacity:
        raise _mapping_error(
            "Channel exceeds controller capacity",
            channel_number=channel_number,
            channel_capacity=controller.channel_capacity,
        )
    if person_id is not None and (person is None or person.site_id != site_id):
        raise _mapping_error(
            "Person does not belong to the selected site",
            person_id=str(person_id),
        )

    occupied_statement = select(Location.id).where(
        Location.controller_id == controller_id,
        Location.channel_number == channel_number,
    )
    if exclude_location_id is not None:
        occupied_statement = occupied_statement.where(Location.id != exclude_location_id)
    if await session.scalar(occupied_statement) is not None:
        raise _mapping_error(
            "Controller channel is already mapped to another location",
            controller_id=str(controller_id),
            channel_number=channel_number,
        )


def _summary(record: LocationRecord) -> LocationSummary:
    lamp_state = record.lamp_state
    return LocationSummary(
        id=record.location.id,
        site_id=record.location.site_id,
        code=record.location.code,
        zone=ZoneBrief(code=record.zone.code, name=record.zone.name),
        person=(
            PersonBrief(id=record.person.id, full_name=record.person.full_name)
            if record.person
            else None
        ),
        hardware=HardwareBrief(
            gateway_code=record.gateway.code,
            controller_code=record.controller.code,
            channel=record.location.channel_number,
        ),
        light=LocationListLightBrief(
            desired_state=(
                lamp_state.desired_state if lamp_state else DesiredState.OFF
            ),
            actual_state=(
                lamp_state.actual_state if lamp_state else ActualState.UNKNOWN
            ),
            lamp_health=(
                lamp_state.lamp_health if lamp_state else LampHealth.UNKNOWN
            ),
        ),
        is_active=record.location.is_active,
    )


async def _detail(session: AsyncSession, record: LocationRecord) -> LocationDetail:
    lamp_state = record.lamp_state
    now = datetime.now(UTC)
    activations = list(
        await session.scalars(
            select(Activation)
            .where(
                Activation.location_id == record.location.id,
                Activation.starts_at <= now,
                Activation.ended_at.is_(None),
                or_(Activation.expires_at.is_(None), Activation.expires_at > now),
            )
            .order_by(Activation.reason, Activation.starts_at, Activation.id)
        )
    )
    commands = list(
        await session.scalars(
            select(LightCommand)
            .where(LightCommand.location_id == record.location.id)
            .order_by(LightCommand.created_at.desc(), LightCommand.id.desc())
            .limit(10)
        )
    )
    events = list(
        await session.scalars(
            select(DeviceEvent)
            .where(DeviceEvent.location_id == record.location.id)
            .order_by(DeviceEvent.occurred_at.desc(), DeviceEvent.id.desc())
            .limit(10)
        )
    )
    return LocationDetail(
        **_summary(record).model_dump(exclude={"light"}),
        anniversary=(
            AnniversaryBrief(
                lunar_day=record.anniversary.lunar_day,
                lunar_month=record.anniversary.lunar_month,
                is_leap_month=record.anniversary.is_leap_month,
            )
            if record.anniversary
            else None
        ),
        light=LightBrief(
            desired_state=lamp_state.desired_state if lamp_state else DesiredState.OFF,
            actual_state=lamp_state.actual_state if lamp_state else ActualState.UNKNOWN,
            lamp_health=lamp_state.lamp_health if lamp_state else LampHealth.UNKNOWN,
            current_ma=lamp_state.current_ma if lamp_state else None,
            active_reasons=await get_active_reasons(session, record.location.id),
            last_reported_at=(
                lamp_state.last_device_report_at if lamp_state else None
            ),
        ),
        active_activations=[
            ActiveActivationBrief(
                id=activation.id,
                reason=activation.reason,
                starts_at=activation.starts_at,
                expires_at=activation.expires_at,
            )
            for activation in activations
        ],
        recent_commands=[
            LocationCommandBrief(
                id=command.id,
                target_state=command.target_state,
                status=command.status,
                reason=command.reason,
                attempt_count=command.attempt_count,
                last_error=command.last_error,
                created_at=command.created_at,
                sent_at=command.sent_at,
                acked_at=command.acked_at,
            )
            for command in commands
        ],
        recent_events=[
            LocationEventBrief(
                id=event.id,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                received_at=event.received_at,
                payload=event.payload,
            )
            for event in events
        ],
    )


async def search_locations(
    session: AsyncSession,
    *,
    search: str | None,
    site_id: UUID | None,
    zone_id: UUID | None,
    controller_id: UUID | None,
    page: int,
    page_size: int,
) -> PaginatedLocations:
    records, total = await list_location_records(
        session,
        search=search,
        site_id=site_id,
        zone_id=zone_id,
        controller_id=controller_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedLocations(
        items=[_summary(record) for record in records],
        page=page,
        page_size=page_size,
        total=total,
    )


async def get_location(session: AsyncSession, location_id: UUID) -> LocationDetail:
    record = await get_location_record(session, location_id)
    if record is None:
        raise APIError(404, "LOCATION_NOT_FOUND", f"Location {location_id} was not found")
    return await _detail(session, record)


def _mapping_snapshot(location: Location) -> dict[str, str | int]:
    return {
        "site_id": str(location.site_id),
        "zone_id": str(location.zone_id),
        "gateway_id": str(location.gateway_id),
        "controller_id": str(location.controller_id),
        "channel_number": location.channel_number,
    }


def _add_mapping_audit(
    session: AsyncSession,
    *,
    location: Location,
    user: User,
    before: dict[str, str | int] | None,
) -> None:
    session.add(
        AuditLog(
            user_id=user.id,
            action="LOCATION_MAPPING_CHANGED",
            entity_type="location",
            entity_id=location.id,
            metadata_json={"before": before, "after": _mapping_snapshot(location)},
        )
    )


async def create_location(
    session: AsyncSession,
    payload: LocationCreate,
    user: User,
) -> LocationDetail:
    values = payload.model_dump()
    values["code"] = payload.code.upper()
    await _validate_mapping(
        session,
        site_id=payload.site_id,
        zone_id=payload.zone_id,
        gateway_id=payload.gateway_id,
        controller_id=payload.controller_id,
        channel_number=payload.channel_number,
        person_id=payload.person_id,
    )
    if await session.scalar(
        select(Location.id).where(
            Location.site_id == payload.site_id,
            Location.code == values["code"],
        )
    ):
        raise APIError(409, "LOCATION_CODE_CONFLICT", "Location code already exists")

    location = Location(**values)
    session.add(location)
    try:
        await session.flush()
    except IntegrityError as error:
        raise APIError(409, "LOCATION_CONFLICT", "Location mapping already exists") from error
    session.add(LampState(location_id=location.id))
    _add_mapping_audit(session, location=location, user=user, before=None)
    await session.flush()
    return await get_location(session, location.id)


async def update_location(
    session: AsyncSession,
    location_id: UUID,
    payload: LocationUpdate,
    user: User,
) -> LocationDetail:
    location = await session.get(Location, location_id)
    if location is None:
        raise APIError(404, "LOCATION_NOT_FOUND", f"Location {location_id} was not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("code") is not None:
        changes["code"] = str(changes["code"]).upper()

    target = {
        "site_id": changes.get("site_id", location.site_id),
        "zone_id": changes.get("zone_id", location.zone_id),
        "gateway_id": changes.get("gateway_id", location.gateway_id),
        "controller_id": changes.get("controller_id", location.controller_id),
        "channel_number": changes.get("channel_number", location.channel_number),
        "person_id": changes.get("person_id", location.person_id),
    }
    await _validate_mapping(
        session,
        **target,
        exclude_location_id=location.id,
    )
    code = changes.get("code")
    if code is not None and await session.scalar(
        select(Location.id).where(
            Location.site_id == target["site_id"],
            Location.code == code,
            Location.id != location.id,
        )
    ):
        raise APIError(409, "LOCATION_CODE_CONFLICT", "Location code already exists")

    before = _mapping_snapshot(location)
    mapping_changed = bool(MAPPING_FIELDS.intersection(changes))
    for field, value in changes.items():
        setattr(location, field, value)
    if mapping_changed:
        _add_mapping_audit(session, location=location, user=user, before=before)
    try:
        await session.flush()
    except IntegrityError as error:
        raise APIError(409, "LOCATION_CONFLICT", "Location mapping already exists") from error
    return await get_location(session, location.id)


async def create_person(session: AsyncSession, payload: PersonCreate) -> PersonResponse:
    if await session.get(Site, payload.site_id) is None:
        raise APIError(422, "PERSON_SITE_INVALID", "Site does not exist")
    person = DeceasedPerson(**payload.model_dump())
    session.add(person)
    await session.flush()
    return PersonResponse.model_validate(person)


async def update_person(
    session: AsyncSession,
    person_id: UUID,
    payload: PersonUpdate,
) -> PersonResponse:
    person = await session.get(DeceasedPerson, person_id)
    if person is None:
        raise APIError(404, "PERSON_NOT_FOUND", f"Person {person_id} was not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(person, field, value)
    await session.flush()
    return PersonResponse.model_validate(person)
