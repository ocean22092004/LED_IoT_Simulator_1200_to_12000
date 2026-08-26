import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pytest

from backend.app.common.enums import DesiredState
from simulator.memorial_sim.controller import (
    ControllerSimulator,
    ControllerSnapshot,
    FieldBusResult,
)
from simulator.memorial_sim.gateway import GatewaySimulator
from simulator.memorial_sim.main import build_gateway_definitions
from simulator.memorial_sim.mqtt_client import IncomingMessage, LastWill
from simulator.memorial_sim.schemas import CommandMessage

pytestmark = pytest.mark.unit
COMMAND_ID = UUID("4b27e51e-0d33-4a91-83a4-5d7e176179bb")
NOW = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Published:
    topic: str
    payload: str
    qos: int
    retain: bool


@dataclass
class RecordingMQTTClient:
    connected_will: LastWill | None = None
    subscriptions: list[tuple[str, int]] = field(default_factory=list)
    publications: list[Published] = field(default_factory=list)

    async def connect(self, last_will: LastWill) -> None:
        self.connected_will = last_will

    async def subscribe(self, topic: str, qos: int) -> None:
        self.subscriptions.append((topic, qos))

    async def publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> None:
        self.publications.append(Published(topic, payload, qos, retain))

    async def messages(self):  # type: ignore[no-untyped-def]
        if False:
            yield IncomingMessage("", b"")

    async def disconnect(self) -> None:
        return None


@dataclass
class RecordingFieldBus:
    controller: ControllerSimulator
    calls: list[tuple[str, int, bool, UUID]] = field(default_factory=list)

    async def set_output(
        self,
        controller_code: str,
        channel: int,
        state: bool,
        command_id: UUID,
    ) -> FieldBusResult:
        self.calls.append((controller_code, channel, state, command_id))
        return await self.controller.set_output(channel, state, command_id)

    async def snapshot(self) -> list[ControllerSnapshot]:
        return [self.controller.snapshot()]


def command_payload(
    *,
    controller_code: str = "CTRL-A-04",
    channel: int = 58,
    gateway_code: str = "GW-A",
) -> str:
    return CommandMessage(
        command_id=COMMAND_ID,
        issued_at=NOW,
        site_code="SITE-001",
        gateway_code=gateway_code,
        controller_code=controller_code,
        channel=channel,
        target_state=DesiredState.ON,
        location_code="A250",
        reason="VISIT",
    ).model_dump_json()


@pytest.fixture
def gateway_parts() -> tuple[GatewaySimulator, RecordingFieldBus, RecordingMQTTClient]:
    controller = ControllerSimulator(
        code="CTRL-A-04",
        address=4,
        channel_capacity=64,
    )
    fieldbus = RecordingFieldBus(controller)
    mqtt = RecordingMQTTClient()
    gateway = GatewaySimulator(
        site_code="SITE-001",
        gateway_code="GW-A",
        fieldbus=fieldbus,
        mqtt=mqtt,
        now=lambda: NOW,
        monotonic=lambda: 100.0,
    )
    return gateway, fieldbus, mqtt


async def test_command_routes_to_exact_controller_and_channel(
    gateway_parts: tuple[GatewaySimulator, RecordingFieldBus, RecordingMQTTClient],
) -> None:
    gateway, fieldbus, mqtt = gateway_parts

    assert await gateway.handle_command(command_payload()) is True

    assert fieldbus.calls == [("CTRL-A-04", 58, True, COMMAND_ID)]
    ack = json.loads(mqtt.publications[-1].payload)
    assert mqtt.publications[-1].topic == "memorial/v1/sites/SITE-001/gateways/GW-A/acks"
    assert mqtt.publications[-1].qos == 1
    assert mqtt.publications[-1].retain is False
    assert ack == {
        "schema_version": 1,
        "command_id": str(COMMAND_ID),
        "occurred_at": "2026-08-21T08:00:00Z",
        "gateway_code": "GW-A",
        "controller_code": "CTRL-A-04",
        "channel": 58,
        "accepted": True,
        "actual_output_state": "ON",
        "current_ma": 42.5,
        "error_code": None,
        "error_message": None,
    }


async def test_duplicate_command_is_idempotent_and_republishes_ack(
    gateway_parts: tuple[GatewaySimulator, RecordingFieldBus, RecordingMQTTClient],
) -> None:
    gateway, fieldbus, mqtt = gateway_parts
    payload = command_payload()

    assert await gateway.handle_command(payload) is True
    assert await gateway.handle_command(payload) is True

    assert len(fieldbus.calls) == 1
    assert len(mqtt.publications) == 2
    assert mqtt.publications[0].payload == mqtt.publications[1].payload


async def test_heartbeat_reports_controller_status(
    gateway_parts: tuple[GatewaySimulator, RecordingFieldBus, RecordingMQTTClient],
) -> None:
    gateway, _, mqtt = gateway_parts

    await gateway.publish_heartbeat()

    published = mqtt.publications[-1]
    assert published.topic.endswith("/heartbeat")
    assert published.qos == 1
    assert published.retain is False
    assert json.loads(published.payload) == {
        "schema_version": 1,
        "gateway_code": "GW-A",
        "occurred_at": "2026-08-21T08:00:00Z",
        "uptime_s": 0,
        "controllers": [{"code": "CTRL-A-04", "status": "ONLINE"}],
    }


async def test_start_connects_with_lwt_and_publishes_presence_and_snapshot(
    gateway_parts: tuple[GatewaySimulator, RecordingFieldBus, RecordingMQTTClient],
) -> None:
    gateway, _, mqtt = gateway_parts

    await gateway.start()

    assert mqtt.connected_will is not None
    assert mqtt.connected_will.topic.endswith("/presence")
    assert mqtt.connected_will.qos == 1
    assert mqtt.connected_will.retain is True
    assert json.loads(mqtt.connected_will.payload)["status"] == "OFFLINE"
    assert mqtt.subscriptions == [
        ("memorial/v1/sites/SITE-001/gateways/GW-A/commands", 1)
    ]
    presence, snapshot = mqtt.publications
    assert presence.topic.endswith("/presence")
    assert presence.retain is True
    assert json.loads(presence.payload)["status"] == "ONLINE"
    assert snapshot.topic.endswith("/snapshot")
    assert snapshot.retain is False
    assert json.loads(snapshot.payload)["controllers"] == [
        {
            "code": "CTRL-A-04",
            "status": "ONLINE",
            "on_channels": [],
            "failed_lamp_channels": [],
        }
    ]


async def test_controller_offline_returns_failure_ack(
    gateway_parts: tuple[GatewaySimulator, RecordingFieldBus, RecordingMQTTClient],
) -> None:
    gateway, fieldbus, mqtt = gateway_parts
    fieldbus.controller.online = False

    await gateway.handle_command(command_payload())

    ack = json.loads(mqtt.publications[-1].payload)
    assert ack["accepted"] is False
    assert ack["actual_output_state"] == "UNKNOWN"
    assert ack["error_code"] == "CONTROLLER_OFFLINE"


async def test_command_for_other_gateway_is_ignored(
    gateway_parts: tuple[GatewaySimulator, RecordingFieldBus, RecordingMQTTClient],
) -> None:
    gateway, fieldbus, mqtt = gateway_parts

    assert await gateway.handle_command(command_payload(gateway_code="GW-B")) is False

    assert fieldbus.calls == []
    assert mqtt.publications == []


def test_default_topology_matches_seed_mapping() -> None:
    definitions = build_gateway_definitions(
        location_count=1200,
        locations_per_zone=300,
        controller_capacity=64,
    )

    assert len(definitions) == 4
    assert definitions[0].gateway_code == "GW-A"
    assert [controller.code for controller in definitions[0].controllers] == [
        "CTRL-A-01",
        "CTRL-A-02",
        "CTRL-A-03",
        "CTRL-A-04",
        "CTRL-A-05",
    ]
    assert definitions[-1].gateway_code == "GW-D"
