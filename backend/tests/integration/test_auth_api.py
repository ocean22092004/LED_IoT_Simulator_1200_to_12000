from collections.abc import AsyncIterator
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.seed import seed_default_users
from backend.app.auth.service import hash_password, require_roles, verify_password
from backend.app.common.enums import UserRole
from backend.app.config import Settings
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session
from backend.app.main import create_app

pytestmark = pytest.mark.integration
technician_dependency = require_roles(UserRole.TECHNICIAN)
TechnicianUser = Annotated[User, Depends(technician_dependency)]


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret=SecretStr("integration-test-jwt-secret-long-enough"),
        jwt_expire_minutes=30,
    )


@pytest.fixture
async def auth_client(
    session: AsyncSession,
    auth_settings: Settings,
) -> AsyncIterator[AsyncClient]:
    session.add(
        User(
            username="staff-api-test",
            password_hash=hash_password("staff-password"),
            role=UserRole.STAFF,
        )
    )
    await session.flush()

    app = create_app(settings=auth_settings, readiness_probe=lambda: ready())

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session

    @app.get("/test/technician")
    async def technician_only(
        _user: TechnicianUser,
    ) -> dict[str, str]:
        return {"status": "allowed"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def ready() -> bool:
    return True


async def login(auth_client: AsyncClient) -> str:
    response = await auth_client.post(
        "/api/v1/auth/login",
        json={"username": "staff-api-test", "password": "staff-password"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    return str(body["access_token"])


async def test_login_success_and_me(auth_client: AsyncClient) -> None:
    token = await login(auth_client)

    response = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "staff-api-test"
    assert response.json()["role"] == "STAFF"


async def test_login_failure_uses_api_error_envelope(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/auth/login",
        json={"username": "staff-api-test", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "AUTH_INVALID_CREDENTIALS",
            "message": "Invalid username or password",
            "details": {},
        }
    }


async def test_staff_cannot_call_technician_route(auth_client: AsyncClient) -> None:
    token = await login(auth_client)

    response = await auth_client.get(
        "/test/technician",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_FORBIDDEN"


async def test_me_rejects_missing_bearer_token(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_default_user_seed_uses_configured_passwords_and_is_idempotent(
    session: AsyncSession,
) -> None:
    settings = Settings(
        _env_file=None,
        admin_password=SecretStr("admin-from-env"),
        staff_password=SecretStr("staff-from-env"),
        tech_password=SecretStr("tech-from-env"),
    )

    assert await seed_default_users(session, settings) == 3
    assert await seed_default_users(session, settings) == 3

    users = {
        user.username: user
        for user in (
            await session.scalars(
                select(User).where(User.username.in_(["admin", "staff", "tech"]))
            )
        )
    }
    assert users["admin"].role is UserRole.ADMIN
    assert users["staff"].role is UserRole.STAFF
    assert users["tech"].role is UserRole.TECHNICIAN
    assert verify_password("admin-from-env", users["admin"].password_hash)
    assert verify_password("staff-from-env", users["staff"].password_hash)
    assert verify_password("tech-from-env", users["tech"].password_hash)
