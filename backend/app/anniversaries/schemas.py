from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AnniversaryRuleUpsert(BaseModel):
    lunar_day: int = Field(ge=1, le=30)
    lunar_month: int = Field(ge=1, le=12)
    is_leap_month: bool = False
    is_enabled: bool = True


class AnniversaryRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    person_id: UUID
    location_id: UUID
    lunar_day: int
    lunar_month: int
    is_leap_month: bool
    is_enabled: bool


class LunarDateResponse(BaseModel):
    year: int
    month: int
    day: int
    is_leap_month: bool


class AnniversaryTodayItem(BaseModel):
    location_id: UUID
    location_code: str
    person_id: UUID
    person_name: str
    rule_id: UUID


class AnniversariesTodayResponse(BaseModel):
    local_date: date
    lunar_date: LunarDateResponse
    items: list[AnniversaryTodayItem]
