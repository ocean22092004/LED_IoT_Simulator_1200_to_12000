from dataclasses import dataclass
from enum import StrEnum


class LampFault(StrEnum):
    BURNED_OUT = "BURNED_OUT"
    STUCK_OFF = "STUCK_OFF"


@dataclass
class ChannelState:
    output_on: bool = False
    lamp_fault: LampFault | None = None
    current_ma: float | None = 0.0
