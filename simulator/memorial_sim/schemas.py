from typing import Literal

from backend.app.mqtt.schemas import (
    AckMessage,
    ChannelTelemetry,
    ControllerHeartbeat,
    ControllerSnapshotMessage,
    HeartbeatMessage,
    LightCommandMessage,
    PresenceMessage,
    SnapshotMessage,
    TelemetryMessage,
)

CommandMessage = LightCommandMessage
DeviceStatus = Literal["ONLINE", "OFFLINE"]

__all__ = [
    "AckMessage",
    "ChannelTelemetry",
    "CommandMessage",
    "ControllerHeartbeat",
    "ControllerSnapshotMessage",
    "DeviceStatus",
    "HeartbeatMessage",
    "PresenceMessage",
    "SnapshotMessage",
    "TelemetryMessage",
]
