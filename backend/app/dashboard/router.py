from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.service import get_current_user
from backend.app.dashboard.schemas import (
    DashboardAnniversariesToday,
    DashboardSummary,
    DeviceHealth,
)
from backend.app.dashboard.service import (
    get_anniversaries_today,
    get_dashboard_summary,
    get_device_health,
)
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    session: DatabaseSession,
    _user: AuthenticatedUser,
) -> DashboardSummary:
    return await get_dashboard_summary(session)


@router.get(
    "/anniversaries-today",
    response_model=DashboardAnniversariesToday,
)
async def dashboard_anniversaries_today(
    session: DatabaseSession,
    _user: AuthenticatedUser,
) -> DashboardAnniversariesToday:
    return await get_anniversaries_today(session)


@router.get("/device-health", response_model=DeviceHealth)
async def dashboard_device_health(
    session: DatabaseSession,
    _user: AuthenticatedUser,
) -> DeviceHealth:
    return await get_device_health(session)
