from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import ActualState, DesiredState
from backend.app.db.models.activation import Activation
from backend.app.db.models.anniversary import AnniversaryRule
from backend.app.db.models.device import Controller
from backend.app.db.models.device_event import DeviceEvent
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.person import DeceasedPerson
from backend.tests.integration.conftest import MappedTopology

pytestmark = pytest.mark.integration


async def test_location_code_is_unique_within_site(mapped_topology: MappedTopology):
    await mapped_topology.create_location(code="A001", channel=1)

    with pytest.raises(IntegrityError):
        await mapped_topology.create_location(code="A001", channel=2)


async def test_controller_channel_can_only_map_once(mapped_topology: MappedTopology):
    await mapped_topology.create_location(code="A001", channel=1)

    with pytest.raises(IntegrityError):
        await mapped_topology.create_location(code="A002", channel=1)


async def test_desired_and_actual_defaults_are_distinct(
    session: AsyncSession,
    mapped_topology: MappedTopology,
):
    location = await mapped_topology.create_location(code="A001", channel=1)
    state = LampState(location_id=location.id)
    session.add(state)
    await session.flush()
    await session.refresh(state)

    assert state.desired_state is DesiredState.OFF
    assert state.actual_state is ActualState.UNKNOWN


@pytest.mark.parametrize(
    ("day", "month"),
    [(0, 1), (31, 1), (1, 0), (1, 13)],
)
async def test_anniversary_day_and_month_are_database_checked(
    session: AsyncSession,
    mapped_topology: MappedTopology,
    day: int,
    month: int,
):
    location = await mapped_topology.create_location(code="A001", channel=1)
    person = DeceasedPerson(site_id=mapped_topology.site.id, full_name="Test Person")
    session.add(person)
    await session.flush()
    session.add(
        AnniversaryRule(
            person_id=person.id,
            location_id=location.id,
            lunar_day=day,
            lunar_month=month,
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_controller_capacity_must_be_positive(
    session: AsyncSession,
    mapped_topology: MappedTopology,
):
    session.add(
        Controller(
            gateway_id=mapped_topology.gateway.id,
            code="CTRL-A-02",
            address=2,
            channel_capacity=0,
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_location_channel_must_be_positive(mapped_topology: MappedTopology):
    with pytest.raises(IntegrityError):
        await mapped_topology.create_location(code="A001", channel=0)


async def test_activation_allows_multiple_null_dedupe_keys(
    session: AsyncSession,
    mapped_topology: MappedTopology,
):
    location = await mapped_topology.create_location(code="A001", channel=1)
    now = datetime.now(UTC)
    session.add_all(
        [
            Activation(location_id=location.id, reason="VISIT", starts_at=now),
            Activation(location_id=location.id, reason="VISIT", starts_at=now),
        ]
    )

    await session.flush()


async def test_activation_rejects_duplicate_non_null_dedupe_key(
    session: AsyncSession,
    mapped_topology: MappedTopology,
):
    location = await mapped_topology.create_location(code="A001", channel=1)
    now = datetime.now(UTC)
    session.add_all(
        [
            Activation(
                location_id=location.id,
                reason="ANNIVERSARY",
                starts_at=now,
                dedupe_key="anniversary:2026-08-25",
            ),
            Activation(
                location_id=location.id,
                reason="ANNIVERSARY",
                starts_at=now,
                dedupe_key="anniversary:2026-08-25",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_device_event_requires_site_id(session: AsyncSession):
    now = datetime.now(UTC)
    session.add(
        DeviceEvent(
            site_id=None,
            event_type="heartbeat",
            occurred_at=now,
            received_at=now,
            payload={},
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()
