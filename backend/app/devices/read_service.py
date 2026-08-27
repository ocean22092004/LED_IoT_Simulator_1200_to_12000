from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import CommandStatus, DeviceStatus
from backend.app.common.errors import APIError
from backend.app.db.models.command import LightCommand
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.location import Location
from backend.app.devices.schemas import (
    CommandRead,
    ControllerRead,
    GatewayDetail,
    GatewayRead,
    OfflineDevices,
    PaginatedCommands,
)


def _gateway_read(gateway: Gateway, affected: int | None) -> GatewayRead:
    return GatewayRead(
        id=gateway.id,
        site_id=gateway.site_id,
        zone_id=gateway.zone_id,
        code=gateway.code,
        name=gateway.name,
        status=gateway.status,
        last_seen_at=gateway.last_seen_at,
        firmware_version=gateway.firmware_version,
        is_simulated=gateway.is_simulated,
        affected_locations=int(affected or 0),
    )


def _controller_read(
    controller: Controller,
    gateway_code: str,
    affected: int | None,
) -> ControllerRead:
    return ControllerRead(
        id=controller.id,
        gateway_id=controller.gateway_id,
        gateway_code=gateway_code,
        code=controller.code,
        address=controller.address,
        channel_capacity=controller.channel_capacity,
        status=controller.status,
        last_seen_at=controller.last_seen_at,
        is_active=controller.is_active,
        affected_locations=int(affected or 0),
    )


async def list_gateways(
    session: AsyncSession,
    *,
    status: DeviceStatus | None = None,
) -> list[GatewayRead]:
    statement = (
        select(
            Gateway,
            func.count(Location.id).filter(Location.is_active.is_(True)),
        )
        .outerjoin(Location, Location.gateway_id == Gateway.id)
        .group_by(Gateway.id)
        .order_by(Gateway.code)
    )
    if status is not None:
        statement = statement.where(Gateway.status == status)
    rows = (await session.execute(statement)).all()
    return [_gateway_read(gateway, affected) for gateway, affected in rows]


async def list_controllers(
    session: AsyncSession,
    *,
    gateway_id: UUID | None = None,
    status: DeviceStatus | None = None,
) -> list[ControllerRead]:
    statement = (
        select(
            Controller,
            Gateway.code,
            func.count(Location.id).filter(Location.is_active.is_(True)),
        )
        .join(Gateway, Gateway.id == Controller.gateway_id)
        .outerjoin(Location, Location.controller_id == Controller.id)
        .where(Controller.is_active.is_(True))
        .group_by(Controller.id, Gateway.code)
        .order_by(Gateway.code, Controller.address)
    )
    if gateway_id is not None:
        statement = statement.where(Controller.gateway_id == gateway_id)
    if status is not None:
        statement = statement.where(Controller.status == status)
    rows = (await session.execute(statement)).all()
    return [
        _controller_read(controller, gateway_code, affected)
        for controller, gateway_code, affected in rows
    ]


async def get_gateway(session: AsyncSession, gateway_id: UUID) -> GatewayDetail:
    statement = (
        select(
            Gateway,
            func.count(Location.id).filter(Location.is_active.is_(True)),
        )
        .outerjoin(Location, Location.gateway_id == Gateway.id)
        .where(Gateway.id == gateway_id)
        .group_by(Gateway.id)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise APIError(404, "GATEWAY_NOT_FOUND", f"Gateway {gateway_id} was not found")
    gateway, affected = row
    return GatewayDetail(
        **_gateway_read(gateway, affected).model_dump(),
        controllers=await list_controllers(session, gateway_id=gateway_id),
    )


async def get_controller(session: AsyncSession, controller_id: UUID) -> ControllerRead:
    statement = (
        select(
            Controller,
            Gateway.code,
            func.count(Location.id).filter(Location.is_active.is_(True)),
        )
        .join(Gateway, Gateway.id == Controller.gateway_id)
        .outerjoin(Location, Location.controller_id == Controller.id)
        .where(Controller.id == controller_id)
        .group_by(Controller.id, Gateway.code)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise APIError(
            404,
            "CONTROLLER_NOT_FOUND",
            f"Controller {controller_id} was not found",
        )
    return _controller_read(*row)


async def get_offline_devices(session: AsyncSession) -> OfflineDevices:
    return OfflineDevices(
        gateways=await list_gateways(session, status=DeviceStatus.OFFLINE),
        controllers=await list_controllers(session, status=DeviceStatus.OFFLINE),
    )


async def list_commands(
    session: AsyncSession,
    *,
    status: CommandStatus | None,
    location_id: UUID | None,
    page: int,
    page_size: int,
) -> PaginatedCommands:
    filters = []
    if status is not None:
        filters.append(LightCommand.status == status)
    if location_id is not None:
        filters.append(LightCommand.location_id == location_id)
    statement = (
        select(LightCommand, Location.code, Gateway.code, Controller.code)
        .join(Location, Location.id == LightCommand.location_id)
        .join(Gateway, Gateway.id == LightCommand.gateway_id)
        .join(Controller, Controller.id == LightCommand.controller_id)
        .where(*filters)
        .order_by(LightCommand.created_at.desc(), LightCommand.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count_statement = select(func.count(LightCommand.id)).where(*filters)
    rows = (await session.execute(statement)).all()
    total = await session.scalar(count_statement)
    return PaginatedCommands(
        items=[
            CommandRead(
                id=command.id,
                location_id=command.location_id,
                location_code=location_code,
                gateway_id=command.gateway_id,
                gateway_code=gateway_code,
                controller_id=command.controller_id,
                controller_code=controller_code,
                channel_number=command.channel_number,
                target_state=command.target_state,
                status=command.status,
                reason=command.reason,
                attempt_count=command.attempt_count,
                next_attempt_at=command.next_attempt_at,
                sent_at=command.sent_at,
                acked_at=command.acked_at,
                last_error=command.last_error,
                created_at=command.created_at,
            )
            for command, location_code, gateway_code, controller_code in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total or 0),
    )
