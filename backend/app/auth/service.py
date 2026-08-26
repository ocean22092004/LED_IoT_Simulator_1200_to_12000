import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import UserRole
from backend.app.common.errors import APIError
from backend.app.config import Settings
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session

JWT_ALGORITHM = "HS256"
password_hasher = PasswordHasher()
bearer_scheme = HTTPBearer(auto_error=False)


class InvalidTokenError(ValueError):
    """Raised when a bearer token is invalid or expired."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    role: UserRole


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def create_access_token(
    *,
    user_id: UUID,
    role: UserRole,
    settings: Settings,
) -> str:
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {
            "sub": str(user_id),
            "role": role.value,
            "iat": issued_at,
            "exp": expires_at,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "role", "iat", "exp"]},
        )
        return AccessTokenClaims(
            user_id=UUID(payload["sub"]),
            role=UserRole(payload["role"]),
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        raise InvalidTokenError("invalid access token") from error


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def authenticate_user(
    session: AsyncSession,
    username: str,
    password: str,
) -> User | None:
    user = await session.scalar(
        select(User).where(User.username == username.strip().lower())
    )
    if user is None or not user.is_active:
        return None
    if not await asyncio.to_thread(verify_password, password, user.password_hash):
        return None
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = await asyncio.to_thread(hash_password, password)
    return user


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> User:
    if credentials is None:
        raise APIError(401, "AUTH_REQUIRED", "Bearer authentication is required")
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError as error:
        raise APIError(401, "AUTH_INVALID_TOKEN", "Invalid or expired access token") from error

    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active or user.role != claims.role:
        raise APIError(401, "AUTH_INVALID_TOKEN", "Invalid or expired access token")
    return user


RoleDependency = Callable[..., Coroutine[Any, Any, User]]


def require_roles(*allowed_roles: UserRole) -> RoleDependency:
    allowed = frozenset(allowed_roles)

    async def authorize(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed:
            raise APIError(
                403,
                "AUTH_FORBIDDEN",
                "You do not have permission to perform this action",
            )
        return current_user

    return authorize
