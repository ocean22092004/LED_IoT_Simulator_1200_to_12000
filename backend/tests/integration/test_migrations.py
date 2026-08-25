import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_ROOT = Path(__file__).resolve().parents[3]


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
