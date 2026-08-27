from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.service import get_current_user
from backend.app.common.enums import CommandStatus, DeviceStatus
from backend.app.db.session import get_db_session
from backend.app.devices.read_service import (
    get_controller,
    get_gateway,
    get_offline_devices,
    list_commands,
    list_controllers,
    list_gateways,
)
from backend.app.devices.schemas import (
    ControllerRead,
    GatewayDetail,
    GatewayRead,
    OfflineDevices,
    PaginatedCommands,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["devices"],
    dependencies=[Depends(get_current_user)],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/gateways", response_model=list[GatewayRead])
async def gateway_list(
    session: DatabaseSession,
    status: DeviceStatus | None = None,
) -> list[GatewayRead]:
    return await list_gateways(session, status=status)


@router.get("/gateways/{gateway_id}", response_model=GatewayDetail)
async def gateway_detail(
    gateway_id: UUID,
    session: DatabaseSession,
) -> GatewayDetail:
    return await get_gateway(session, gateway_id)


@router.get("/controllers", response_model=list[ControllerRead])
async def controller_list(
    session: DatabaseSession,
    gateway_id: UUID | None = None,
    status: DeviceStatus | None = None,
) -> list[ControllerRead]:
    return await list_controllers(session, gateway_id=gateway_id, status=status)


@router.get("/controllers/{controller_id}", response_model=ControllerRead)
async def controller_detail(
    controller_id: UUID,
    session: DatabaseSession,
) -> ControllerRead:
    return await get_controller(session, controller_id)


@router.get("/devices/offline", response_model=OfflineDevices)
async def offline_devices(session: DatabaseSession) -> OfflineDevices:
    return await get_offline_devices(session)


@router.get("/commands", response_model=PaginatedCommands)
async def command_list(
    session: DatabaseSession,
    status: CommandStatus | None = None,
    location_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginatedCommands:
    return await list_commands(
        session,
        status=status,
        location_id=location_id,
        page=page,
        page_size=page_size,
    )
