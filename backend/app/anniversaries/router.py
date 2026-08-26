from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.anniversaries.schemas import (
    AnniversariesTodayResponse,
    AnniversaryRuleResponse,
    AnniversaryRuleUpsert,
)
from backend.app.anniversaries.service import (
    BUSINESS_TIMEZONE,
    anniversaries_for_local_date,
    delete_anniversary_rule,
    put_anniversary_rule,
)
from backend.app.auth.service import get_current_user, require_roles
from backend.app.common.enums import UserRole
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session

router = APIRouter(prefix="/api/v1", tags=["anniversaries"])
admin_dependency = require_roles(UserRole.ADMIN)
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(admin_dependency)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.put(
    "/locations/{location_id}/anniversary",
    response_model=AnniversaryRuleResponse,
)
async def anniversary_put(
    location_id: UUID,
    payload: AnniversaryRuleUpsert,
    session: DatabaseSession,
    user: AdminUser,
) -> AnniversaryRuleResponse:
    return await put_anniversary_rule(session, location_id, payload, user)


@router.delete(
    "/locations/{location_id}/anniversary",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def anniversary_delete(
    location_id: UUID,
    session: DatabaseSession,
    user: AdminUser,
) -> Response:
    await delete_anniversary_rule(session, location_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/anniversaries/today", response_model=AnniversariesTodayResponse)
async def anniversaries_today(
    session: DatabaseSession,
    _user: AuthenticatedUser,
) -> AnniversariesTodayResponse:
    local_date = datetime.now(BUSINESS_TIMEZONE).date()
    return await anniversaries_for_local_date(session, local_date)
