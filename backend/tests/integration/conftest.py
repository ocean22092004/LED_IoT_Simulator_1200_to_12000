from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.config import get_settings
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.location import Location
from backend.app.db.models.site import Site
from backend.app.db.models.zone import Zone


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as database_session:
            yield database_session
            await database_session.rollback()
    finally:
        await engine.dispose()


@dataclass
class MappedTopology:
    session: AsyncSession
    site: Site
    zone: Zone
    gateway: Gateway
    controller: Controller

    async def create_location(self, code: str, channel: int) -> Location:
        location = Location(
            site_id=self.site.id,
            zone_id=self.zone.id,
            code=code,
            gateway_id=self.gateway.id,
            controller_id=self.controller.id,
            channel_number=channel,
        )
        self.session.add(location)
        await self.session.flush()
        return location


@pytest_asyncio.fixture
async def mapped_topology(session: AsyncSession) -> MappedTopology:
    site = Site(code="SITE-TEST", name="Test Site", timezone="Asia/Ho_Chi_Minh")
    session.add(site)
    await session.flush()

    zone = Zone(site_id=site.id, code="A", name="Khu A")
    session.add(zone)
    await session.flush()

    gateway = Gateway(site_id=site.id, zone_id=zone.id, code="GW-A", name="Gateway A")
    session.add(gateway)
    await session.flush()

    controller = Controller(
        gateway_id=gateway.id,
        code="CTRL-A-01",
        address=1,
        channel_capacity=64,
    )
    session.add(controller)
    await session.flush()

    return MappedTopology(
        session=session,
        site=site,
        zone=zone,
        gateway=gateway,
        controller=controller,
    )
