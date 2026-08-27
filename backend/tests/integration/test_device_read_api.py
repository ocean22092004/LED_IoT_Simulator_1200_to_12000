from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.service import create_access_token, hash_password
from backend.app.common.enums import (
    CommandStatus,
    DesiredState,
    DeviceStatus,
    UserRole,
)
from backend.app.config import Settings
from backend.app.db.models.command import LightCommand
from backend.app.db.models.device import Controller
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.tests.integration.conftest import MappedTopology

pytestmark = pytest.mark.integration


async def ready() -> bool:
    return True


@dataclass(frozen=True)
class DeviceAPIContext:
    client: AsyncClient
    session: AsyncSession
    topology: MappedTopology
    headers: dict[str, str]
    location_ids: tuple[str, str]
    empty_controller: Controller


@pytest_asyncio.fixture
async def device_api(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> AsyncIterator[DeviceAPIContext]:
    mapped_topology.gateway.status = DeviceStatus.OFFLINE
    mapped_topology.controller.status = DeviceStatus.OFFLINE
    first = await mapped_topology.create_location(f"DEV-READ-{uuid4().hex[:8]}", 1)
    second = await mapped_topology.create_location(f"DEV-READ-{uuid4().hex[:8]}", 2)
    session.add_all([LampState(location_id=first.id), LampState(location_id=second.id)])
    empty_controller = Controller(
        gateway_id=mapped_topology.gateway.id,
        code=f"CTRL-EMPTY-{uuid4().hex[:8]}",
        address=2,
        channel_capacity=64,
        status=DeviceStatus.ONLINE,
    )
    session.add(empty_controller)
    user = User(
        username=f"device-reader-{uuid4().hex[:8]}",
        password_hash=hash_password("test-password"),
        role=UserRole.STAFF,
    )
    session.add(user)
    await session.flush()
    settings = Settings(
        _env_file=None,
        jwt_secret=SecretStr("device-read-test-secret-long-enough"),
        frontend_origin="http://admin.test",
    )
    token = create_access_token(user_id=user.id, role=user.role, settings=settings)
    app = create_app(settings=settings, readiness_probe=ready)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield DeviceAPIContext(
            client=client,
            session=session,
            topology=mapped_topology,
            headers={"Authorization": f"Bearer {token}"},
            location_ids=(str(first.id), str(second.id)),
            empty_controller=empty_controller,
        )


async def test_device_read_routes_require_authentication(
    device_api: DeviceAPIContext,
) -> None:
    for path in (
        "/api/v1/gateways",
        "/api/v1/controllers",
        "/api/v1/devices/offline",
        "/api/v1/commands",
    ):
        response = await device_api.client.get(path)
        assert response.status_code == 401


async def test_gateway_and_controller_reads_include_affected_locations(
    device_api: DeviceAPIContext,
) -> None:
    gateway_response = await device_api.client.get(
        "/api/v1/gateways",
        headers=device_api.headers,
    )
    controller_response = await device_api.client.get(
        "/api/v1/controllers",
        params={"gateway_id": str(device_api.topology.gateway.id)},
        headers=device_api.headers,
    )
    gateway_detail = await device_api.client.get(
        f"/api/v1/gateways/{device_api.topology.gateway.id}",
        headers=device_api.headers,
    )
    controller_detail = await device_api.client.get(
        f"/api/v1/controllers/{device_api.topology.controller.id}",
        headers=device_api.headers,
    )

    assert gateway_response.status_code == 200
    gateway = next(
        item
        for item in gateway_response.json()
        if item["id"] == str(device_api.topology.gateway.id)
    )
    assert gateway["affected_locations"] == 2
    assert controller_response.status_code == 200
    controllers = controller_response.json()
    mapped = next(
        item
        for item in controllers
        if item["id"] == str(device_api.topology.controller.id)
    )
    empty = next(
        item
        for item in controllers
        if item["id"] == str(device_api.empty_controller.id)
    )
    assert mapped["affected_locations"] == 2
    assert empty["affected_locations"] == 0
    assert len(gateway_detail.json()["controllers"]) == 2
    assert controller_detail.json()["affected_locations"] == 2


async def test_offline_devices_are_grouped_by_type(device_api: DeviceAPIContext) -> None:
    response = await device_api.client.get(
        "/api/v1/devices/offline",
        headers=device_api.headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["gateways"]] == [
        str(device_api.topology.gateway.id)
    ]
    assert [item["id"] for item in body["controllers"]] == [
        str(device_api.topology.controller.id)
    ]


async def test_commands_support_status_location_filters_and_pagination(
    device_api: DeviceAPIContext,
) -> None:
    location_id = device_api.location_ids[0]
    now = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)
    device_api.session.add_all(
        [
            LightCommand(
                location_id=location_id,
                gateway_id=device_api.topology.gateway.id,
                controller_id=device_api.topology.controller.id,
                channel_number=1,
                target_state=DesiredState.ON,
                status=CommandStatus.FAILED,
                reason="VISIT",
                next_attempt_at=now,
                last_error="ACK timeout",
            ),
            LightCommand(
                location_id=device_api.location_ids[1],
                gateway_id=device_api.topology.gateway.id,
                controller_id=device_api.topology.controller.id,
                channel_number=2,
                target_state=DesiredState.OFF,
                status=CommandStatus.ACKED,
                reason="VISIT_ENDED",
                next_attempt_at=now,
            ),
        ]
    )
    await device_api.session.flush()

    response = await device_api.client.get(
        "/api/v1/commands",
        params={
            "status": "FAILED",
            "location_id": location_id,
            "page": 1,
            "page_size": 1,
        },
        headers=device_api.headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 1
    assert body["items"][0]["status"] == "FAILED"
    assert body["items"][0]["location_id"] == location_id
    assert body["items"][0]["location_code"].startswith("DEV-READ-")


async def test_cors_allows_only_configured_frontend_origin(
    device_api: DeviceAPIContext,
) -> None:
    allowed = await device_api.client.options(
        "/api/v1/gateways",
        headers={
            "Origin": "http://admin.test",
            "Access-Control-Request-Method": "GET",
        },
    )
    denied = await device_api.client.options(
        "/api/v1/gateways",
        headers={
            "Origin": "http://other.test",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://admin.test"
    assert "access-control-allow-origin" not in denied.headers
