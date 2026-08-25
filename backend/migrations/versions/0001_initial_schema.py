"""Create the complete initial simulator schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

device_status = postgresql.ENUM(
    "ONLINE", "OFFLINE", "UNKNOWN", name="device_status", create_type=False
)
desired_state = postgresql.ENUM("ON", "OFF", name="desired_state", create_type=False)
actual_state = postgresql.ENUM("ON", "OFF", "UNKNOWN", name="actual_state", create_type=False)
controller_output_state = postgresql.ENUM(
    "ON", "OFF", "UNKNOWN", name="controller_output_state", create_type=False
)
lamp_health = postgresql.ENUM(
    "OK", "SUSPECTED_FAILED", "UNKNOWN", name="lamp_health", create_type=False
)
activation_reason = postgresql.ENUM(
    "ANNIVERSARY", "VISIT", "MANUAL_ON", name="activation_reason", create_type=False
)
command_status = postgresql.ENUM(
    "PENDING", "SENT", "ACKED", "FAILED", name="command_status", create_type=False
)
user_role = postgresql.ENUM(
    "ADMIN", "STAFF", "TECHNICIAN", name="user_role", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        device_status,
        desired_state,
        actual_state,
        controller_output_state,
        lamp_health,
        activation_reason,
        command_status,
        user_role,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default="Asia/Ho_Chi_Minh",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "code"),
    )
    op.create_table(
        "deceased_people",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("death_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "gateways",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", device_status, server_default="UNKNOWN", nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("firmware_version", sa.String(length=64), nullable=True),
        sa.Column("is_simulated", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "code"),
    )
    op.create_table(
        "controllers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("address", sa.Integer(), nullable=False),
        sa.Column("channel_capacity", sa.Integer(), server_default="64", nullable=False),
        sa.Column("status", device_status, server_default="UNKNOWN", nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint(
            "channel_capacity > 0",
            name=op.f("ck_controllers_channel_capacity_positive"),
        ),
        sa.ForeignKeyConstraint(["gateway_id"], ["gateways.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gateway_id", "address"),
        sa.UniqueConstraint("gateway_id", "code"),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("controller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_number", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "channel_number >= 1",
            name=op.f("ck_locations_channel_number_positive"),
        ),
        sa.ForeignKeyConstraint(["controller_id"], ["controllers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["gateway_id"], ["gateways.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["person_id"], ["deceased_people.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("controller_id", "channel_number"),
        sa.UniqueConstraint("site_id", "code"),
    )
    op.create_table(
        "anniversary_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lunar_day", sa.SmallInteger(), nullable=False),
        sa.Column("lunar_month", sa.SmallInteger(), nullable=False),
        sa.Column("is_leap_month", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "lunar_day BETWEEN 1 AND 30",
            name=op.f("ck_anniversary_rules_lunar_day_range"),
        ),
        sa.CheckConstraint(
            "lunar_month BETWEEN 1 AND 12",
            name=op.f("ck_anniversary_rules_lunar_month_range"),
        ),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["person_id"], ["deceased_people.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("location_id"),
    )
    op.create_table(
        "activations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", activation_reason, nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=160), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("location_id", "dedupe_key"),
    )
    op.create_index(
        "ix_activations_active_expires_at",
        "activations",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_index(
        "ix_activations_location_ended_at",
        "activations",
        ["location_id", "ended_at"],
        unique=False,
    )
    op.create_index(
        "ix_activations_reason_starts_at",
        "activations",
        ["reason", "starts_at"],
        unique=False,
    )
    op.create_table(
        "lamp_states",
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("desired_state", desired_state, server_default="OFF", nullable=False),
        sa.Column("actual_state", actual_state, server_default="UNKNOWN", nullable=False),
        sa.Column(
            "controller_output_state",
            controller_output_state,
            server_default="UNKNOWN",
            nullable=False,
        ),
        sa.Column("lamp_health", lamp_health, server_default="UNKNOWN", nullable=False),
        sa.Column("current_ma", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("desired_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_device_report_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.BigInteger(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("location_id"),
    )
    op.create_table(
        "light_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("controller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_number", sa.Integer(), nullable=False),
        sa.Column("target_state", desired_state, nullable=False),
        sa.Column("status", command_status, server_default="PENDING", nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["controller_id"], ["controllers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["gateway_id"], ["gateways.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_light_commands_location_created_at_desc",
        "light_commands",
        ["location_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_light_commands_status_next_attempt_at",
        "light_commands",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_table(
        "device_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("controller_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("device_events")
    op.drop_index("ix_light_commands_status_next_attempt_at", table_name="light_commands")
    op.drop_index("ix_light_commands_location_created_at_desc", table_name="light_commands")
    op.drop_table("light_commands")
    op.drop_table("lamp_states")
    op.drop_index("ix_activations_reason_starts_at", table_name="activations")
    op.drop_index("ix_activations_location_ended_at", table_name="activations")
    op.drop_index("ix_activations_active_expires_at", table_name="activations")
    op.drop_table("activations")
    op.drop_table("anniversary_rules")
    op.drop_table("locations")
    op.drop_table("users")
    op.drop_table("controllers")
    op.drop_table("gateways")
    op.drop_table("deceased_people")
    op.drop_table("zones")
    op.drop_table("sites")

    bind = op.get_bind()
    for enum_type in (
        user_role,
        command_status,
        activation_reason,
        lamp_health,
        controller_output_state,
        actual_state,
        desired_state,
        device_status,
    ):
        enum_type.drop(bind, checkfirst=True)
