from typing import Literal

from backend.app.mqtt.schemas import (
    AckMessage,
    ControllerHeartbeat,
    ControllerSnapshotMessage,
    HeartbeatMessage,
    LightCommandMessage,
    PresenceMessage,
    SnapshotMessage,
)

CommandMessage = LightCommandMessage
DeviceStatus = Literal["ONLINE", "OFFLINE"]

__all__ = [
    "AckMessage",
    "CommandMessage",
    "ControllerHeartbeat",
    "ControllerSnapshotMessage",
    "DeviceStatus",
    "HeartbeatMessage",
    "PresenceMessage",
    "SnapshotMessage",
]
