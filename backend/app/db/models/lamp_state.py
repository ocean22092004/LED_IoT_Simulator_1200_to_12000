from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.common.enums import (
    ACTUAL_STATE_DB,
    CONTROLLER_OUTPUT_STATE_DB,
    DESIRED_STATE_DB,
    LAMP_HEALTH_DB,
    ActualState,
    ControllerOutputState,
    DesiredState,
    LampHealth,
)
from backend.app.db.base import Base


class LampState(Base):
    __tablename__ = "lamp_states"

    location_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    desired_state: Mapped[DesiredState] = mapped_column(
        DESIRED_STATE_DB,
        nullable=False,
        default=DesiredState.OFF,
        server_default=DesiredState.OFF.value,
    )
    actual_state: Mapped[ActualState] = mapped_column(
        ACTUAL_STATE_DB,
        nullable=False,
        default=ActualState.UNKNOWN,
        server_default=ActualState.UNKNOWN.value,
    )
    controller_output_state: Mapped[ControllerOutputState] = mapped_column(
        CONTROLLER_OUTPUT_STATE_DB,
        nullable=False,
        default=ControllerOutputState.UNKNOWN,
        server_default=ControllerOutputState.UNKNOWN.value,
    )
    lamp_health: Mapped[LampHealth] = mapped_column(
        LAMP_HEALTH_DB,
        nullable=False,
        default=LampHealth.UNKNOWN,
        server_default=LampHealth.UNKNOWN.value,
    )
    current_ma: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    desired_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_device_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
