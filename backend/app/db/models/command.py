from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.common.enums import (
    COMMAND_STATUS_DB,
    DESIRED_STATE_DB,
    CommandStatus,
    DesiredState,
)
from backend.app.db.base import Base, UUIDPrimaryKeyMixin


class LightCommand(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "light_commands"
    __table_args__ = (
        Index("ix_light_commands_status_next_attempt_at", "status", "next_attempt_at"),
        Index(
            "ix_light_commands_location_created_at_desc",
            "location_id",
            text("created_at DESC"),
        ),
    )

    location_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gateway_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("gateways.id", ondelete="RESTRICT"),
        nullable=False,
    )
    controller_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("controllers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    channel_number: Mapped[int] = mapped_column(Integer, nullable=False)
    target_state: Mapped[DesiredState] = mapped_column(DESIRED_STATE_DB, nullable=False)
    status: Mapped[CommandStatus] = mapped_column(
        COMMAND_STATUS_DB,
        nullable=False,
        default=CommandStatus.PENDING,
        server_default=CommandStatus.PENDING.value,
    )
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
