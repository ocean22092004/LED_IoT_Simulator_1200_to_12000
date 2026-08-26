from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from simulator.memorial_sim.controller import (
    ControllerSimulator,
    ControllerSnapshot,
    FieldBusResult,
)


class FieldBus(Protocol):
    async def set_output(
        self,
        controller_code: str,
        channel: int,
        state: bool,
        command_id: UUID,
    ) -> FieldBusResult: ...

    async def snapshot(self) -> list[ControllerSnapshot]: ...


class SimulatedFieldBus:
    def __init__(self, controllers: Iterable[ControllerSimulator]) -> None:
        controller_list = list(controllers)
        self.controllers = {
            controller.code: controller
            for controller in controller_list
        }
        if len(self.controllers) != len(controller_list):
            raise ValueError("controller codes must be unique")

    async def set_output(
        self,
        controller_code: str,
        channel: int,
        state: bool,
        command_id: UUID,
    ) -> FieldBusResult:
        controller = self.controllers.get(controller_code)
        if controller is None:
            return FieldBusResult(
                command_id=command_id,
                controller_code=controller_code,
                channel=channel,
                accepted=False,
                actual_output_state="UNKNOWN",
                current_ma=None,
                error_code="CONTROLLER_NOT_FOUND",
                error_message=f"{controller_code} was not found",
            )
        return await controller.set_output(channel, state, command_id)

    async def snapshot(self) -> list[ControllerSnapshot]:
        return [
            controller.snapshot()
            for controller in sorted(
                self.controllers.values(),
                key=lambda value: value.code,
            )
        ]
