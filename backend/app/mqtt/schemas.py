from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.common.enums import ActualState, DesiredState


class LightCommandMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    command_id: UUID
    issued_at: datetime
    site_code: str = Field(min_length=1)
    gateway_code: str = Field(min_length=1)
    controller_code: str = Field(min_length=1)
    channel: int = Field(ge=1)
    target_state: DesiredState
    location_code: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def require_aware_issued_at(self) -> Self:
        if self.issued_at.tzinfo is None or self.issued_at.utcoffset() is None:
            raise ValueError("issued_at must be timezone-aware")
        return self


DeviceMessageStatus = Literal["ONLINE", "OFFLINE"]
ChannelNumber = Annotated[int, Field(ge=1)]


class DeviceMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_aware_occurred_at(self) -> Self:
        occurred_at = getattr(self, "occurred_at", None)
        if not isinstance(occurred_at, datetime):
            return self
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return self


class AckMessage(DeviceMessage):
    schema_version: Literal[1] = 1
    command_id: UUID
    occurred_at: datetime
    gateway_code: str = Field(min_length=1)
    controller_code: str = Field(min_length=1)
    channel: ChannelNumber
    accepted: bool
    actual_output_state: ActualState
    current_ma: float | None
    error_code: str | None
    error_message: str | None


class ControllerHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    status: DeviceMessageStatus


class HeartbeatMessage(DeviceMessage):
    schema_version: Literal[1] = 1
    gateway_code: str = Field(min_length=1)
    occurred_at: datetime
    uptime_s: int = Field(ge=0)
    controllers: list[ControllerHeartbeat]


class ControllerSnapshotMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    status: DeviceMessageStatus
    on_channels: list[ChannelNumber]
    failed_lamp_channels: list[ChannelNumber]


class SnapshotMessage(DeviceMessage):
    schema_version: Literal[1] = 1
    gateway_code: str = Field(min_length=1)
    occurred_at: datetime
    controllers: list[ControllerSnapshotMessage]


class PresenceMessage(DeviceMessage):
    gateway_code: str = Field(min_length=1)
    status: DeviceMessageStatus
    occurred_at: datetime


class ChannelTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: ChannelNumber
    output_state: ActualState
    current_ma: float | None


class TelemetryMessage(DeviceMessage):
    schema_version: Literal[1] = 1
    gateway_code: str = Field(min_length=1)
    controller_code: str = Field(min_length=1)
    occurred_at: datetime
    channels: list[ChannelTelemetry]
