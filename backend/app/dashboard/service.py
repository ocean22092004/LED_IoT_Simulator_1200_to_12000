from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from backend.app.common.enums import (
    ActivationReason,
    ActualState,
    DesiredState,
    DeviceStatus,
    LampHealth,
)
from backend.app.dashboard.schemas import (
    ControllerHealth,
    DashboardAnniversariesToday,
    DashboardAnniversaryItem,
    DashboardSummary,
    DeviceHealth,
    GatewayHealth,
)
from backend.app.db.models.activation import Activation
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.models.person import DeceasedPerson
from backend.app.db.models.zone import Zone

BUSINESS_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def _active_activation(now: datetime) -> tuple[ColumnElement[bool], ...]:
    return (
        Activation.starts_at <= now,
        Activation.ended_at.is_(None),
        or_(Activation.expires_at.is_(None), Activation.expires_at > now),
    )


async def get_dashboard_summary(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> DashboardSummary:
    observed_at = now or datetime.now(UTC)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    location_counts = (
        await session.execute(
            select(
                func.count(Location.id),
                func.count(Location.id).filter(LampState.desired_state == DesiredState.ON),
                func.count(Location.id).filter(LampState.actual_state == ActualState.ON),
                func.count(Location.id).filter(
                    LampState.actual_state == ActualState.UNKNOWN
                ),
                func.count(Location.id).filter(
                    LampState.lamp_health == LampHealth.SUSPECTED_FAILED
                ),
            )
            .join(LampState, LampState.location_id == Location.id)
            .where(Location.is_active.is_(True))
        )
    ).one()
    activation_counts = (
        await session.execute(
            select(
                func.count(distinct(Activation.location_id)).filter(
                    Activation.reason == ActivationReason.ANNIVERSARY
                ),
                func.count(distinct(Activation.location_id)).filter(
                    Activation.reason == ActivationReason.VISIT
                ),
            ).where(*_active_activation(observed_at))
        )
    ).one()
    gateway_counts = (
        await session.execute(
            select(
                func.count(Gateway.id).filter(Gateway.status == DeviceStatus.ONLINE),
                func.count(Gateway.id).filter(Gateway.status == DeviceStatus.OFFLINE),
            )
        )
    ).one()
    controller_counts = (
        await session.execute(
            select(
                func.count(Controller.id).filter(
                    Controller.status == DeviceStatus.ONLINE
                ),
                func.count(Controller.id).filter(
                    Controller.status == DeviceStatus.OFFLINE
                ),
            ).where(Controller.is_active.is_(True))
        )
    ).one()
    return DashboardSummary(
        total_locations=int(location_counts[0] or 0),
        desired_on=int(location_counts[1] or 0),
        actual_on=int(location_counts[2] or 0),
        actual_unknown=int(location_counts[3] or 0),
        anniversaries_today=int(activation_counts[0] or 0),
        active_visits=int(activation_counts[1] or 0),
        gateways_online=int(gateway_counts[0] or 0),
        gateways_offline=int(gateway_counts[1] or 0),
        controllers_online=int(controller_counts[0] or 0),
        controllers_offline=int(controller_counts[1] or 0),
        suspected_failed_lamps=int(location_counts[4] or 0),
    )


async def get_anniversaries_today(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> DashboardAnniversariesToday:
    observed_at = now or datetime.now(UTC)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    rows = (
        await session.execute(
            select(Activation, Location, DeceasedPerson, Zone.code)
            .join(Location, Location.id == Activation.location_id)
            .join(Zone, Zone.id == Location.zone_id)
            .outerjoin(DeceasedPerson, DeceasedPerson.id == Location.person_id)
            .where(
                Activation.reason == ActivationReason.ANNIVERSARY,
                Location.is_active.is_(True),
                *_active_activation(observed_at),
            )
            .order_by(Location.code, Activation.id)
        )
    ).all()
    items = [
        DashboardAnniversaryItem(
            activation_id=activation.id,
            location_id=location.id,
            location_code=location.code,
            person_id=person.id if person is not None else None,
            person_name=person.full_name if person is not None else None,
            zone_code=zone_code,
            starts_at=activation.starts_at,
            expires_at=activation.expires_at,
        )
        for activation, location, person, zone_code in rows
    ]
    return DashboardAnniversariesToday(
        local_date=observed_at.astimezone(BUSINESS_TIMEZONE).date(),
        total=len(items),
        items=items,
    )


async def get_device_health(session: AsyncSession) -> DeviceHealth:
    gateway_rows = (
        await session.execute(
            select(
                Gateway,
                func.count(Location.id).filter(Location.is_active.is_(True)),
            )
            .outerjoin(Location, Location.gateway_id == Gateway.id)
            .group_by(Gateway.id)
            .order_by(Gateway.code)
        )
    ).all()
    controller_rows = (
        await session.execute(
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
    ).all()
    return DeviceHealth(
        gateways=[
            GatewayHealth(
                id=gateway.id,
                code=gateway.code,
                name=gateway.name,
                status=gateway.status,
                last_seen_at=gateway.last_seen_at,
                affected_locations=int(affected or 0),
            )
            for gateway, affected in gateway_rows
        ],
        controllers=[
            ControllerHealth(
                id=controller.id,
                gateway_id=controller.gateway_id,
                gateway_code=gateway_code,
                code=controller.code,
                address=controller.address,
                status=controller.status,
                last_seen_at=controller.last_seen_at,
                affected_locations=int(affected or 0),
            )
            for controller, gateway_code, affected in controller_rows
        ],
    )
