from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.common.enums import ActivationReason


class VisitStartRequest(BaseModel):
    duration_minutes: Literal[30, 60, 120, 240] | None = 60


class ActivationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    location_id: UUID
    reason: ActivationReason
    starts_at: datetime
    expires_at: datetime | None
    created_by_user_id: UUID | None
    ended_at: datetime | None
    created_at: datetime
