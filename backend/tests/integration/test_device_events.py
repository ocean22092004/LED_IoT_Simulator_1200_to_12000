from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import (
    ActualState,
    CommandStatus,
    ControllerOutputState,
    DesiredState,
    DeviceStatus,
    LampHealth,
)
from backend.app.db.models.device_event import DeviceEvent
from backend.app.db.models.lamp_state import LampState
from backend.app.lights.commands import enqueue_state_command
from backend.app.mqtt.consumer import (
    handle_ack,
    handle_heartbeat,
    handle_presence,
    handle_snapshot,
    handle_telemetry,
)
from backend.app.mqtt.schemas import (
    AckMessage,
    ChannelTelemetry,
    ControllerHeartbeat,
    ControllerSnapshotMessage,
    HeartbeatMessage,
    PresenceMessage,
    SnapshotMessage,
    TelemetryMessage,
)
from backend.tests.integration.conftest import MappedTopology

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)


async def create_lamp(
    session: AsyncSession,
    topology: MappedTopology,
    code: str,
    channel: int,
    *,
    desired: DesiredState = DesiredState.OFF,
    actual: ActualState = ActualState.UNKNOWN,
) -> LampState:
    location = await topology.create_location(code, channel)
    state = LampState(
        location_id=location.id,
        desired_state=desired,
        actual_state=actual,
        controller_output_state=ControllerOutputState(actual.value),
    )
    session.add(state)
    await session.flush()
    return state


async def test_ack_success_marks_command_acked_and_updates_actual_state(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    lamp = await create_lamp(
        session,
        mapped_topology,
        "ACK-A250",
        58,
        desired=DesiredState.ON,
        actual=ActualState.OFF,
    )
    command = await enqueue_state_command(
        lamp.location_id,
        DesiredState.ON,
        "VISIT",
        now=NOW,
        session=session,
    )

    await handle_ack(
        AckMessage(
            command_id=command.id,
            occurred_at=NOW,
            gateway_code="GW-A",
            controller_code="CTRL-A-01",
            channel=58,
            accepted=True,
            actual_output_state=ActualState.ON,
            current_ma=42.5,
            error_code=None,
            error_message=None,
        ),
        received_at=NOW,
        session=session,
    )

    assert command.status is CommandStatus.ACKED
    assert command.acked_at == NOW
    assert lamp.desired_state is DesiredState.ON
    assert lamp.actual_state is ActualState.ON
    assert lamp.controller_output_state is ControllerOutputState.ON
    assert lamp.lamp_health is LampHealth.OK
    assert lamp.current_ma == Decimal("42.50")
    assert lamp.last_device_report_at == NOW
    event_count = await session.scalar(
        select(func.count())
        .select_from(DeviceEvent)
        .where(DeviceEvent.location_id == lamp.location_id)
    )
    assert event_count == 1


async def test_failure_ack_marks_failed_without_false_actual_on(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    lamp = await create_lamp(
        session,
        mapped_topology,
        "ACK-FAIL",
        4,
        desired=DesiredState.ON,
        actual=ActualState.OFF,
    )
    command = await enqueue_state_command(
        lamp.location_id,
        DesiredState.ON,
        "VISIT",
        now=NOW,
        session=session,
    )

    await handle_ack(
        AckMessage(
            command_id=command.id,
            occurred_at=NOW,
            gateway_code="GW-A",
            controller_code="CTRL-A-01",
            channel=4,
            accepted=False,
            actual_output_state=ActualState.UNKNOWN,
            current_ma=None,
            error_code="CONTROLLER_OFFLINE",
            error_message="CTRL-A-01 is offline",
        ),
        received_at=NOW,
        session=session,
    )

    assert command.status is CommandStatus.FAILED
    assert command.last_error == "CONTROLLER_OFFLINE: CTRL-A-01 is offline"
    assert lamp.desired_state is DesiredState.ON
    assert lamp.actual_state is ActualState.UNKNOWN
    assert lamp.actual_state is not ActualState.ON
    assert mapped_topology.controller.status is DeviceStatus.OFFLINE


async def test_burned_lamp_ack_marks_health_suspected_failed(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    lamp = await create_lamp(session, mapped_topology, "BURNED", 10)
    command = await enqueue_state_command(
        lamp.location_id,
        DesiredState.ON,
        "MANUAL_ON",
        now=NOW,
        session=session,
    )

    await handle_ack(
        AckMessage(
            command_id=command.id,
            occurred_at=NOW,
            gateway_code="GW-A",
            controller_code="CTRL-A-01",
            channel=10,
            accepted=True,
            actual_output_state=ActualState.ON,
            current_ma=0.0,
            error_code=None,
            error_message=None,
        ),
        session=session,
    )

    assert lamp.actual_state is ActualState.ON
    assert lamp.controller_output_state is ControllerOutputState.ON
    assert lamp.lamp_health is LampHealth.SUSPECTED_FAILED
    assert lamp.current_ma == Decimal("0.00")


async def test_burned_lamp_telemetry_marks_health_suspected_failed(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    burned = await create_lamp(
        session,
        mapped_topology,
        "TELEMETRY-BURNED",
        11,
        actual=ActualState.ON,
    )
    off = await create_lamp(
        session,
        mapped_topology,
        "TELEMETRY-OFF",
        12,
        actual=ActualState.OFF,
    )
    off.lamp_health = LampHealth.OK

    await handle_telemetry(
        TelemetryMessage(
            gateway_code="GW-A",
            controller_code="CTRL-A-01",
            occurred_at=NOW,
            channels=[
                ChannelTelemetry(
                    channel=11,
                    output_state=ActualState.ON,
                    current_ma=0.0,
                ),
                ChannelTelemetry(
                    channel=12,
                    output_state=ActualState.OFF,
                    current_ma=0.0,
                ),
            ],
        ),
        site_code="SITE-TEST",
        received_at=NOW,
        session=session,
    )

    assert burned.actual_state is ActualState.ON
    assert burned.controller_output_state is ControllerOutputState.ON
    assert burned.lamp_health is LampHealth.SUSPECTED_FAILED
    assert burned.current_ma == Decimal("0.00")
    assert off.actual_state is ActualState.OFF
    assert off.lamp_health is LampHealth.OK


async def test_snapshot_updates_every_online_controller_channel(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    on_lamp = await create_lamp(session, mapped_topology, "SNAP-ON", 1)
    off_lamp = await create_lamp(session, mapped_topology, "SNAP-OFF", 2)

    await handle_snapshot(
        SnapshotMessage(
            gateway_code="GW-A",
            occurred_at=NOW,
            controllers=[
                ControllerSnapshotMessage(
                    code="CTRL-A-01",
                    status=DeviceStatus.ONLINE,
                    on_channels=[1],
                    failed_lamp_channels=[1],
                )
            ],
        ),
        site_code="SITE-TEST",
        received_at=NOW,
        session=session,
    )

    assert on_lamp.actual_state is ActualState.ON
    assert on_lamp.controller_output_state is ControllerOutputState.ON
    assert on_lamp.lamp_health is LampHealth.SUSPECTED_FAILED
    assert on_lamp.current_ma == Decimal("0.00")
    assert off_lamp.actual_state is ActualState.OFF
    assert off_lamp.controller_output_state is ControllerOutputState.OFF
    assert off_lamp.lamp_health is LampHealth.OK
    assert off_lamp.current_ma == Decimal("0.00")


async def test_offline_presence_marks_gateway_locations_unknown_only(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    lamp = await create_lamp(
        session,
        mapped_topology,
        "OFFLINE",
        3,
        desired=DesiredState.ON,
        actual=ActualState.ON,
    )

    await handle_presence(
        PresenceMessage(
            gateway_code="GW-A",
            status=DeviceStatus.OFFLINE,
            occurred_at=NOW,
        ),
        site_code="SITE-TEST",
        received_at=NOW,
        session=session,
    )

    assert mapped_topology.gateway.status is DeviceStatus.OFFLINE
    assert mapped_topology.controller.status is DeviceStatus.OFFLINE
    assert lamp.desired_state is DesiredState.ON
    assert lamp.actual_state is ActualState.UNKNOWN
    assert lamp.controller_output_state is ControllerOutputState.UNKNOWN
    assert lamp.lamp_health is LampHealth.UNKNOWN
    assert lamp.current_ma is None


async def test_heartbeat_updates_status_and_offline_controller_locations(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    lamp = await create_lamp(
        session,
        mapped_topology,
        "HEARTBEAT",
        5,
        actual=ActualState.ON,
    )

    await handle_heartbeat(
        HeartbeatMessage(
            gateway_code="GW-A",
            occurred_at=NOW,
            uptime_s=12,
            controllers=[
                ControllerHeartbeat(
                    code="CTRL-A-01",
                    status=DeviceStatus.OFFLINE,
                )
            ],
        ),
        site_code="SITE-TEST",
        received_at=NOW,
        session=session,
    )

    assert mapped_topology.gateway.status is DeviceStatus.ONLINE
    assert mapped_topology.gateway.last_seen_at == NOW
    assert mapped_topology.controller.status is DeviceStatus.OFFLINE
    assert lamp.actual_state is ActualState.UNKNOWN
