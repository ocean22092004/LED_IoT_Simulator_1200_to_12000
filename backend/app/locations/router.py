from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.service import get_current_user, require_roles
from backend.app.common.enums import UserRole
from backend.app.common.errors import APIError
from backend.app.db.models.user import User
from backend.app.db.models.zone import Zone
from backend.app.db.session import get_db_session
from backend.app.locations.schemas import (
    LocationCreate,
    LocationDetail,
    LocationUpdate,
    PaginatedLocations,
    PersonCreate,
    PersonResponse,
    PersonUpdate,
    ZoneResponse,
)
from backend.app.locations.service import (
    create_location,
    create_person,
    get_location,
    search_locations,
    update_location,
    update_person,
)

router = APIRouter(prefix="/api/v1/locations", tags=["locations"])
zone_router = APIRouter(prefix="/api/v1/zones", tags=["locations"])
person_router = APIRouter(prefix="/api/v1/people", tags=["people"])

authenticated_dependency = get_current_user
admin_dependency = require_roles(UserRole.ADMIN)
AuthenticatedUser = Annotated[User, Depends(authenticated_dependency)]
AdminUser = Annotated[User, Depends(admin_dependency)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=PaginatedLocations)
async def list_locations(
    session: DatabaseSession,
    _user: AuthenticatedUser,
    search: str | None = None,
    site_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginatedLocations:
    return await search_locations(
        session,
        search=search,
        site_id=site_id,
        zone_id=None,
        page=page,
        page_size=page_size,
    )


@router.get("/{location_id}", response_model=LocationDetail)
async def location_detail(
    location_id: UUID,
    session: DatabaseSession,
    _user: AuthenticatedUser,
) -> LocationDetail:
    return await get_location(session, location_id)


@router.post("", response_model=LocationDetail, status_code=status.HTTP_201_CREATED)
async def location_create(
    payload: LocationCreate,
    session: DatabaseSession,
    user: AdminUser,
) -> LocationDetail:
    return await create_location(session, payload, user)


@router.patch("/{location_id}", response_model=LocationDetail)
async def location_update(
    location_id: UUID,
    payload: LocationUpdate,
    session: DatabaseSession,
    user: AdminUser,
) -> LocationDetail:
    return await update_location(session, location_id, payload, user)


@zone_router.get("", response_model=list[ZoneResponse])
async def list_zones(
    session: DatabaseSession,
    _user: AuthenticatedUser,
    site_id: UUID | None = None,
) -> list[Zone]:
    statement = select(Zone).order_by(Zone.sort_order, Zone.code)
    if site_id is not None:
        statement = statement.where(Zone.site_id == site_id)
    return list(await session.scalars(statement))


@zone_router.get("/{zone_id}/locations", response_model=PaginatedLocations)
async def list_zone_locations(
    zone_id: UUID,
    session: DatabaseSession,
    _user: AuthenticatedUser,
    search: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginatedLocations:
    if await session.get(Zone, zone_id) is None:
        raise APIError(404, "ZONE_NOT_FOUND", f"Zone {zone_id} was not found")
    return await search_locations(
        session,
        search=search,
        site_id=None,
        zone_id=zone_id,
        page=page,
        page_size=page_size,
    )


@person_router.post("", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
async def person_create(
    payload: PersonCreate,
    session: DatabaseSession,
    _user: AdminUser,
) -> PersonResponse:
    return await create_person(session, payload)


@person_router.patch("/{person_id}", response_model=PersonResponse)
async def person_update(
    person_id: UUID,
    payload: PersonUpdate,
    session: DatabaseSession,
    _user: AdminUser,
) -> PersonResponse:
    return await update_person(session, person_id, payload)
