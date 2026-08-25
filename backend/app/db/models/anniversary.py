from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, SmallInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AnniversaryRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "anniversary_rules"
    __table_args__ = (
        UniqueConstraint("location_id"),
        CheckConstraint("lunar_day BETWEEN 1 AND 30", name="lunar_day_range"),
        CheckConstraint("lunar_month BETWEEN 1 AND 12", name="lunar_month_range"),
    )

    person_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("deceased_people.id", ondelete="RESTRICT"),
        nullable=False,
    )
    location_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lunar_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    lunar_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_leap_month: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
