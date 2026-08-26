from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.activations.schemas import ActivationResponse, VisitStartRequest
from backend.app.activations.service import (
    end_manual_on,
    end_visit,
    start_manual_on,
    start_visit,
)
from backend.app.auth.service import require_roles
from backend.app.common.enums import UserRole
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session

router = APIRouter(prefix="/api/v1", tags=["activations"])
visit_dependency = require_roles(UserRole.STAFF, UserRole.ADMIN)
technician_dependency = require_roles(UserRole.TECHNICIAN, UserRole.ADMIN)
VisitUser = Annotated[User, Depends(visit_dependency)]
TechnicianUser = Annotated[User, Depends(technician_dependency)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
IdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=1, max_length=128),
]


@router.post(
    "/locations/{location_id}/visits",
    response_model=ActivationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_visit(
    location_id: UUID,
    payload: VisitStartRequest,
    response: Response,
    session: DatabaseSession,
    user: VisitUser,
    idempotency_key: IdempotencyKey = None,
) -> ActivationResponse:
    activation, created = await start_visit(
        session,
        location_id=location_id,
        duration_minutes=payload.duration_minutes,
        actor=user,
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return ActivationResponse.model_validate(activation)


@router.post(
    "/activations/{activation_id}/end",
    response_model=ActivationResponse,
)
async def visit_end(
    activation_id: UUID,
    session: DatabaseSession,
    user: VisitUser,
) -> ActivationResponse:
    activation, _ = await end_visit(
        session,
        activation_id=activation_id,
        actor=user,
    )
    return ActivationResponse.model_validate(activation)


@router.post(
    "/locations/{location_id}/manual-on",
    response_model=ActivationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def manual_on(
    location_id: UUID,
    response: Response,
    session: DatabaseSession,
    user: TechnicianUser,
) -> ActivationResponse:
    activation, created = await start_manual_on(
        session,
        location_id=location_id,
        actor=user,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return ActivationResponse.model_validate(activation)


@router.post(
    "/locations/{location_id}/manual-off",
    response_model=ActivationResponse,
)
async def manual_off(
    location_id: UUID,
    session: DatabaseSession,
    user: TechnicianUser,
) -> ActivationResponse:
    activation = await end_manual_on(
        session,
        location_id=location_id,
        actor=user,
    )
    return ActivationResponse.model_validate(activation)
