from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.service import create_access_token, hash_password
from backend.app.common.enums import UserRole
from backend.app.config import Settings
from backend.app.db.models.audit_log import AuditLog
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.app.simulator.service import get_simulator_client

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class SimulatorCall:
    method: str
    path: str
    payload: dict[str, object] | None


@dataclass
class RecordingSimulatorClient:
    status_code: int = 200
    calls: list[SimulatorCall] = field(default_factory=list)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None,
    ) -> httpx.Response:
        self.calls.append(SimulatorCall(method, path, json))
        return httpx.Response(
            self.status_code,
            json={"status": "ok", "path": path},
            request=httpx.Request(method, f"http://simulator{path}"),
        )


@dataclass(frozen=True)
class SimulatorAPIContext:
    client: AsyncClient
    upstream: RecordingSimulatorClient
    session: AsyncSession
    users: dict[UserRole, User]
    headers: dict[UserRole, dict[str, str]]


async def ready() -> bool:
    return True


async def build_context(
    session: AsyncSession,
    *,
    enabled: bool,
) -> AsyncIterator[SimulatorAPIContext]:
    suffix = uuid4().hex[:8]
    users = {
        role: User(
            username=f"simulator-{role.value.lower()}-{suffix}",
            password_hash=hash_password("test-password"),
            role=role,
        )
        for role in UserRole
    }
    session.add_all(users.values())
    await session.flush()
    settings = Settings(
        _env_file=None,
        simulator_admin_enabled=enabled,
        jwt_secret=SecretStr("simulator-api-test-secret-long-enough"),
    )
    headers = {
        role: {
            "Authorization": "Bearer "
            + create_access_token(user_id=user.id, role=role, settings=settings)
        }
        for role, user in users.items()
    }
    upstream = RecordingSimulatorClient()
    app = create_app(settings=settings, readiness_probe=ready)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    async def override_simulator_client() -> AsyncIterator[RecordingSimulatorClient]:
        yield upstream

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_simulator_client] = override_simulator_client
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield SimulatorAPIContext(client, upstream, session, users, headers)


@pytest_asyncio.fixture
async def simulator_api(session: AsyncSession) -> AsyncIterator[SimulatorAPIContext]:
    async for context in build_context(session, enabled=True):
        yield context


async def test_technician_can_control_all_fault_injection_endpoints(
    simulator_api: SimulatorAPIContext,
) -> None:
    context = simulator_api
    requests: list[tuple[str, str, dict[str, object] | None]] = [
        ("POST", "/api/v1/simulator/gateways/GW-A/offline", None),
        ("POST", "/api/v1/simulator/gateways/GW-A/online", None),
        ("POST", "/api/v1/simulator/controllers/CTRL-A-04/offline", None),
        ("POST", "/api/v1/simulator/controllers/CTRL-A-04/online", None),
        (
            "POST",
            "/api/v1/simulator/locations/A250/fault",
            {"fault": "BURNED_OUT"},
        ),
        ("DELETE", "/api/v1/simulator/locations/A250/fault", None),
        ("POST", "/api/v1/simulator/controllers/CTRL-A-04/reset", None),
        (
            "POST",
            "/api/v1/simulator/settings",
            {"command_latency_ms": 1000, "ack_drop_rate": 0.25},
        ),
    ]

    for method, path, payload in requests:
        response = await context.client.request(
            method,
            path,
            json=payload,
            headers=context.headers[UserRole.TECHNICIAN],
        )
        assert response.status_code == 200

    assert context.upstream.calls == [
        SimulatorCall("POST", "/internal/gateways/GW-A/offline", None),
        SimulatorCall("POST", "/internal/gateways/GW-A/online", None),
        SimulatorCall("POST", "/internal/controllers/CTRL-A-04/offline", None),
        SimulatorCall("POST", "/internal/controllers/CTRL-A-04/online", None),
        SimulatorCall(
            "POST",
            "/internal/locations/A250/fault",
            {"fault": "BURNED_OUT"},
        ),
        SimulatorCall("DELETE", "/internal/locations/A250/fault", None),
        SimulatorCall("POST", "/internal/controllers/CTRL-A-04/reset", None),
        SimulatorCall(
            "POST",
            "/internal/settings",
            {"command_latency_ms": 1000, "ack_drop_rate": 0.25},
        ),
    ]
    actions = list(
        await context.session.scalars(
            select(AuditLog.action)
            .where(AuditLog.user_id == context.users[UserRole.TECHNICIAN].id)
            .order_by(AuditLog.id)
        )
    )
    assert actions == [
        "SIMULATOR_FAULT_SET",
        "SIMULATOR_FAULT_CLEARED",
        "SIMULATOR_FAULT_SET",
        "SIMULATOR_FAULT_CLEARED",
        "SIMULATOR_FAULT_SET",
        "SIMULATOR_FAULT_CLEARED",
        "SIMULATOR_FAULT_SET",
        "SIMULATOR_FAULT_SET",
    ]


async def test_staff_cannot_control_simulator(
    simulator_api: SimulatorAPIContext,
) -> None:
    response = await simulator_api.client.post(
        "/api/v1/simulator/gateways/GW-A/offline",
        headers=simulator_api.headers[UserRole.STAFF],
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_FORBIDDEN"
    assert simulator_api.upstream.calls == []


async def test_simulator_routes_are_disabled_by_configuration(
    session: AsyncSession,
) -> None:
    async for context in build_context(session, enabled=False):
        response = await context.client.post(
            "/api/v1/simulator/gateways/GW-A/offline",
            headers=context.headers[UserRole.ADMIN],
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "SIMULATOR_ADMIN_DISABLED"
        assert context.upstream.calls == []


async def test_upstream_not_found_uses_public_error_contract(
    simulator_api: SimulatorAPIContext,
) -> None:
    simulator_api.upstream.status_code = 404

    response = await simulator_api.client.post(
        "/api/v1/simulator/gateways/GW-Z/offline",
        headers=simulator_api.headers[UserRole.ADMIN],
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SIMULATOR_TARGET_NOT_FOUND"
    audits = list(
        await simulator_api.session.scalars(
            select(AuditLog).where(
                AuditLog.user_id == simulator_api.users[UserRole.ADMIN].id
            )
        )
    )
    assert audits == []
