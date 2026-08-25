from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.common.enums import ACTIVATION_REASON_DB, ActivationReason
from backend.app.db.base import Base, UUIDPrimaryKeyMixin


class Activation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "activations"
    __table_args__ = (
        UniqueConstraint("location_id", "dedupe_key"),
        Index("ix_activations_location_ended_at", "location_id", "ended_at"),
        Index(
            "ix_activations_active_expires_at",
            "expires_at",
            postgresql_where=text("ended_at IS NULL"),
        ),
        Index("ix_activations_reason_starts_at", "reason", "starts_at"),
    )

    location_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[ActivationReason] = mapped_column(ACTIVATION_REASON_DB, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
