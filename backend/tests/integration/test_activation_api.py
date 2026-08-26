from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.activations.service import create_activation
from backend.app.auth.service import create_access_token, hash_password
from backend.app.common.enums import ActivationReason, DesiredState, UserRole
from backend.app.config import Settings
from backend.app.db.models.activation import Activation
from backend.app.db.models.audit_log import AuditLog
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.tests.integration.conftest import MappedTopology

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class ActivationAPIContext:
    client: AsyncClient
    session: AsyncSession
    location: Location
    lamp: LampState
    users: dict[UserRole, User]
    headers: dict[UserRole, dict[str, str]]


async def ready() -> bool:
    return True


@pytest_asyncio.fixture
async def activation_api(
    session: AsyncSession,
    mapped_topology: MappedTopology,
) -> AsyncIterator[ActivationAPIContext]:
    suffix = uuid4().hex[:8]
    location = await mapped_topology.create_location(f"ACT-API-{suffix}", 20)
    lamp = LampState(location_id=location.id)
    session.add(lamp)
    users = {
        role: User(
            username=f"activation-{role.value.lower()}-{suffix}",
            password_hash=hash_password("test-password"),
            role=role,
        )
        for role in UserRole
    }
    session.add_all(users.values())
    await session.flush()

    settings = Settings(
        _env_file=None,
        jwt_secret=SecretStr("activation-api-test-secret-long-enough"),
    )
    headers = {
        role: {
            "Authorization": "Bearer "
            + create_access_token(user_id=user.id, role=role, settings=settings)
        }
        for role, user in users.items()
    }
    app = create_app(settings=settings, readiness_probe=ready)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield ActivationAPIContext(client, session, location, lamp, users, headers)


async def test_staff_can_start_and_end_visit_with_audit(
    activation_api: ActivationAPIContext,
) -> None:
    context = activation_api

    response = await context.client.post(
        f"/api/v1/locations/{context.location.id}/visits",
        json={"duration_minutes": 30},
        headers=context.headers[UserRole.STAFF],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["reason"] == "VISIT"
    assert body["expires_at"] is not None
    assert context.lamp.desired_state is DesiredState.ON

    response = await context.client.post(
        f"/api/v1/activations/{body['id']}/end",
        headers=context.headers[UserRole.STAFF],
    )

    assert response.status_code == 200
    assert response.json()["ended_at"] is not None
    assert context.lamp.desired_state is DesiredState.OFF
    audits = list(
        await context.session.scalars(
            select(AuditLog)
            .where(AuditLog.user_id == context.users[UserRole.STAFF].id)
            .order_by(AuditLog.id)
        )
    )
    assert [audit.action for audit in audits] == ["VISIT_STARTED", "VISIT_ENDED"]
    assert all(audit.entity_id is not None for audit in audits)


async def test_visit_accepts_until_manually_ended_and_idempotency_key(
    activation_api: ActivationAPIContext,
) -> None:
    context = activation_api
    request_headers = {
        **context.headers[UserRole.STAFF],
        "Idempotency-Key": "visit-from-front-desk-42",
    }

    first = await context.client.post(
        f"/api/v1/locations/{context.location.id}/visits",
        json={"duration_minutes": None},
        headers=request_headers,
    )
    second = await context.client.post(
        f"/api/v1/locations/{context.location.id}/visits",
        json={"duration_minutes": None},
        headers=request_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["expires_at"] is None
    activations = list(
        await context.session.scalars(
            select(Activation).where(Activation.location_id == context.location.id)
        )
    )
    assert len(activations) == 1


@pytest.mark.parametrize("duration", [0, 15, 45, 241])
async def test_visit_rejects_unsupported_duration(
    activation_api: ActivationAPIContext,
    duration: int,
) -> None:
    response = await activation_api.client.post(
        f"/api/v1/locations/{activation_api.location.id}/visits",
        json={"duration_minutes": duration},
        headers=activation_api.headers[UserRole.STAFF],
    )

    assert response.status_code == 422


async def test_staff_cannot_manual_on(activation_api: ActivationAPIContext) -> None:
    response = await activation_api.client.post(
        f"/api/v1/locations/{activation_api.location.id}/manual-on",
        headers=activation_api.headers[UserRole.STAFF],
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_FORBIDDEN"


async def test_technician_can_manual_on_and_off_with_audit(
    activation_api: ActivationAPIContext,
) -> None:
    context = activation_api

    on_response = await context.client.post(
        f"/api/v1/locations/{context.location.id}/manual-on",
        headers=context.headers[UserRole.TECHNICIAN],
    )
    duplicate_response = await context.client.post(
        f"/api/v1/locations/{context.location.id}/manual-on",
        headers=context.headers[UserRole.TECHNICIAN],
    )

    assert on_response.status_code == 201
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["id"] == on_response.json()["id"]
    assert context.lamp.desired_state is DesiredState.ON

    off_response = await context.client.post(
        f"/api/v1/locations/{context.location.id}/manual-off",
        headers=context.headers[UserRole.TECHNICIAN],
    )

    assert off_response.status_code == 200
    assert off_response.json()["ended_at"] is not None
    assert context.lamp.desired_state is DesiredState.OFF
    audits = list(
        await context.session.scalars(
            select(AuditLog)
            .where(AuditLog.user_id == context.users[UserRole.TECHNICIAN].id)
            .order_by(AuditLog.id)
        )
    )
    assert [audit.action for audit in audits] == [
        "MANUAL_ON_STARTED",
        "MANUAL_ON_ENDED",
    ]


async def test_manual_off_does_not_end_anniversary(
    activation_api: ActivationAPIContext,
) -> None:
    context = activation_api
    now = datetime.now(UTC)
    anniversary = await create_activation(
        context.location.id,
        ActivationReason.ANNIVERSARY,
        starts_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        now=now,
        session=context.session,
    )
    on_response = await context.client.post(
        f"/api/v1/locations/{context.location.id}/manual-on",
        headers=context.headers[UserRole.TECHNICIAN],
    )

    response = await context.client.post(
        f"/api/v1/locations/{context.location.id}/manual-off",
        headers=context.headers[UserRole.TECHNICIAN],
    )

    assert on_response.status_code == 201
    assert response.status_code == 200
    assert anniversary.ended_at is None
    assert context.lamp.desired_state is DesiredState.ON
