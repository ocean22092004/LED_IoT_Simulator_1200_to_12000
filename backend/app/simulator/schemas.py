from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fault: Literal["BURNED_OUT", "STUCK_OFF"] = "BURNED_OUT"


class SimulatorSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_latency_ms: int | None = Field(default=None, ge=0)
    ack_drop_rate: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_setting(self) -> Self:
        if self.command_latency_ms is None and self.ack_drop_rate is None:
            raise ValueError("at least one simulator setting is required")
        return self
