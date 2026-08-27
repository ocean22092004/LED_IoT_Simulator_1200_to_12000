from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.app.common.enums import (
    ActivationReason,
    ActualState,
    CommandStatus,
    DesiredState,
    LampHealth,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ZoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    site_id: UUID
    code: str
    name: str
    sort_order: int
    is_active: bool


class ZoneBrief(BaseModel):
    code: str
    name: str


class PersonBrief(BaseModel):
    id: UUID
    full_name: str


class AnniversaryBrief(BaseModel):
    lunar_day: int
    lunar_month: int
    is_leap_month: bool


class HardwareBrief(BaseModel):
    gateway_code: str
    controller_code: str
    channel: int


class LightBrief(BaseModel):
    desired_state: DesiredState
    actual_state: ActualState
    lamp_health: LampHealth
    current_ma: Decimal | None
    active_reasons: list[ActivationReason]
    last_reported_at: datetime | None


class LocationListLightBrief(BaseModel):
    desired_state: DesiredState
    actual_state: ActualState
    lamp_health: LampHealth


class ActiveActivationBrief(BaseModel):
    id: UUID
    reason: ActivationReason
    starts_at: datetime
    expires_at: datetime | None


class LocationCommandBrief(BaseModel):
    id: UUID
    target_state: DesiredState
    status: CommandStatus
    reason: str
    attempt_count: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None
    acked_at: datetime | None


class LocationEventBrief(BaseModel):
    id: int
    event_type: str
    occurred_at: datetime
    received_at: datetime
    payload: dict[str, Any]


class LocationSummary(BaseModel):
    id: UUID
    site_id: UUID
    code: str
    zone: ZoneBrief
    person: PersonBrief | None
    hardware: HardwareBrief
    light: LocationListLightBrief
    is_active: bool


class LocationDetail(BaseModel):
    id: UUID
    site_id: UUID
    code: str
    zone: ZoneBrief
    person: PersonBrief | None
    hardware: HardwareBrief
    is_active: bool
    anniversary: AnniversaryBrief | None
    light: LightBrief
    active_activations: list[ActiveActivationBrief]
    recent_commands: list[LocationCommandBrief]
    recent_events: list[LocationEventBrief]


class PaginatedLocations(BaseModel):
    items: list[LocationSummary]
    page: int
    page_size: int
    total: int


class LocationCreate(BaseModel):
    site_id: UUID
    zone_id: UUID
    code: NonEmptyText
    person_id: UUID | None = None
    gateway_id: UUID
    controller_id: UUID
    channel_number: int = Field(ge=1)
    is_active: bool = True


class LocationUpdate(BaseModel):
    site_id: UUID | None = None
    zone_id: UUID | None = None
    code: NonEmptyText | None = None
    person_id: UUID | None = None
    gateway_id: UUID | None = None
    controller_id: UUID | None = None
    channel_number: int | None = Field(default=None, ge=1)
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> Self:
        nullable_fields = {"person_id"}
        invalid_fields = sorted(
            field
            for field in self.model_fields_set - nullable_fields
            if getattr(self, field) is None
        )
        if invalid_fields:
            raise ValueError(f"fields cannot be null: {', '.join(invalid_fields)}")
        return self


class PersonCreate(BaseModel):
    site_id: UUID
    full_name: NonEmptyText
    birth_date: date | None = None
    death_date: date | None = None
    notes: str | None = None


class PersonUpdate(BaseModel):
    full_name: NonEmptyText | None = None
    birth_date: date | None = None
    death_date: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def reject_null_name(self) -> Self:
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("full_name cannot be null")
        return self


class PersonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    site_id: UUID
    full_name: str
    birth_date: date | None
    death_date: date | None
    notes: str | None
