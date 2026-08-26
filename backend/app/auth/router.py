from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.schemas import LoginRequest, TokenResponse, UserResponse
from backend.app.auth.service import (
    authenticate_user,
    create_access_token,
    get_app_settings,
    get_current_user,
)
from backend.app.common.errors import APIError
from backend.app.config import Settings
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> TokenResponse:
    user = await authenticate_user(session, request.username, request.password)
    if user is None:
        raise APIError(401, "AUTH_INVALID_CREDENTIALS", "Invalid username or password")
    return TokenResponse(
        access_token=create_access_token(
            user_id=user.id,
            role=user.role,
            settings=settings,
        )
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user
