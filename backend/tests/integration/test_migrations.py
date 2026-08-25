import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.config import get_settings

pytestmark = pytest.mark.integration
PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_DATABASE = "memorial_migration_test"


async def execute_admin_statement(statement: str) -> None:
    admin_url = make_url(get_settings().database_url).set(database="postgres")
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def run_alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ | {"DATABASE_URL": database_url}

    def invoke() -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=PROJECT_ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    await asyncio.to_thread(invoke)


async def migration_database_counts(database_url: str) -> tuple[int, int, str | None]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            table_count = await connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM pg_tables
                    WHERE schemaname = 'public'
                      AND tablename <> 'alembic_version'
                    """
                )
            )
            enum_count = await connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM pg_type type
                    JOIN pg_namespace namespace ON namespace.oid = type.typnamespace
                    WHERE namespace.nspname = 'public'
                      AND type.typname IN (
                        'device_status', 'desired_state', 'actual_state',
                        'controller_output_state', 'lamp_health', 'activation_reason',
                        'command_status', 'user_role'
                      )
                    """
                )
            )
            revision = None
            if table_count:
                revision = await connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
    finally:
        await engine.dispose()

    return int(table_count or 0), int(enum_count or 0), revision


async def test_initial_migration_upgrade_downgrade_upgrade_round_trip():
    database_url = make_url(get_settings().database_url).set(
        database=MIGRATION_DATABASE
    ).render_as_string(hide_password=False)
    await execute_admin_statement(f'DROP DATABASE IF EXISTS "{MIGRATION_DATABASE}" WITH (FORCE)')
    await execute_admin_statement(f'CREATE DATABASE "{MIGRATION_DATABASE}"')
    try:
        await run_alembic(database_url, "upgrade", "head")
        assert await migration_database_counts(database_url) == (
            13,
            8,
            "0001_initial_schema",
        )

        await run_alembic(database_url, "downgrade", "base")
        assert await migration_database_counts(database_url) == (0, 0, None)

        await run_alembic(database_url, "upgrade", "head")
        assert await migration_database_counts(database_url) == (
            13,
            8,
            "0001_initial_schema",
        )
    finally:
        await execute_admin_statement(
            f'DROP DATABASE IF EXISTS "{MIGRATION_DATABASE}" WITH (FORCE)'
        )


def test_models_match_alembic_head():
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "No new upgrade operations detected" in completed.stdout


async def test_database_is_at_initial_schema_head(session: AsyncSession):
    revision = await session.scalar(text("SELECT version_num FROM alembic_version"))

    assert revision == "0001_initial_schema"


async def test_initial_migration_creates_all_section_15_tables(session: AsyncSession):
    result = await session.execute(
        text(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename <> 'alembic_version'
            ORDER BY tablename
            """
        )
    )

    assert set(result.scalars()) == {
        "activations",
        "anniversary_rules",
        "audit_logs",
        "controllers",
        "deceased_people",
        "device_events",
        "gateways",
        "lamp_states",
        "light_commands",
        "locations",
        "sites",
        "users",
        "zones",
    }


async def test_initial_migration_preserves_critical_index_semantics(
    session: AsyncSession,
):
    result = await session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname IN (
                'ix_activations_active_expires_at',
                'ix_light_commands_location_created_at_desc'
              )
            """
        )
    )
    indexes = dict(result.all())

    assert "WHERE (ended_at IS NULL)" in indexes[
        "ix_activations_active_expires_at"
    ]
    assert "(location_id, created_at DESC)" in indexes[
        "ix_light_commands_location_created_at_desc"
    ]
