from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.common.enums import DesiredState


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
