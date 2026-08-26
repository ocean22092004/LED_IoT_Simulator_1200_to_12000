from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from simulator.memorial_sim.lamp import ChannelState, LampFault

OutputState = Literal["ON", "OFF", "UNKNOWN"]


@dataclass(frozen=True)
class FieldBusResult:
    command_id: UUID
    controller_code: str
    channel: int
    accepted: bool
    actual_output_state: OutputState
    current_ma: float | None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ControllerSnapshot:
    code: str
    status: Literal["ONLINE", "OFFLINE"]
    on_channels: tuple[int, ...]
    failed_lamp_channels: tuple[int, ...]


@dataclass
class ControllerSimulator:
    code: str
    address: int
    channel_capacity: int = 64
    online: bool = True
    channels: dict[int, ChannelState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("controller code must not be empty")
        if self.address <= 0:
            raise ValueError("controller address must be positive")
        if self.channel_capacity <= 0:
            raise ValueError("channel capacity must be positive")
        if not self.channels:
            self.channels = {
                channel: ChannelState()
                for channel in range(1, self.channel_capacity + 1)
            }
        elif set(self.channels) != set(range(1, self.channel_capacity + 1)):
            raise ValueError("channels must cover the configured capacity")

    async def set_output(
        self,
        channel: int,
        state: bool,
        command_id: UUID,
    ) -> FieldBusResult:
        if channel not in self.channels:
            return FieldBusResult(
                command_id=command_id,
                controller_code=self.code,
                channel=channel,
                accepted=False,
                actual_output_state="UNKNOWN",
                current_ma=None,
                error_code="INVALID_CHANNEL",
                error_message=f"Channel {channel} is invalid for {self.code}",
            )
        if not self.online:
            return FieldBusResult(
                command_id=command_id,
                controller_code=self.code,
                channel=channel,
                accepted=False,
                actual_output_state="UNKNOWN",
                current_ma=None,
                error_code="CONTROLLER_OFFLINE",
                error_message=f"{self.code} is offline",
            )

        channel_state = self.channels[channel]
        if state and channel_state.lamp_fault is LampFault.STUCK_OFF:
            channel_state.output_on = False
            channel_state.current_ma = 0.0
            return FieldBusResult(
                command_id=command_id,
                controller_code=self.code,
                channel=channel,
                accepted=False,
                actual_output_state="OFF",
                current_ma=0.0,
                error_code="OUTPUT_FAULT",
                error_message=f"Channel {channel} on {self.code} is stuck off",
            )

        channel_state.output_on = state
        if not state or channel_state.lamp_fault is LampFault.BURNED_OUT:
            channel_state.current_ma = 0.0
        else:
            channel_state.current_ma = 42.5
        return FieldBusResult(
            command_id=command_id,
            controller_code=self.code,
            channel=channel,
            accepted=True,
            actual_output_state="ON" if state else "OFF",
            current_ma=channel_state.current_ma,
        )

    def snapshot(self) -> ControllerSnapshot:
        return ControllerSnapshot(
            code=self.code,
            status="ONLINE" if self.online else "OFFLINE",
            on_channels=tuple(
                channel
                for channel, state in self.channels.items()
                if state.output_on
            ),
            failed_lamp_channels=tuple(
                channel
                for channel, state in self.channels.items()
                if state.lamp_fault is LampFault.BURNED_OUT
            ),
        )
