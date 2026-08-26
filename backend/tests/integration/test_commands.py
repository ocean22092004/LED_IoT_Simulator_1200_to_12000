from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.activations.service import create_activation
from backend.app.common.enums import (
    ActivationReason,
    ActualState,
    CommandStatus,
    DesiredState,
    DeviceStatus,
)
from backend.app.db.models.command import LightCommand
from backend.app.db.models.lamp_state import LampState
from backend.app.lights.commands import enqueue_state_command
from backend.app.lights.reconciliation import reconcile_all, reconcile_location
from backend.tests.integration.conftest import MappedTopology

pytestmark = pytest.mark.integration


async def create_command_location(
    session: AsyncSession,
    mapped_topology: MappedTopology,
    *,
    code: str,
    channel: int,
    desired: DesiredState,
    actual: ActualState,
) -> LampState:
    location = await mapped_topology.create_location(code, channel)
    state = LampState(
        location_id=location.id,
        desired_state=desired,
        actual_state=actual,
    )
    session.add(state)
    await session.flush()
    return state


async def test_desired_equal_actual_creates_no_command(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    state = await create_command_location(
        session,
        mapped_topology,
        code="CMD-EQUAL",
        channel=1,
        desired=DesiredState.OFF,
        actual=ActualState.OFF,
    )

    assert await reconcile_location(state.location_id, session=session) is None


async def test_desired_on_actual_off_creates_pending_command(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    state = await create_command_location(
        session,
        mapped_topology,
        code="CMD-MISMATCH",
        channel=2,
        desired=DesiredState.ON,
        actual=ActualState.OFF,
    )
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)

    command = await reconcile_location(
        state.location_id,
        reason="VISIT",
        now=now,
        session=session,
    )

    assert command is not None
    assert command.location_id == state.location_id
    assert command.gateway_id == mapped_topology.gateway.id
    assert command.controller_id == mapped_topology.controller.id
    assert command.channel_number == 2
    assert command.target_state is DesiredState.ON
    assert command.status is CommandStatus.PENDING
    assert command.reason == "VISIT"
    assert command.attempt_count == 0
    assert command.next_attempt_at == now


async def test_actual_unknown_only_enqueues_when_devices_are_online(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    state = await create_command_location(
        session,
        mapped_topology,
        code="CMD-UNKNOWN",
        channel=3,
        desired=DesiredState.ON,
        actual=ActualState.UNKNOWN,
    )

    assert await reconcile_location(state.location_id, session=session) is None

    mapped_topology.gateway.status = DeviceStatus.ONLINE
    mapped_topology.controller.status = DeviceStatus.ONLINE
    await session.flush()

    command = await reconcile_location(state.location_id, session=session)
    assert command is not None
    assert command.target_state is DesiredState.ON


async def test_enqueue_deduplicates_pending_and_sent_target_commands(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    state = await create_command_location(
        session,
        mapped_topology,
        code="CMD-DEDUPE",
        channel=4,
        desired=DesiredState.ON,
        actual=ActualState.OFF,
    )
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)

    first = await enqueue_state_command(
        state.location_id,
        DesiredState.ON,
        "VISIT",
        now=now,
        session=session,
    )
    second = await enqueue_state_command(
        state.location_id,
        DesiredState.ON,
        "RECONCILIATION",
        now=now + timedelta(seconds=1),
        session=session,
    )
    first.status = CommandStatus.SENT
    await session.flush()
    third = await enqueue_state_command(
        state.location_id,
        DesiredState.ON,
        "RECONCILIATION",
        now=now + timedelta(seconds=2),
        session=session,
    )

    assert second.id == first.id
    assert third.id == first.id
    count = await session.scalar(
        select(func.count())
        .select_from(LightCommand)
        .where(LightCommand.location_id == state.location_id)
    )
    assert count == 1


async def test_activation_change_enqueues_command(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    state = await create_command_location(
        session,
        mapped_topology,
        code="CMD-ACTIVATION",
        channel=5,
        desired=DesiredState.OFF,
        actual=ActualState.OFF,
    )
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    await create_activation(
        state.location_id,
        ActivationReason.VISIT,
        starts_at=now,
        expires_at=now + timedelta(hours=1),
        now=now,
        session=session,
    )

    command = await session.scalar(
        select(LightCommand).where(LightCommand.location_id == state.location_id)
    )
    assert command is not None
    assert command.target_state is DesiredState.ON
    assert command.reason == "VISIT"


async def test_reconcile_all_is_bounded(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    state = await create_command_location(
        session,
        mapped_topology,
        code="CMD-BATCH",
        channel=6,
        desired=DesiredState.ON,
        actual=ActualState.OFF,
    )
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)

    assert await reconcile_all(limit=1, now=now, session=session) == 1
    assert await session.scalar(
        select(LightCommand).where(LightCommand.location_id == state.location_id)
    ) is not None
