from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.activations.service import create_activation, end_activation
from backend.app.common.enums import ActivationReason, DesiredState
from backend.app.db.models.lamp_state import LampState
from backend.app.lights.resolver import resolve_desired_state
from backend.tests.integration.conftest import MappedTopology

pytestmark = pytest.mark.integration


async def create_location_state(
    session: AsyncSession,
    mapped_topology: MappedTopology,
    *,
    code: str,
    channel: int,
) -> LampState:
    location = await mapped_topology.create_location(code, channel)
    state = LampState(location_id=location.id)
    session.add(state)
    await session.flush()
    return state


async def test_create_and_end_visit_updates_desired_state(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    state = await create_location_state(
        session,
        mapped_topology,
        code="ACT-VISIT",
        channel=1,
    )
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)

    activation = await create_activation(
        state.location_id,
        ActivationReason.VISIT,
        starts_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        now=now,
        session=session,
    )

    assert state.desired_state is DesiredState.ON
    assert state.desired_changed_at == now
    assert state.version == 1

    ended_at = now + timedelta(minutes=10)
    ended = await end_activation(
        activation.id,
        actor=None,
        ended_at=ended_at,
        session=session,
    )

    assert ended.ended_at == ended_at
    assert state.desired_state is DesiredState.OFF
    assert state.desired_changed_at == ended_at
    assert state.version == 2


async def test_ending_visit_keeps_anniversary_intent_on(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    state = await create_location_state(
        session,
        mapped_topology,
        code="ACT-OVERLAP",
        channel=2,
    )
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    anniversary = await create_activation(
        state.location_id,
        ActivationReason.ANNIVERSARY,
        starts_at=now - timedelta(hours=8),
        expires_at=now + timedelta(hours=16),
        now=now,
        session=session,
    )
    visit = await create_activation(
        state.location_id,
        ActivationReason.VISIT,
        starts_at=now,
        expires_at=now + timedelta(hours=1),
        now=now,
        session=session,
    )

    assert state.desired_state is DesiredState.ON
    assert state.version == 1

    await end_activation(
        visit.id,
        actor=None,
        ended_at=now + timedelta(minutes=10),
        session=session,
    )
    result = await resolve_desired_state(
        state.location_id,
        now + timedelta(minutes=10),
        session=session,
    )

    assert result.desired_state == "ON"
    assert result.active_reasons == ("ANNIVERSARY",)
    assert result.changed is False
    assert state.version == 1

    await end_activation(
        anniversary.id,
        actor=None,
        ended_at=now + timedelta(minutes=11),
        session=session,
    )
    assert state.desired_state is DesiredState.OFF
    assert state.version == 2


async def test_expired_activation_resolves_off(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    state = await create_location_state(
        session,
        mapped_topology,
        code="ACT-EXPIRED",
        channel=3,
    )
    starts_at = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    await create_activation(
        state.location_id,
        ActivationReason.VISIT,
        starts_at=starts_at,
        expires_at=starts_at + timedelta(minutes=5),
        now=starts_at,
        session=session,
    )

    result = await resolve_desired_state(
        state.location_id,
        starts_at + timedelta(minutes=5),
        session=session,
    )

    assert result.desired_state == "OFF"
    assert result.active_reasons == ()
    assert result.changed is True
    assert state.desired_state is DesiredState.OFF
