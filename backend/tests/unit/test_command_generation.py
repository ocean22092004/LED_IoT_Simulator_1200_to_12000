import pytest

from backend.app.common.enums import ActualState, DesiredState, DeviceStatus
from backend.app.lights.reconciliation import command_is_needed

pytestmark = pytest.mark.unit


def test_equal_desired_and_actual_needs_no_command() -> None:
    assert not command_is_needed(
        DesiredState.ON,
        ActualState.ON,
        DeviceStatus.ONLINE,
        DeviceStatus.ONLINE,
    )


def test_known_state_mismatch_needs_command() -> None:
    assert command_is_needed(
        DesiredState.ON,
        ActualState.OFF,
        DeviceStatus.UNKNOWN,
        DeviceStatus.UNKNOWN,
    )


def test_unknown_actual_needs_online_gateway_and_controller() -> None:
    assert command_is_needed(
        DesiredState.ON,
        ActualState.UNKNOWN,
        DeviceStatus.ONLINE,
        DeviceStatus.ONLINE,
    )
    assert not command_is_needed(
        DesiredState.ON,
        ActualState.UNKNOWN,
        DeviceStatus.OFFLINE,
        DeviceStatus.ONLINE,
    )
    assert not command_is_needed(
        DesiredState.ON,
        ActualState.UNKNOWN,
        DeviceStatus.ONLINE,
        DeviceStatus.UNKNOWN,
    )
