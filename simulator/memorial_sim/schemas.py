from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.mqtt.schemas import LightCommandMessage

CommandMessage = LightCommandMessage
DeviceStatus = Literal["ONLINE", "OFFLINE"]
OutputState = Literal["ON", "OFF", "UNKNOWN"]


class DeviceMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("occurred_at", check_fields=False)
    @classmethod
    def require_aware_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


class AckMessage(DeviceMessage):
    schema_version: Literal[1] = 1
    command_id: UUID
    occurred_at: datetime
    gateway_code: str = Field(min_length=1)
    controller_code: str = Field(min_length=1)
    channel: int = Field(ge=1)
    accepted: bool
    actual_output_state: OutputState
    current_ma: float | None
    error_code: str | None
    error_message: str | None


class ControllerHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    status: DeviceStatus


class HeartbeatMessage(DeviceMessage):
    schema_version: Literal[1] = 1
    gateway_code: str = Field(min_length=1)
    occurred_at: datetime
    uptime_s: int = Field(ge=0)
    controllers: list[ControllerHeartbeat]


class ControllerSnapshotMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    status: DeviceStatus
    on_channels: list[int]
    failed_lamp_channels: list[int]


class SnapshotMessage(DeviceMessage):
    schema_version: Literal[1] = 1
    gateway_code: str = Field(min_length=1)
    occurred_at: datetime
    controllers: list[ControllerSnapshotMessage]


class PresenceMessage(DeviceMessage):
    gateway_code: str = Field(min_length=1)
    status: DeviceStatus
    occurred_at: datetime
