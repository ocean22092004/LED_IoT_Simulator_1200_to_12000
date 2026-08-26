from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.service import create_access_token, hash_password
from backend.app.common.enums import (
    ActivationReason,
    ActualState,
    DesiredState,
    LampHealth,
    UserRole,
)
from backend.app.config import Settings
from backend.app.db.models.activation import Activation
from backend.app.db.models.audit_log import AuditLog
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.models.person import DeceasedPerson
from backend.app.db.models.site import Site
from backend.app.db.models.user import User
from backend.app.db.models.zone import Zone
from backend.app.db.session import get_db_session
from backend.app.main import create_app

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class LocationAPIContext:
    client: AsyncClient
    session: AsyncSession
    site: Site
    zone: Zone
    gateway: Gateway
    controller: Controller
    location: Location
    person: DeceasedPerson
    admin: User
    headers: dict[str, str]


async def ready() -> bool:
    return True


@pytest_asyncio.fixture
async def location_api(session: AsyncSession) -> AsyncIterator[LocationAPIContext]:
    suffix = uuid4().hex[:10]
    site = Site(code=f"SITE-API-{suffix}", name="API Test Site")
    session.add(site)
    await session.flush()

    zone = Zone(site_id=site.id, code="A", name="Khu A", sort_order=1)
    session.add(zone)
    await session.flush()

    gateway = Gateway(
        site_id=site.id,
        zone_id=zone.id,
        code="GW-A",
        name="Gateway A",
    )
    session.add(gateway)
    await session.flush()

    controller = Controller(
        gateway_id=gateway.id,
        code="CTRL-A-01",
        address=1,
        channel_capacity=4,
    )
    person = DeceasedPerson(
        site_id=site.id,
        full_name="Người Đã Khuất Trần Văn Case",
    )
    session.add_all([controller, person])
    await session.flush()

    location = Location(
        site_id=site.id,
        zone_id=zone.id,
        code="A250",
        person_id=person.id,
        gateway_id=gateway.id,
        controller_id=controller.id,
        channel_number=1,
    )
    second_location = Location(
        site_id=site.id,
        zone_id=zone.id,
        code="B001",
        gateway_id=gateway.id,
        controller_id=controller.id,
        channel_number=2,
    )
    session.add_all([location, second_location])
    await session.flush()

    session.add_all(
        [
            LampState(
                location_id=location.id,
                desired_state=DesiredState.ON,
                actual_state=ActualState.OFF,
                lamp_health=LampHealth.OK,
                current_ma=Decimal("42.50"),
            ),
            LampState(location_id=second_location.id),
            Activation(
                location_id=location.id,
                reason=ActivationReason.VISIT,
                starts_at=datetime.now(UTC) - timedelta(minutes=5),
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
            ),
        ]
    )

    admin = User(
        username=f"locations-admin-{suffix}",
        password_hash=hash_password("test-password"),
        role=UserRole.ADMIN,
    )
    session.add(admin)
    await session.flush()

    settings = Settings(
        _env_file=None,
        jwt_secret=SecretStr("location-api-test-secret-long-enough"),
    )
    token = create_access_token(user_id=admin.id, role=admin.role, settings=settings)
    app = create_app(settings=settings, readiness_probe=ready)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield LocationAPIContext(
            client=client,
            session=session,
            site=site,
            zone=zone,
            gateway=gateway,
            controller=controller,
            location=location,
            person=person,
            admin=admin,
            headers={"Authorization": f"Bearer {token}"},
        )


async def test_exact_code_search_is_first_and_site_scoped(
    location_api: LocationAPIContext,
) -> None:
    response = await location_api.client.get(
        "/api/v1/locations",
        params={"search": "A250", "site_id": str(location_api.site.id)},
        headers=location_api.headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["code"] == "A250"


@pytest.mark.parametrize("search", ["a250", "trần văn case", "TRẦN VĂN CASE"])
async def test_search_is_case_insensitive(
    location_api: LocationAPIContext,
    search: str,
) -> None:
    response = await location_api.client.get(
        "/api/v1/locations",
        params={"search": search, "site_id": str(location_api.site.id)},
        headers=location_api.headers,
    )

    assert response.status_code == 200
    assert [item["code"] for item in response.json()["items"]] == ["A250"]


async def test_location_detail_keeps_desired_and_actual_state_separate(
    location_api: LocationAPIContext,
) -> None:
    response = await location_api.client.get(
        f"/api/v1/locations/{location_api.location.id}",
        headers=location_api.headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["zone"] == {"code": "A", "name": "Khu A"}
    assert body["person"]["full_name"] == "Người Đã Khuất Trần Văn Case"
    assert body["hardware"] == {
        "gateway_code": "GW-A",
        "controller_code": "CTRL-A-01",
        "channel": 1,
    }
    assert body["light"]["desired_state"] == "ON"
    assert body["light"]["actual_state"] == "OFF"
    assert body["light"]["active_reasons"] == ["VISIT"]


async def test_location_search_is_paginated(location_api: LocationAPIContext) -> None:
    response = await location_api.client.get(
        "/api/v1/locations",
        params={"site_id": str(location_api.site.id), "page": 2, "page_size": 1},
        headers=location_api.headers,
    )

    assert response.status_code == 200
    assert response.json()["page"] == 2
    assert response.json()["page_size"] == 1
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1


async def test_location_create_rejects_channel_above_controller_capacity(
    location_api: LocationAPIContext,
) -> None:
    response = await location_api.client.post(
        "/api/v1/locations",
        json={
            "site_id": str(location_api.site.id),
            "zone_id": str(location_api.zone.id),
            "code": "A999",
            "gateway_id": str(location_api.gateway.id),
            "controller_id": str(location_api.controller.id),
            "channel_number": 5,
        },
        headers=location_api.headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LOCATION_MAPPING_INVALID"


async def test_location_create_rejects_mismatched_zone_and_occupied_channel(
    location_api: LocationAPIContext,
) -> None:
    other_zone = Zone(
        site_id=location_api.site.id,
        code="OTHER",
        name="Khu khác",
        sort_order=2,
    )
    location_api.session.add(other_zone)
    await location_api.session.flush()

    base_payload = {
        "site_id": str(location_api.site.id),
        "code": "A997",
        "gateway_id": str(location_api.gateway.id),
        "controller_id": str(location_api.controller.id),
    }
    response = await location_api.client.post(
        "/api/v1/locations",
        json={
            **base_payload,
            "zone_id": str(other_zone.id),
            "channel_number": 3,
        },
        headers=location_api.headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LOCATION_MAPPING_INVALID"

    response = await location_api.client.post(
        "/api/v1/locations",
        json={
            **base_payload,
            "zone_id": str(location_api.zone.id),
            "channel_number": 1,
        },
        headers=location_api.headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["channel_number"] == 1


async def test_location_create_and_patch_create_lamp_state_and_audit_mapping(
    location_api: LocationAPIContext,
) -> None:
    response = await location_api.client.post(
        "/api/v1/locations",
        json={
            "site_id": str(location_api.site.id),
            "zone_id": str(location_api.zone.id),
            "code": "A999",
            "gateway_id": str(location_api.gateway.id),
            "controller_id": str(location_api.controller.id),
            "channel_number": 3,
        },
        headers=location_api.headers,
    )
    assert response.status_code == 201
    location_id = UUID(response.json()["id"])
    assert await location_api.session.get(LampState, location_id) is not None

    response = await location_api.client.patch(
        f"/api/v1/locations/{location_id}",
        json={"code": "A998", "channel_number": 4},
        headers=location_api.headers,
    )
    assert response.status_code == 200
    assert response.json()["code"] == "A998"
    assert response.json()["hardware"]["channel"] == 4

    audit_actions = list(
        await location_api.session.scalars(
            select(AuditLog.action)
            .where(AuditLog.entity_id == location_id)
            .order_by(AuditLog.id)
        )
    )
    assert audit_actions == ["LOCATION_MAPPING_CHANGED", "LOCATION_MAPPING_CHANGED"]


async def test_person_create_and_patch(location_api: LocationAPIContext) -> None:
    response = await location_api.client.post(
        "/api/v1/people",
        json={
            "site_id": str(location_api.site.id),
            "full_name": "Người đã khuất Test",
            "notes": "Ghi chú ban đầu",
        },
        headers=location_api.headers,
    )
    assert response.status_code == 201
    person_id = response.json()["id"]

    response = await location_api.client.patch(
        f"/api/v1/people/{person_id}",
        json={"full_name": "Người đã khuất Đã Cập Nhật", "notes": None},
        headers=location_api.headers,
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Người đã khuất Đã Cập Nhật"
    assert response.json()["notes"] is None


async def test_zones_and_zone_locations_are_available(
    location_api: LocationAPIContext,
) -> None:
    response = await location_api.client.get(
        "/api/v1/zones",
        params={"site_id": str(location_api.site.id)},
        headers=location_api.headers,
    )
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(location_api.zone.id),
            "site_id": str(location_api.site.id),
            "code": "A",
            "name": "Khu A",
            "sort_order": 1,
            "is_active": True,
        }
    ]

    response = await location_api.client.get(
        f"/api/v1/zones/{location_api.zone.id}/locations",
        params={"page_size": 1},
        headers=location_api.headers,
    )
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1


async def test_request_validation_uses_api_error_envelope(
    location_api: LocationAPIContext,
) -> None:
    response = await location_api.client.get(
        "/api/v1/locations",
        params={"page_size": 201},
        headers=location_api.headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
