from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.anniversaries.lunar import VietnameseLunarCalendarProvider
from backend.app.anniversaries.service import sync_anniversaries_for_local_date
from backend.app.auth.service import create_access_token, hash_password
from backend.app.common.enums import ActivationReason, UserRole
from backend.app.config import Settings
from backend.app.db.models.activation import Activation
from backend.app.db.models.anniversary import AnniversaryRule
from backend.app.db.models.audit_log import AuditLog
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.models.person import DeceasedPerson
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.tests.integration.conftest import MappedTopology

pytestmark = pytest.mark.integration


async def ready() -> bool:
    return True


async def test_anniversary_sync_is_idempotent_and_uses_local_midnight(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    person = DeceasedPerson(
        site_id=mapped_topology.site.id,
        full_name="Người đã khuất ngày Tết",
    )
    session.add(person)
    await session.flush()
    location = Location(
        site_id=mapped_topology.site.id,
        zone_id=mapped_topology.zone.id,
        code="TET001",
        person_id=person.id,
        gateway_id=mapped_topology.gateway.id,
        controller_id=mapped_topology.controller.id,
        channel_number=1,
    )
    session.add(location)
    await session.flush()

    local_date = date(2026, 2, 17)
    # Settle any matching rules that may already exist in a developer database.
    await sync_anniversaries_for_local_date(local_date, session=session)
    session.add(
        AnniversaryRule(
            person_id=person.id,
            location_id=location.id,
            lunar_day=1,
            lunar_month=1,
            is_leap_month=False,
        )
    )
    await session.flush()

    assert await sync_anniversaries_for_local_date(local_date, session=session) == 1
    assert await sync_anniversaries_for_local_date(local_date, session=session) == 0

    activation = await session.scalar(
        select(Activation).where(Activation.location_id == location.id)
    )
    assert activation is not None
    assert activation.reason is ActivationReason.ANNIVERSARY
    assert activation.starts_at == datetime(2026, 2, 16, 17, 0, tzinfo=UTC)
    assert activation.expires_at == datetime(2026, 2, 17, 17, 0, tzinfo=UTC)
    assert activation.dedupe_key == "anniversary:2026-02-17"
    count = await session.scalar(
        select(func.count())
        .select_from(Activation)
        .where(Activation.location_id == location.id)
    )
    assert count == 1


@pytest_asyncio.fixture
async def anniversary_client(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> AsyncIterator[tuple[AsyncClient, dict[str, str], Location, User]]:
    suffix = uuid4().hex[:8]
    person = DeceasedPerson(
        site_id=mapped_topology.site.id,
        full_name="Người đã khuất API Anniversary",
    )
    session.add(person)
    await session.flush()
    location = Location(
        site_id=mapped_topology.site.id,
        zone_id=mapped_topology.zone.id,
        code=f"ANN-{suffix}",
        person_id=person.id,
        gateway_id=mapped_topology.gateway.id,
        controller_id=mapped_topology.controller.id,
        channel_number=1,
    )
    session.add(location)
    await session.flush()
    session.add(LampState(location_id=location.id))

    admin = User(
        username=f"anniversary-admin-{suffix}",
        password_hash=hash_password("test-password"),
        role=UserRole.ADMIN,
    )
    session.add(admin)
    await session.flush()

    settings = Settings(
        _env_file=None,
        jwt_secret=SecretStr("anniversary-api-test-secret-long-enough"),
    )
    token = create_access_token(user_id=admin.id, role=admin.role, settings=settings)
    app = create_app(settings=settings, readiness_probe=ready)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client, {"Authorization": f"Bearer {token}"}, location, admin


async def test_anniversary_rule_api_audits_put_and_delete(
    anniversary_client: tuple[AsyncClient, dict[str, str], Location, User],
    session: AsyncSession,
) -> None:
    client, headers, location, admin = anniversary_client
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    lunar_today = VietnameseLunarCalendarProvider().from_solar(today)

    response = await client.put(
        f"/api/v1/locations/{location.id}/anniversary",
        json={
            "lunar_day": lunar_today.day,
            "lunar_month": lunar_today.month,
            "is_leap_month": lunar_today.is_leap_month,
            "is_enabled": True,
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["location_id"] == str(location.id)

    response = await client.get("/api/v1/anniversaries/today", headers=headers)
    assert response.status_code == 200
    assert location.code in [item["location_code"] for item in response.json()["items"]]

    response = await client.delete(
        f"/api/v1/locations/{location.id}/anniversary",
        headers=headers,
    )
    assert response.status_code == 204
    assert await session.scalar(
        select(AnniversaryRule).where(AnniversaryRule.location_id == location.id)
    ) is None

    audits = list(
        await session.scalars(
            select(AuditLog)
            .where(
                AuditLog.user_id == admin.id,
                AuditLog.entity_id == location.id,
                AuditLog.action == "ANNIVERSARY_RULE_CHANGED",
            )
            .order_by(AuditLog.id)
        )
    )
    assert len(audits) == 2
