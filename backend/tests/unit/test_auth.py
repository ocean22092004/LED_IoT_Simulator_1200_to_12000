from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import SecretStr

from backend.app.auth.service import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.app.common.enums import UserRole
from backend.app.config import Settings

pytestmark = pytest.mark.unit


def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret=SecretStr("test-only-secret-with-sufficient-length"),
        jwt_expire_minutes=30,
    )


def test_password_hash_uses_argon2_and_verifies_password() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert password_hash.startswith("$argon2id$")
    assert "correct horse battery staple" not in password_hash
    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong", password_hash)


def test_access_token_round_trip_preserves_identity_and_role() -> None:
    user_id = uuid4()
    token = create_access_token(
        user_id=user_id,
        role=UserRole.STAFF,
        settings=auth_settings(),
    )

    claims = decode_access_token(token, auth_settings())

    assert claims.user_id == user_id
    assert claims.role is UserRole.STAFF


def test_expired_access_token_is_rejected() -> None:
    settings = auth_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "role": UserRole.ADMIN.value,
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, settings)
