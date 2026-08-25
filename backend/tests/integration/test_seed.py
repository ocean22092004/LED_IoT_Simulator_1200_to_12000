import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, make_url, select, text, update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from backend.app.config import get_settings
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.models.site import Site
from backend.app.db.models.zone import Zone
from backend.app.seed import SeedTopologyConflict, seed_simulator

pytestmark = pytest.mark.integration
PROJECT_ROOT = Path(__file__).resolve().parents[3]


async def execute_admin_statement(statement: str) -> None:
    admin_url = make_url(get_settings().database_url).set(database="postgres")
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def migrate_database(database_url: str) -> None:
    environment = os.environ | {"DATABASE_URL": database_url}

    def invoke() -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=PROJECT_ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    await asyncio.to_thread(invoke)


@pytest_asyncio.fixture
async def seed_database_url() -> AsyncIterator[str]:
    database_name = f"memorial_seed_test_{uuid4().hex[:12]}"
    database_url = (
        make_url(get_settings().database_url)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )
    await execute_admin_statement(f'CREATE DATABASE "{database_name}"')
    try:
        await migrate_database(database_url)
        yield database_url
    finally:
        await execute_admin_statement(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')


@pytest_asyncio.fixture
async def session(seed_database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(seed_database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as database_session:
            yield database_session
            await database_session.rollback()
    finally:
        await engine.dispose()


async def assert_mapping_invariants(
    session: AsyncSession,
    expected_locations: int,
) -> None:
    result = await session.execute(
        text(
            """
            SELECT
                count(*) AS location_count,
                count(DISTINCT location.code) AS distinct_code_count,
                count(DISTINCT (location.controller_id, location.channel_number))
                    AS distinct_channel_count,
                count(*) FILTER (
                    WHERE location.channel_number < 1
                       OR location.channel_number > controller.channel_capacity
                ) AS invalid_channel_count,
                count(*) FILTER (
                    WHERE location.gateway_id <> controller.gateway_id
                ) AS gateway_mismatch_count
            FROM locations AS location
            JOIN controllers AS controller ON controller.id = location.controller_id
            JOIN sites AS site ON site.id = location.site_id
            WHERE site.code = 'SITE-001'
            """
        )
    )
    row = result.one()

    assert row.location_count == expected_locations
    assert row.distinct_code_count == expected_locations
    assert row.distinct_channel_count == expected_locations
    assert row.invalid_channel_count == 0
    assert row.gateway_mismatch_count == 0


async def test_seed_1200_has_expected_topology_and_state_defaults(
    session: AsyncSession,
) -> None:
    result = await seed_simulator(1200, session=session)

    assert result.site_count == 1
    assert result.zone_count == 4
    assert result.gateway_count == 4
    assert result.controller_count == 20
    assert result.location_count == 1200
    assert result.person_count == 1200
    assert result.lamp_state_count == 1200
    await assert_mapping_invariants(session, 1200)

    a250 = (
        await session.execute(
            text(
                """
                SELECT gateway.code, controller.code, location.channel_number
                FROM locations AS location
                JOIN sites AS site ON site.id = location.site_id
                JOIN gateways AS gateway ON gateway.id = location.gateway_id
                JOIN controllers AS controller ON controller.id = location.controller_id
                WHERE site.code = 'SITE-001' AND location.code = 'A250'
                """
            )
        )
    ).one()
    assert tuple(a250) == ("GW-A", "CTRL-A-04", 58)

    state_counts = (
        await session.execute(
            text(
                """
                SELECT
                    count(*) FILTER (WHERE desired_state = 'OFF') AS desired_off,
                    count(*) FILTER (WHERE actual_state = 'UNKNOWN') AS actual_unknown,
                    count(*) FILTER (
                        WHERE controller_output_state = 'UNKNOWN'
                    ) AS output_unknown,
                    count(*) FILTER (WHERE lamp_health = 'UNKNOWN') AS health_unknown
                FROM lamp_states
                """
            )
        )
    ).one()
    assert tuple(state_counts) == (1200, 1200, 1200, 1200)


async def test_seed_rerun_is_idempotent_and_rejects_topology_change(
    session: AsyncSession,
) -> None:
    first = await seed_simulator(1200, session=session)
    second = await seed_simulator(1200, session=session)

    assert second == first
    await assert_mapping_invariants(session, 1200)

    with pytest.raises(SeedTopologyConflict, match="make reset-db"):
        await seed_simulator(12000, session=session)


async def test_seed_rejects_parent_relationship_drift(session: AsyncSession) -> None:
    await seed_simulator(1200, session=session)
    zone_b_id = await session.scalar(select(Zone.id).where(Zone.code == "B"))
    assert zone_b_id is not None
    await session.execute(update(Gateway).where(Gateway.code == "GW-A").values(zone_id=zone_b_id))

    with pytest.raises(SeedTopologyConflict, match="make reset-db"):
        await seed_simulator(1200, session=session)


async def test_seed_rejects_gateway_parent_from_another_site(
    session: AsyncSession,
) -> None:
    await seed_simulator(1200, session=session)
    other_site = Site(
        code="SITE-OTHER",
        name="Other site",
        timezone="Asia/Ho_Chi_Minh",
    )
    session.add(other_site)
    await session.flush()
    other_zone = Zone(site_id=other_site.id, code="A", name="Other A")
    session.add(other_zone)
    await session.flush()
    await session.execute(
        update(Gateway).where(Gateway.code == "GW-A").values(zone_id=other_zone.id)
    )

    with pytest.raises(SeedTopologyConflict, match="make reset-db"):
        await seed_simulator(1200, session=session)


async def test_seed_rejects_location_parents_from_another_site(
    session: AsyncSession,
) -> None:
    await seed_simulator(1200, session=session)
    other_site = Site(
        code="SITE-OTHER",
        name="Other site",
        timezone="Asia/Ho_Chi_Minh",
    )
    session.add(other_site)
    await session.flush()
    other_zone = Zone(site_id=other_site.id, code="A", name="Other A")
    session.add(other_zone)
    await session.flush()
    other_gateway = Gateway(
        site_id=other_site.id,
        zone_id=other_zone.id,
        code="GW-A",
        name="Other GW-A",
    )
    session.add(other_gateway)
    await session.flush()
    other_controller = Controller(
        gateway_id=other_gateway.id,
        code="CTRL-A-01",
        address=1,
        channel_capacity=64,
    )
    session.add(other_controller)
    await session.flush()
    await session.execute(
        update(Location)
        .where(Location.code == "A001")
        .values(
            zone_id=other_zone.id,
            gateway_id=other_gateway.id,
            controller_id=other_controller.id,
        )
    )

    with pytest.raises(SeedTopologyConflict, match="make reset-db"):
        await seed_simulator(1200, session=session)


async def test_seed_rejects_non_deterministic_location_identity(
    session: AsyncSession,
) -> None:
    await seed_simulator(1, session=session)
    await session.execute(delete(LampState))
    await session.execute(update(Location).where(Location.code == "A001").values(id=uuid4()))

    with pytest.raises(SeedTopologyConflict, match="make reset-db"):
        await seed_simulator(1, session=session)


async def test_seed_rejects_wrong_site_timezone(session: AsyncSession) -> None:
    await seed_simulator(1, session=session)
    await session.execute(update(Site).where(Site.code == "SITE-001").values(timezone="UTC"))

    with pytest.raises(SeedTopologyConflict, match="make reset-db"):
        await seed_simulator(1, session=session)


async def test_conflicting_concurrent_seeds_cannot_both_succeed(
    seed_database_url: str,
) -> None:
    engine = create_async_engine(seed_database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as setup_session:
        setup_session.add(
            Site(
                code="SITE-001",
                name="Existing empty site",
                timezone="Asia/Ho_Chi_Minh",
            )
        )
        await setup_session.commit()

    async def run_seed(location_count: int):
        async with session_factory() as concurrent_session:
            try:
                result = await seed_simulator(
                    location_count,
                    session=concurrent_session,
                )
                await concurrent_session.commit()
                return result
            except Exception:
                await concurrent_session.rollback()
                raise

    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                run_seed(1200),
                run_seed(12000),
                return_exceptions=True,
            ),
            timeout=30,
        )
        async with session_factory() as verification_session:
            persisted_location_count = await verification_session.scalar(
                select(func.count()).select_from(Location)
            )
    finally:
        await engine.dispose()

    successes = [result for result in results if not isinstance(result, Exception)]
    conflicts = [result for result in results if isinstance(result, SeedTopologyConflict)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert persisted_location_count == successes[0].location_count


async def test_seed_12000_uses_extended_zone_codes(
    session: AsyncSession,
) -> None:
    result = await seed_simulator(12000, session=session)

    assert result.site_count == 1
    assert result.zone_count == 40
    assert result.gateway_count == 40
    assert result.controller_count == 200
    assert result.location_count == 12000
    assert result.person_count == 12000
    assert result.lamp_state_count == 12000
    await assert_mapping_invariants(session, 12000)

    codes = set(
        (
            await session.execute(
                text(
                    """
                    SELECT location.code
                    FROM locations AS location
                    JOIN sites AS site ON site.id = location.site_id
                    WHERE site.code = 'SITE-001'
                      AND location.code IN ('AA001', 'AN300')
                    """
                )
            )
        ).scalars()
    )
    assert codes == {"AA001", "AN300"}
