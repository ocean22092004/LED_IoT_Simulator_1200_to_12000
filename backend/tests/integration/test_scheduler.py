from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.activations.service import create_activation, expire_activations
from backend.app.anniversaries.lunar import LunarDate
from backend.app.common.enums import (
    ActivationReason,
    ActualState,
    CommandStatus,
    DesiredState,
    DeviceStatus,
)
from backend.app.db.models.activation import Activation
from backend.app.db.models.anniversary import AnniversaryRule
from backend.app.db.models.command import LightCommand
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.models.person import DeceasedPerson
from backend.app.devices.service import sweep_stale_devices
from backend.app.workers.scheduler import run_reconciliation, run_startup_recovery
from backend.tests.integration.conftest import MappedTopology

pytestmark = pytest.mark.integration


class FixedLunarCalendar:
    def from_solar(self, solar_date: date) -> LunarDate:
        return LunarDate(
            year=solar_date.year,
            month=7,
            day=15,
            is_leap_month=False,
        )


async def create_state(
    session: AsyncSession,
    topology: MappedTopology,
    code: str,
    channel: int,
    *,
    desired: DesiredState = DesiredState.OFF,
    actual: ActualState = ActualState.OFF,
) -> LampState:
    location = await topology.create_location(code, channel)
    state = LampState(
        location_id=location.id,
        desired_state=desired,
        actual_state=actual,
    )
    session.add(state)
    await session.flush()
    return state


async def test_startup_at_ten_creates_missing_anniversary_activation(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    now = datetime(2026, 8, 26, 3, 0, tzinfo=UTC)  # 10:00 Asia/Ho_Chi_Minh
    mapped_topology.gateway.status = DeviceStatus.ONLINE
    mapped_topology.gateway.last_seen_at = now
    mapped_topology.controller.status = DeviceStatus.ONLINE
    mapped_topology.controller.last_seen_at = now
    state = await create_state(session, mapped_topology, "SCHED-ANN", 1)
    person = DeceasedPerson(
        site_id=mapped_topology.site.id,
        full_name="Scheduler Anniversary",
    )
    session.add(person)
    await session.flush()
    location = await session.get(Location, state.location_id)
    assert location is not None
    location.person_id = person.id
    session.add(
        AnniversaryRule(
            person_id=person.id,
            location_id=location.id,
            lunar_day=15,
            lunar_month=7,
            is_leap_month=False,
        )
    )
    await session.flush()

    result = await run_startup_recovery(
        now=now,
        provider=FixedLunarCalendar(),
        offline_after_seconds=15,
        session=session,
    )

    activation = await session.scalar(
        select(Activation).where(
            Activation.location_id == location.id,
            Activation.reason == ActivationReason.ANNIVERSARY,
        )
    )
    assert result.anniversaries_created == 1
    assert activation is not None
    assert activation.dedupe_key == "anniversary:2026-08-26"
    assert state.desired_state is DesiredState.ON


async def test_expired_visit_turns_off_unless_anniversary_remains_active(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    visit_only = await create_state(session, mapped_topology, "SCHED-EXP", 2)
    overlap = await create_state(session, mapped_topology, "SCHED-OVERLAP", 3)
    expired_visit = await create_activation(
        visit_only.location_id,
        ActivationReason.VISIT,
        starts_at=now - timedelta(hours=1),
        expires_at=now,
        now=now - timedelta(minutes=1),
        session=session,
    )
    overlap_visit = await create_activation(
        overlap.location_id,
        ActivationReason.VISIT,
        starts_at=now - timedelta(hours=1),
        expires_at=now,
        now=now - timedelta(minutes=1),
        session=session,
    )
    await create_activation(
        overlap.location_id,
        ActivationReason.ANNIVERSARY,
        starts_at=now - timedelta(hours=8),
        expires_at=now + timedelta(hours=16),
        now=now - timedelta(minutes=1),
        session=session,
    )

    expired_count = await expire_activations(now=now, session=session)

    assert expired_count == 2
    assert expired_visit.ended_at == now
    assert overlap_visit.ended_at == now
    assert visit_only.desired_state is DesiredState.OFF
    assert overlap.desired_state is DesiredState.ON


async def test_stale_gateway_marks_locations_unknown_and_preserves_desired(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    state = await create_state(
        session,
        mapped_topology,
        "SCHED-STALE",
        4,
        desired=DesiredState.ON,
        actual=ActualState.ON,
    )
    mapped_topology.gateway.status = DeviceStatus.ONLINE
    mapped_topology.gateway.last_seen_at = now - timedelta(seconds=16)
    mapped_topology.controller.status = DeviceStatus.ONLINE
    mapped_topology.controller.last_seen_at = now
    await session.flush()

    result = await sweep_stale_devices(
        now=now,
        offline_after_seconds=15,
        session=session,
    )

    assert result.gateways_marked_offline == 1
    assert result.controllers_marked_offline == 1
    assert result.locations_marked_unknown == 1
    assert mapped_topology.gateway.status is DeviceStatus.OFFLINE
    assert mapped_topology.controller.status is DeviceStatus.OFFLINE
    assert state.desired_state is DesiredState.ON
    assert state.actual_state is ActualState.UNKNOWN


async def test_reconciliation_after_controller_reset_enqueues_restore_command(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    state = await create_state(
        session,
        mapped_topology,
        "SCHED-RESET",
        5,
        desired=DesiredState.ON,
        actual=ActualState.OFF,
    )
    mapped_topology.gateway.status = DeviceStatus.ONLINE
    mapped_topology.controller.status = DeviceStatus.ONLINE
    await session.flush()

    assert await run_reconciliation(now=now, session=session) == 1

    command = await session.scalar(
        select(LightCommand).where(LightCommand.location_id == state.location_id)
    )
    assert command is not None
    assert command.target_state is DesiredState.ON
    assert command.status is CommandStatus.PENDING
