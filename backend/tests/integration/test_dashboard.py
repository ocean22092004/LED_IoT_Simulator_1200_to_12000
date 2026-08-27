from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.service import create_access_token, hash_password
from backend.app.common.enums import (
    ActivationReason,
    ActualState,
    DesiredState,
    DeviceStatus,
    LampHealth,
    UserRole,
)
from backend.app.config import Settings
from backend.app.dashboard.service import (
    get_anniversaries_today,
    get_dashboard_summary,
    get_device_health,
)
from backend.app.db.models.activation import Activation
from backend.app.db.models.device import Controller
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.person import DeceasedPerson
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.tests.integration.conftest import MappedTopology

pytestmark = pytest.mark.integration
NOW = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)  # 10:00 Asia/Ho_Chi_Minh


async def ready() -> bool:
    return True


async def create_lamp(
    session: AsyncSession,
    topology: MappedTopology,
    code: str,
    channel: int,
    *,
    desired: DesiredState,
    actual: ActualState,
    health: LampHealth,
) -> LampState:
    location = await topology.create_location(code, channel)
    lamp = LampState(
        location_id=location.id,
        desired_state=desired,
        actual_state=actual,
        lamp_health=health,
    )
    session.add(lamp)
    await session.flush()
    return lamp


async def test_summary_aggregate_counts_are_correct(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    baseline = await get_dashboard_summary(session, now=NOW)
    mapped_topology.gateway.status = DeviceStatus.OFFLINE
    mapped_topology.controller.status = DeviceStatus.ONLINE
    on = await create_lamp(
        session,
        mapped_topology,
        f"DASH-ON-{uuid4().hex[:8]}",
        1,
        desired=DesiredState.ON,
        actual=ActualState.ON,
        health=LampHealth.SUSPECTED_FAILED,
    )
    unknown = await create_lamp(
        session,
        mapped_topology,
        f"DASH-UNKNOWN-{uuid4().hex[:8]}",
        2,
        desired=DesiredState.ON,
        actual=ActualState.UNKNOWN,
        health=LampHealth.UNKNOWN,
    )
    session.add_all(
        [
            Activation(
                location_id=on.location_id,
                reason=ActivationReason.VISIT,
                starts_at=NOW - timedelta(minutes=5),
                expires_at=NOW + timedelta(minutes=55),
            ),
            Activation(
                location_id=unknown.location_id,
                reason=ActivationReason.ANNIVERSARY,
                starts_at=NOW - timedelta(hours=3),
                expires_at=NOW + timedelta(hours=21),
            ),
        ]
    )
    await session.flush()

    summary = await get_dashboard_summary(session, now=NOW)

    assert summary.total_locations == baseline.total_locations + 2
    assert summary.desired_on == baseline.desired_on + 2
    assert summary.actual_on == baseline.actual_on + 1
    assert summary.actual_unknown == baseline.actual_unknown + 1
    assert summary.anniversaries_today == baseline.anniversaries_today + 1
    assert summary.active_visits == baseline.active_visits + 1
    assert summary.gateways_offline == baseline.gateways_offline + 1
    assert summary.controllers_online == baseline.controllers_online + 1
    assert summary.suspected_failed_lamps == baseline.suspected_failed_lamps + 1


async def test_anniversaries_today_lists_only_current_activation(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    person = DeceasedPerson(
        site_id=mapped_topology.site.id,
        full_name="Dashboard Anniversary",
    )
    session.add(person)
    await session.flush()
    current = await mapped_topology.create_location(f"DASH-ANN-{uuid4().hex[:8]}", 3)
    current.person_id = person.id
    expired = await mapped_topology.create_location(f"DASH-OLD-{uuid4().hex[:8]}", 4)
    session.add_all(
        [
            LampState(location_id=current.id),
            LampState(location_id=expired.id),
            Activation(
                location_id=current.id,
                reason=ActivationReason.ANNIVERSARY,
                starts_at=NOW - timedelta(hours=3),
                expires_at=NOW + timedelta(hours=21),
            ),
            Activation(
                location_id=expired.id,
                reason=ActivationReason.ANNIVERSARY,
                starts_at=NOW - timedelta(days=1, hours=3),
                expires_at=NOW - timedelta(hours=3),
                ended_at=NOW - timedelta(hours=3),
            ),
        ]
    )
    await session.flush()

    response = await get_anniversaries_today(session, now=NOW)

    matching = [item for item in response.items if item.location_id == current.id]
    assert response.local_date.isoformat() == "2026-08-27"
    assert len(matching) == 1
    assert matching[0].location_code == current.code
    assert matching[0].person_name == "Dashboard Anniversary"
    assert all(item.location_id != expired.id for item in response.items)


async def test_device_health_groups_affected_location_count(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> None:
    mapped_topology.gateway.status = DeviceStatus.OFFLINE
    mapped_topology.controller.status = DeviceStatus.OFFLINE
    locations = [
        await mapped_topology.create_location(f"DASH-DEVICE-{uuid4().hex[:8]}", channel)
        for channel in (5, 6, 7)
    ]
    session.add_all([LampState(location_id=location.id) for location in locations])
    empty_controller = Controller(
        gateway_id=mapped_topology.gateway.id,
        code=f"CTRL-DASH-{uuid4().hex[:8]}",
        address=2,
        channel_capacity=64,
        status=DeviceStatus.ONLINE,
    )
    session.add(empty_controller)
    await session.flush()

    response = await get_device_health(session)

    gateway = next(item for item in response.gateways if item.id == mapped_topology.gateway.id)
    controller = next(
        item for item in response.controllers if item.id == mapped_topology.controller.id
    )
    empty = next(item for item in response.controllers if item.id == empty_controller.id)
    assert gateway.affected_locations == 3
    assert controller.affected_locations == 3
    assert empty.affected_locations == 0


@pytest_asyncio.fixture
async def dashboard_client(
    session: AsyncSession,
) -> AsyncIterator[tuple[AsyncClient, dict[str, str]]]:
    user = User(
        username=f"dashboard-{uuid4().hex[:8]}",
        password_hash=hash_password("test-password"),
        role=UserRole.STAFF,
    )
    session.add(user)
    await session.flush()
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        jwt_secret=SecretStr("dashboard-test-secret-long-enough"),
    )
    app = create_app(settings=settings, readiness_probe=ready)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    headers = {
        "Authorization": "Bearer "
        + create_access_token(user_id=user.id, role=user.role, settings=settings)
    }
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client, headers


async def test_dashboard_routes_require_authentication_and_return_read_models(
    dashboard_client: tuple[AsyncClient, dict[str, str]],
) -> None:
    client, headers = dashboard_client

    unauthorized = await client.get("/api/v1/dashboard/summary")
    responses = [
        await client.get(path, headers=headers)
        for path in (
            "/api/v1/dashboard/summary",
            "/api/v1/dashboard/anniversaries-today",
            "/api/v1/dashboard/device-health",
        )
    ]

    assert unauthorized.status_code == 401
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert "total_locations" in responses[0].json()
    assert "items" in responses[1].json()
    assert set(responses[2].json()) == {"gateways", "controllers"}
