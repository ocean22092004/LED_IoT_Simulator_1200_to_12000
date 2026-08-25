from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.common.enums import DEVICE_STATUS_DB, DeviceStatus
from backend.app.db.base import Base, UUIDPrimaryKeyMixin


class Gateway(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "gateways"
    __table_args__ = (UniqueConstraint("site_id", "code"),)

    site_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="RESTRICT"),
        nullable=False,
    )
    zone_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("zones.id", ondelete="RESTRICT"),
        nullable=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(
        DEVICE_STATUS_DB,
        nullable=False,
        default=DeviceStatus.UNKNOWN,
        server_default=DeviceStatus.UNKNOWN.value,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )


class Controller(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "controllers"
    __table_args__ = (
        UniqueConstraint("gateway_id", "code"),
        UniqueConstraint("gateway_id", "address"),
        CheckConstraint("channel_capacity > 0", name="channel_capacity_positive"),
    )

    gateway_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("gateways.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    address: Mapped[int] = mapped_column(Integer, nullable=False)
    channel_capacity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=64,
        server_default="64",
    )
    status: Mapped[DeviceStatus] = mapped_column(
        DEVICE_STATUS_DB,
        nullable=False,
        default=DeviceStatus.UNKNOWN,
        server_default=DeviceStatus.UNKNOWN.value,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
