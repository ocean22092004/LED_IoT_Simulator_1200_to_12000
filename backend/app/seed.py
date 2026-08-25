import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.app.config import Settings, get_settings
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.models.person import DeceasedPerson
from backend.app.db.models.site import Site
from backend.app.db.models.zone import Zone
from backend.app.db.session import get_session_factory

SITE_CODE = "SITE-001"
SITE_NAME = "Nghĩa trang mô phỏng"
SITE_TIMEZONE = "Asia/Ho_Chi_Minh"
SEED_NAMESPACE = UUID("9d4e12a5-0e49-5f79-9a43-7fd7aa1d2b77")
BATCH_SIZE = 1_000


class SeedTopologyConflict(RuntimeError):
    """Raised when a populated site would need destructive topology changes."""


@dataclass(frozen=True)
class SeedResult:
    site_count: int
    zone_count: int
    gateway_count: int
    controller_count: int
    location_count: int
    person_count: int
    lamp_state_count: int


@dataclass(frozen=True)
class HardwareMapping:
    zone_code: str
    gateway_code: str
    controller_code: str
    controller_address: int
    channel_number: int


def excel_zone_code(index: int) -> str:
    if index <= 0:
        raise ValueError("zone index must be positive")

    code = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        code = chr(ord("A") + remainder) + code
    return code


def mapping_for_location(
    location_number: int,
    locations_per_zone: int = 300,
    controller_capacity: int = 64,
) -> HardwareMapping:
    if location_number <= 0:
        raise ValueError("location number must be positive")
    if locations_per_zone <= 0:
        raise ValueError("locations per zone must be positive")
    if controller_capacity <= 0:
        raise ValueError("controller capacity must be positive")

    zone_index = (location_number - 1) // locations_per_zone + 1
    index_in_zone = (location_number - 1) % locations_per_zone + 1
    controller_address = (index_in_zone - 1) // controller_capacity + 1
    channel_number = (index_in_zone - 1) % controller_capacity + 1
    zone_code = excel_zone_code(zone_index)

    return HardwareMapping(
        zone_code=zone_code,
        gateway_code=f"GW-{zone_code}",
        controller_code=f"CTRL-{zone_code}-{controller_address:02d}",
        controller_address=controller_address,
        channel_number=channel_number,
    )


def _seed_uuid(entity: str, natural_key: str) -> UUID:
    return uuid5(SEED_NAMESPACE, f"{SITE_CODE}:{entity}:{natural_key}")


def _topology_conflict(detail: str) -> SeedTopologyConflict:
    return SeedTopologyConflict(
        f"{SITE_CODE} already contains a different topology ({detail}); "
        "run `make reset-db`, then migrate and seed again"
    )


async def _insert_batches(
    session: AsyncSession,
    table: Any,
    rows: Sequence[dict[str, Any]],
    conflict_columns: Sequence[str],
) -> None:
    for start in range(0, len(rows), BATCH_SIZE):
        statement = (
            postgresql_insert(table)
            .values(rows[start : start + BATCH_SIZE])
            .on_conflict_do_nothing(index_elements=list(conflict_columns))
        )
        await session.execute(statement)


async def _validate_existing_topology(
    session: AsyncSession,
    site_id: UUID,
    expected_mappings: dict[str, HardwareMapping],
    controller_capacity: int,
) -> None:
    expected_zones = {mapping.zone_code for mapping in expected_mappings.values()}
    expected_people = {_seed_uuid("person", location_code) for location_code in expected_mappings}

    zone_result = await session.execute(select(Zone.code).where(Zone.site_id == site_id))
    if set(zone_result.scalars()) != expected_zones:
        raise _topology_conflict("zone set does not match")

    gateway_result = await session.execute(
        select(Gateway.code, Zone.code)
        .join(Zone, Zone.id == Gateway.zone_id)
        .where(Gateway.site_id == site_id)
    )
    existing_gateways = {gateway_code: zone_code for gateway_code, zone_code in gateway_result}
    if existing_gateways != {
        mapping.gateway_code: mapping.zone_code for mapping in expected_mappings.values()
    }:
        raise _topology_conflict("gateway set or zone relationship does not match")

    controller_result = await session.execute(
        select(
            Gateway.code,
            Controller.code,
            Controller.address,
            Controller.channel_capacity,
        )
        .join(Gateway, Gateway.id == Controller.gateway_id)
        .where(Gateway.site_id == site_id)
    )
    existing_controllers = {
        (gateway_code, code, address, capacity)
        for gateway_code, code, address, capacity in controller_result
    }
    expected_controller_rows = {
        (
            mapping.gateway_code,
            mapping.controller_code,
            mapping.controller_address,
            controller_capacity,
        )
        for mapping in expected_mappings.values()
    }
    if existing_controllers != expected_controller_rows:
        raise _topology_conflict("controller set, parent, or capacity does not match")

    person_result = await session.execute(
        select(DeceasedPerson.id).where(DeceasedPerson.site_id == site_id)
    )
    if set(person_result.scalars()) != expected_people:
        raise _topology_conflict("person set does not match")

    location_gateway = aliased(Gateway)
    controller_gateway = aliased(Gateway)
    location_result = await session.execute(
        select(
            Location.id,
            Location.code,
            Location.person_id,
            Zone.code,
            location_gateway.code,
            Controller.code,
            Controller.address,
            Location.channel_number,
            controller_gateway.code,
        )
        .join(Zone, Zone.id == Location.zone_id)
        .join(location_gateway, location_gateway.id == Location.gateway_id)
        .join(Controller, Controller.id == Location.controller_id)
        .join(controller_gateway, controller_gateway.id == Controller.gateway_id)
        .where(Location.site_id == site_id)
    )
    existing_mappings = {
        location_code: (
            location_id,
            person_id,
            HardwareMapping(
                zone_code=zone_code,
                gateway_code=gateway_code,
                controller_code=controller_code,
                controller_address=controller_address,
                channel_number=channel_number,
            ),
            controller_gateway_code,
        )
        for (
            location_id,
            location_code,
            person_id,
            zone_code,
            gateway_code,
            controller_code,
            controller_address,
            channel_number,
            controller_gateway_code,
        ) in location_result
    }
    expected_location_rows = {
        location_code: (
            _seed_uuid("location", location_code),
            _seed_uuid("person", location_code),
            mapping,
            mapping.gateway_code,
        )
        for location_code, mapping in expected_mappings.items()
    }
    if existing_mappings != expected_location_rows:
        raise _topology_conflict("location identity or mapping does not match")


async def _count_existing_topology(session: AsyncSession, site_id: UUID) -> tuple[int, int]:
    location_count = await session.scalar(
        select(func.count()).select_from(Location).where(Location.site_id == site_id)
    )
    zone_count = await session.scalar(
        select(func.count()).select_from(Zone).where(Zone.site_id == site_id)
    )
    gateway_count = await session.scalar(
        select(func.count()).select_from(Gateway).where(Gateway.site_id == site_id)
    )
    controller_count = await session.scalar(
        select(func.count())
        .select_from(Controller)
        .join(Gateway, Gateway.id == Controller.gateway_id)
        .where(Gateway.site_id == site_id)
    )
    person_count = await session.scalar(
        select(func.count()).select_from(DeceasedPerson).where(DeceasedPerson.site_id == site_id)
    )
    return int(location_count or 0), int(zone_count or 0) + int(gateway_count or 0) + int(
        controller_count or 0
    ) + int(person_count or 0)


def _build_expected_mappings(
    location_count: int,
    locations_per_zone: int,
    controller_capacity: int,
) -> dict[str, HardwareMapping]:
    expected: dict[str, HardwareMapping] = {}
    for location_number in range(1, location_count + 1):
        mapping = mapping_for_location(
            location_number,
            locations_per_zone=locations_per_zone,
            controller_capacity=controller_capacity,
        )
        index_in_zone = (location_number - 1) % locations_per_zone + 1
        expected[f"{mapping.zone_code}{index_in_zone:03d}"] = mapping
    return expected


async def _seed_simulator(
    location_count: int,
    locations_per_zone: int,
    controller_capacity: int,
    session: AsyncSession,
) -> SeedResult:
    if location_count <= 0:
        raise ValueError("location count must be positive")
    if locations_per_zone <= 0:
        raise ValueError("locations per zone must be positive")
    if controller_capacity <= 0:
        raise ValueError("controller capacity must be positive")

    expected_mappings = _build_expected_mappings(
        location_count,
        locations_per_zone,
        controller_capacity,
    )
    zone_codes = sorted(
        {mapping.zone_code for mapping in expected_mappings.values()},
        key=lambda code: (len(code), code),
    )

    await _insert_batches(
        session,
        Site.__table__,
        [
            {
                "id": _seed_uuid("site", SITE_CODE),
                "code": SITE_CODE,
                "name": SITE_NAME,
                "timezone": SITE_TIMEZONE,
            }
        ],
        ["code"],
    )
    site_result = await session.execute(
        select(Site.id, Site.timezone).where(Site.code == SITE_CODE).with_for_update()
    )
    site_row = site_result.one_or_none()
    if site_row is None:
        raise RuntimeError(f"failed to create or find {SITE_CODE}")
    site_id, site_timezone = site_row
    if site_timezone != SITE_TIMEZONE:
        raise _topology_conflict(f"site timezone is {site_timezone!r}, expected {SITE_TIMEZONE!r}")

    existing_location_count, existing_hardware_count = await _count_existing_topology(
        session, site_id
    )
    if existing_location_count not in (0, location_count):
        raise _topology_conflict(
            f"found {existing_location_count} locations, requested {location_count}"
        )
    if existing_location_count == 0 and existing_hardware_count:
        raise _topology_conflict("hardware exists without locations")
    if existing_location_count:
        await _validate_existing_topology(
            session,
            site_id,
            expected_mappings,
            controller_capacity,
        )

    await _insert_batches(
        session,
        Zone.__table__,
        [
            {
                "id": _seed_uuid("zone", zone_code),
                "site_id": site_id,
                "code": zone_code,
                "name": f"Khu {zone_code}",
                "sort_order": index,
            }
            for index, zone_code in enumerate(zone_codes, start=1)
        ],
        ["site_id", "code"],
    )
    zone_result = await session.execute(
        select(Zone.code, Zone.id).where(
            Zone.site_id == site_id,
            Zone.code.in_(zone_codes),
        )
    )
    zone_ids = {code: identifier for code, identifier in zone_result}
    if set(zone_ids) != set(zone_codes):
        raise _topology_conflict("unable to resolve all zones")

    await _insert_batches(
        session,
        Gateway.__table__,
        [
            {
                "id": _seed_uuid("gateway", f"GW-{zone_code}"),
                "site_id": site_id,
                "zone_id": zone_ids[zone_code],
                "code": f"GW-{zone_code}",
                "name": f"Gateway {zone_code}",
            }
            for zone_code in zone_codes
        ],
        ["site_id", "code"],
    )
    gateway_codes = [f"GW-{zone_code}" for zone_code in zone_codes]
    gateway_result = await session.execute(
        select(Gateway.code, Gateway.id).where(
            Gateway.site_id == site_id,
            Gateway.code.in_(gateway_codes),
        )
    )
    gateway_ids = {code: identifier for code, identifier in gateway_result}
    if set(gateway_ids) != set(gateway_codes):
        raise _topology_conflict("unable to resolve all gateways")

    controller_mappings = {
        mapping.controller_code: mapping for mapping in expected_mappings.values()
    }
    await _insert_batches(
        session,
        Controller.__table__,
        [
            {
                "id": _seed_uuid("controller", code),
                "gateway_id": gateway_ids[mapping.gateway_code],
                "code": code,
                "address": mapping.controller_address,
                "channel_capacity": controller_capacity,
            }
            for code, mapping in controller_mappings.items()
        ],
        ["gateway_id", "code"],
    )
    controller_result = await session.execute(
        select(Controller.code, Controller.id)
        .join(Gateway, Gateway.id == Controller.gateway_id)
        .where(
            Gateway.site_id == site_id,
            Controller.code.in_(list(controller_mappings)),
        )
    )
    controller_ids = {code: identifier for code, identifier in controller_result}
    if set(controller_ids) != set(controller_mappings):
        raise _topology_conflict("unable to resolve all controllers")

    person_rows: list[dict[str, Any]] = []
    location_rows: list[dict[str, Any]] = []
    lamp_state_rows: list[dict[str, Any]] = []
    for location_code, mapping in expected_mappings.items():
        person_id = _seed_uuid("person", location_code)
        location_id = _seed_uuid("location", location_code)
        person_rows.append(
            {
                "id": person_id,
                "site_id": site_id,
                "full_name": f"Người đã khuất {location_code}",
            }
        )
        location_rows.append(
            {
                "id": location_id,
                "site_id": site_id,
                "zone_id": zone_ids[mapping.zone_code],
                "code": location_code,
                "person_id": person_id,
                "gateway_id": gateway_ids[mapping.gateway_code],
                "controller_id": controller_ids[mapping.controller_code],
                "channel_number": mapping.channel_number,
            }
        )
        lamp_state_rows.append({"location_id": location_id})

    await _insert_batches(session, DeceasedPerson.__table__, person_rows, ["id"])
    await _insert_batches(
        session,
        Location.__table__,
        location_rows,
        ["site_id", "code"],
    )
    await _insert_batches(
        session,
        LampState.__table__,
        lamp_state_rows,
        ["location_id"],
    )
    await session.flush()

    site_count = await session.scalar(
        select(func.count()).select_from(Site).where(Site.code == SITE_CODE)
    )
    zone_count = await session.scalar(
        select(func.count()).select_from(Zone).where(Zone.site_id == site_id)
    )
    gateway_count = await session.scalar(
        select(func.count()).select_from(Gateway).where(Gateway.site_id == site_id)
    )
    controller_count = await session.scalar(
        select(func.count())
        .select_from(Controller)
        .join(Gateway, Gateway.id == Controller.gateway_id)
        .where(Gateway.site_id == site_id)
    )
    persisted_location_count = await session.scalar(
        select(func.count()).select_from(Location).where(Location.site_id == site_id)
    )
    person_count = await session.scalar(
        select(func.count()).select_from(DeceasedPerson).where(DeceasedPerson.site_id == site_id)
    )
    lamp_state_count = await session.scalar(
        select(func.count())
        .select_from(LampState)
        .join(Location, Location.id == LampState.location_id)
        .where(Location.site_id == site_id)
    )

    return SeedResult(
        site_count=int(site_count or 0),
        zone_count=int(zone_count or 0),
        gateway_count=int(gateway_count or 0),
        controller_count=int(controller_count or 0),
        location_count=int(persisted_location_count or 0),
        person_count=int(person_count or 0),
        lamp_state_count=int(lamp_state_count or 0),
    )


async def seed_simulator(
    location_count: int,
    locations_per_zone: int = 300,
    controller_capacity: int = 64,
    *,
    session: AsyncSession | None = None,
) -> SeedResult:
    if session is not None:
        return await _seed_simulator(
            location_count,
            locations_per_zone,
            controller_capacity,
            session,
        )

    async with get_session_factory()() as owned_session:
        try:
            result = await _seed_simulator(
                location_count,
                locations_per_zone,
                controller_capacity,
                owned_session,
            )
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return result


def _parser(settings: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed deterministic simulator topology")
    parser.add_argument(
        "--locations",
        type=int,
        default=settings.simulator_location_count,
    )
    parser.add_argument(
        "--locations-per-zone",
        type=int,
        default=settings.simulator_locations_per_zone,
    )
    parser.add_argument(
        "--controller-capacity",
        type=int,
        default=settings.simulator_controller_capacity,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser(get_settings())
    arguments = parser.parse_args(argv)
    try:
        result = asyncio.run(
            seed_simulator(
                arguments.locations,
                locations_per_zone=arguments.locations_per_zone,
                controller_capacity=arguments.controller_capacity,
            )
        )
    except (SeedTopologyConflict, ValueError) as error:
        parser.exit(2, f"seed failed: {error}\n")

    print(
        " ".join(f"{field}={getattr(result, field)}" for field in SeedResult.__dataclass_fields__)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
