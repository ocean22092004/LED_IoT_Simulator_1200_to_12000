from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.service import record_audit
from backend.app.auth.service import get_app_settings, require_roles
from backend.app.common.enums import UserRole
from backend.app.common.errors import APIError
from backend.app.config import Settings
from backend.app.db.models.user import User
from backend.app.db.session import get_db_session
from backend.app.simulator.schemas import FaultRequest, SimulatorSettingsRequest
from backend.app.simulator.service import get_simulator_client, proxy_simulator_request


async def require_simulator_admin_enabled(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> None:
    if not settings.simulator_admin_enabled:
        raise APIError(404, "SIMULATOR_ADMIN_DISABLED", "Simulator controls are disabled")


router = APIRouter(
    prefix="/api/v1/simulator",
    tags=["simulator"],
    dependencies=[Depends(require_simulator_admin_enabled)],
)
simulator_user_dependency = require_roles(UserRole.TECHNICIAN, UserRole.ADMIN)
SimulatorUser = Annotated[User, Depends(simulator_user_dependency)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
SimulatorClient = Annotated[httpx.AsyncClient, Depends(get_simulator_client)]


async def _control(
    *,
    client: httpx.AsyncClient,
    session: AsyncSession,
    user: User,
    method: str,
    path: str,
    action: str,
    entity_type: str,
    code: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = await proxy_simulator_request(client, method, path, payload=payload)
    await record_audit(
        session,
        user=user,
        action=action,
        entity_type=entity_type,
        entity_id=None,
        metadata={
            **({"code": code} if code is not None else {}),
            **({"payload": payload} if payload is not None else {}),
        },
    )
    return result


@router.post("/gateways/{code}/offline")
async def gateway_offline(
    code: str,
    client: SimulatorClient,
    session: DatabaseSession,
    user: SimulatorUser,
) -> dict[str, Any]:
    return await _control(
        client=client,
        session=session,
        user=user,
        method="POST",
        path=f"/internal/gateways/{code}/offline",
        action="SIMULATOR_FAULT_SET",
        entity_type="simulator_gateway",
        code=code,
    )


@router.post("/gateways/{code}/online")
async def gateway_online(
    code: str,
    client: SimulatorClient,
    session: DatabaseSession,
    user: SimulatorUser,
) -> dict[str, Any]:
    return await _control(
        client=client,
        session=session,
        user=user,
        method="POST",
        path=f"/internal/gateways/{code}/online",
        action="SIMULATOR_FAULT_CLEARED",
        entity_type="simulator_gateway",
        code=code,
    )


@router.post("/controllers/{code}/offline")
async def controller_offline(
    code: str,
    client: SimulatorClient,
    session: DatabaseSession,
    user: SimulatorUser,
) -> dict[str, Any]:
    return await _control(
        client=client,
        session=session,
        user=user,
        method="POST",
        path=f"/internal/controllers/{code}/offline",
        action="SIMULATOR_FAULT_SET",
        entity_type="simulator_controller",
        code=code,
    )


@router.post("/controllers/{code}/online")
async def controller_online(
    code: str,
    client: SimulatorClient,
    session: DatabaseSession,
    user: SimulatorUser,
) -> dict[str, Any]:
    return await _control(
        client=client,
        session=session,
        user=user,
        method="POST",
        path=f"/internal/controllers/{code}/online",
        action="SIMULATOR_FAULT_CLEARED",
        entity_type="simulator_controller",
        code=code,
    )


@router.post("/locations/{code}/fault")
async def location_fault(
    code: str,
    payload: FaultRequest,
    client: SimulatorClient,
    session: DatabaseSession,
    user: SimulatorUser,
) -> dict[str, Any]:
    return await _control(
        client=client,
        session=session,
        user=user,
        method="POST",
        path=f"/internal/locations/{code}/fault",
        action="SIMULATOR_FAULT_SET",
        entity_type="simulator_location",
        code=code,
        payload=payload.model_dump(),
    )


@router.delete("/locations/{code}/fault")
async def location_fault_clear(
    code: str,
    client: SimulatorClient,
    session: DatabaseSession,
    user: SimulatorUser,
) -> dict[str, Any]:
    return await _control(
        client=client,
        session=session,
        user=user,
        method="DELETE",
        path=f"/internal/locations/{code}/fault",
        action="SIMULATOR_FAULT_CLEARED",
        entity_type="simulator_location",
        code=code,
    )


@router.post("/controllers/{code}/reset")
async def controller_reset(
    code: str,
    client: SimulatorClient,
    session: DatabaseSession,
    user: SimulatorUser,
) -> dict[str, Any]:
    return await _control(
        client=client,
        session=session,
        user=user,
        method="POST",
        path=f"/internal/controllers/{code}/reset",
        action="SIMULATOR_FAULT_SET",
        entity_type="simulator_controller",
        code=code,
    )


@router.post("/settings")
async def simulator_settings(
    payload: SimulatorSettingsRequest,
    client: SimulatorClient,
    session: DatabaseSession,
    user: SimulatorUser,
) -> dict[str, Any]:
    return await _control(
        client=client,
        session=session,
        user=user,
        method="POST",
        path="/internal/settings",
        action="SIMULATOR_FAULT_SET",
        entity_type="simulator_settings",
        payload=payload.model_dump(exclude_none=True),
    )
