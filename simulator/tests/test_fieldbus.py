from uuid import uuid4

import pytest

from simulator.memorial_sim.controller import ControllerSimulator
from simulator.memorial_sim.fieldbus import SimulatedFieldBus
from simulator.memorial_sim.lamp import LampFault

pytestmark = pytest.mark.unit


@pytest.fixture
def controller() -> ControllerSimulator:
    return ControllerSimulator(code="CTRL-A-01", address=1, channel_capacity=4)


@pytest.fixture
def fieldbus(controller: ControllerSimulator) -> SimulatedFieldBus:
    return SimulatedFieldBus([controller])


async def test_valid_on_and_off_control_output(
    fieldbus: SimulatedFieldBus,
    controller: ControllerSimulator,
) -> None:
    command_id = uuid4()

    on_result = await fieldbus.set_output("CTRL-A-01", 2, True, command_id)

    assert on_result.accepted is True
    assert on_result.actual_output_state == "ON"
    assert on_result.current_ma is not None and on_result.current_ma > 0
    assert controller.channels[2].output_on is True

    off_result = await fieldbus.set_output("CTRL-A-01", 2, False, uuid4())

    assert off_result.accepted is True
    assert off_result.actual_output_state == "OFF"
    assert off_result.current_ma == 0.0
    assert controller.channels[2].output_on is False


async def test_invalid_channel_is_rejected(fieldbus: SimulatedFieldBus) -> None:
    result = await fieldbus.set_output("CTRL-A-01", 5, True, uuid4())

    assert result.accepted is False
    assert result.actual_output_state == "UNKNOWN"
    assert result.error_code == "INVALID_CHANNEL"


async def test_offline_controller_is_rejected(
    fieldbus: SimulatedFieldBus,
    controller: ControllerSimulator,
) -> None:
    controller.online = False

    result = await fieldbus.set_output("CTRL-A-01", 1, True, uuid4())

    assert result.accepted is False
    assert result.actual_output_state == "UNKNOWN"
    assert result.error_code == "CONTROLLER_OFFLINE"


async def test_burned_lamp_draws_no_current_while_output_is_on(
    fieldbus: SimulatedFieldBus,
    controller: ControllerSimulator,
) -> None:
    controller.channels[3].lamp_fault = LampFault.BURNED_OUT

    result = await fieldbus.set_output("CTRL-A-01", 3, True, uuid4())

    assert result.accepted is True
    assert result.actual_output_state == "ON"
    assert result.current_ma == 0.0
    snapshot = (await fieldbus.snapshot())[0]
    assert snapshot.on_channels == (3,)
    assert snapshot.failed_lamp_channels == (3,)


async def test_stuck_off_fault_rejects_on_and_keeps_output_off(
    fieldbus: SimulatedFieldBus,
    controller: ControllerSimulator,
) -> None:
    controller.channels[4].lamp_fault = LampFault.STUCK_OFF

    result = await fieldbus.set_output("CTRL-A-01", 4, True, uuid4())

    assert result.accepted is False
    assert result.actual_output_state == "OFF"
    assert result.current_ma == 0.0
    assert result.error_code == "OUTPUT_FAULT"
    assert controller.channels[4].output_on is False


async def test_unknown_controller_is_reported_by_fieldbus(
    fieldbus: SimulatedFieldBus,
) -> None:
    result = await fieldbus.set_output("CTRL-Z-99", 1, True, uuid4())

    assert result.accepted is False
    assert result.actual_output_state == "UNKNOWN"
    assert result.error_code == "CONTROLLER_NOT_FOUND"


def test_duplicate_controller_code_is_rejected() -> None:
    controllers = [
        ControllerSimulator(code="CTRL-A-01", address=1),
        ControllerSimulator(code="CTRL-A-01", address=2),
    ]

    with pytest.raises(ValueError, match="unique"):
        SimulatedFieldBus(controllers)
