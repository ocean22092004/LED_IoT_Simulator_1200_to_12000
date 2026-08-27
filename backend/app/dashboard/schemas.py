from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from backend.app.common.enums import DeviceStatus


class DashboardSummary(BaseModel):
    total_locations: int
    desired_on: int
    actual_on: int
    actual_unknown: int
    anniversaries_today: int
    active_visits: int
    gateways_online: int
    gateways_offline: int
    controllers_online: int
    controllers_offline: int
    suspected_failed_lamps: int


class DashboardAnniversaryItem(BaseModel):
    activation_id: UUID
    location_id: UUID
    location_code: str
    person_id: UUID | None
    person_name: str | None
    zone_code: str
    starts_at: datetime
    expires_at: datetime | None


class DashboardAnniversariesToday(BaseModel):
    local_date: date
    total: int
    items: list[DashboardAnniversaryItem]


class GatewayHealth(BaseModel):
    id: UUID
    code: str
    name: str
    status: DeviceStatus
    last_seen_at: datetime | None
    affected_locations: int


class ControllerHealth(BaseModel):
    id: UUID
    gateway_id: UUID
    gateway_code: str
    code: str
    address: int
    status: DeviceStatus
    last_seen_at: datetime | None
    affected_locations: int


class DeviceHealth(BaseModel):
    gateways: list[GatewayHealth]
    controllers: list[ControllerHealth]
