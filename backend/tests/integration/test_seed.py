import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.seed import SeedTopologyConflict, seed_simulator

pytestmark = pytest.mark.integration


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
