from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.app.common.enums import (
    CommandStatus,
    DesiredState,
    DeviceStatus,
)


class GatewayRead(BaseModel):
    id: UUID
    site_id: UUID
    zone_id: UUID | None
    code: str
    name: str
    status: DeviceStatus
    last_seen_at: datetime | None
    firmware_version: str | None
    is_simulated: bool
    affected_locations: int


class ControllerRead(BaseModel):
    id: UUID
    gateway_id: UUID
    gateway_code: str
    code: str
    address: int
    channel_capacity: int
    status: DeviceStatus
    last_seen_at: datetime | None
    is_active: bool
    affected_locations: int


class GatewayDetail(GatewayRead):
    controllers: list[ControllerRead]


class OfflineDevices(BaseModel):
    gateways: list[GatewayRead]
    controllers: list[ControllerRead]


class CommandRead(BaseModel):
    id: UUID
    location_id: UUID
    location_code: str
    gateway_id: UUID
    gateway_code: str
    controller_id: UUID
    controller_code: str
    channel_number: int
    target_state: DesiredState
    status: CommandStatus
    reason: str
    attempt_count: int
    next_attempt_at: datetime
    sent_at: datetime | None
    acked_at: datetime | None
    last_error: str | None
    created_at: datetime


class PaginatedCommands(BaseModel):
    items: list[CommandRead]
    page: int
    page_size: int
    total: int
