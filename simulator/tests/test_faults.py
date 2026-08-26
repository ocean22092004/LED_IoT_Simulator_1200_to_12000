import json
from dataclasses import dataclass, field

import pytest
from httpx import ASGITransport, AsyncClient

from simulator.memorial_sim.controller import ControllerSimulator
from simulator.memorial_sim.faults import (
    LocationTarget,
    SimulatorControlPlane,
    build_location_targets,
    create_control_app,
)
from simulator.memorial_sim.fieldbus import SimulatedFieldBus
from simulator.memorial_sim.gateway import GatewaySimulator
from simulator.memorial_sim.lamp import LampFault
from simulator.memorial_sim.mqtt_client import IncomingMessage, LastWill

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class Published:
    topic: str
    payload: str
    retain: bool


@dataclass
class RecordingMQTTClient:
    connections: int = 0
    disconnections: int = 0
    publications: list[Published] = field(default_factory=list)

    async def connect(self, _last_will: LastWill) -> None:
        self.connections += 1

    async def subscribe(self, topic: str, qos: int) -> None:
        del topic, qos
        return None

    async def publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> None:
        assert qos == 1
        self.publications.append(Published(topic, payload, retain))

    async def messages(self):  # type: ignore[no-untyped-def]
        if False:
            yield IncomingMessage("", b"")

    async def wait_for_reconnect(self) -> None:
        await self.messages().__anext__()

    async def disconnect(self) -> None:
        self.disconnections += 1


@pytest.fixture
def control_parts() -> tuple[
    SimulatorControlPlane,
    GatewaySimulator,
    ControllerSimulator,
    RecordingMQTTClient,
]:
    controller = ControllerSimulator("CTRL-A-04", address=4, channel_capacity=64)
    mqtt = RecordingMQTTClient()
    gateway = GatewaySimulator(
        site_code="SITE-001",
        gateway_code="GW-A",
        fieldbus=SimulatedFieldBus([controller]),
        mqtt=mqtt,
    )
    control = SimulatorControlPlane(
        gateways=[gateway],
        controllers=[controller],
        controller_gateways={controller.code: gateway.gateway_code},
        locations={"A250": LocationTarget("GW-A", "CTRL-A-04", 58)},
        reset_offline_seconds=0,
    )
    return control, gateway, controller, mqtt


def test_location_targets_match_seed_mapping() -> None:
    targets = build_location_targets(
        location_count=1200,
        locations_per_zone=300,
        controller_capacity=64,
    )

    assert targets["A250"] == LocationTarget("GW-A", "CTRL-A-04", 58)
    assert targets["D300"] == LocationTarget("GW-D", "CTRL-D-05", 44)


async def test_gateway_can_disconnect_and_reconnect(
    control_parts: tuple[
        SimulatorControlPlane,
        GatewaySimulator,
        ControllerSimulator,
        RecordingMQTTClient,
    ],
) -> None:
    control, gateway, _, mqtt = control_parts
    await gateway.start()

    offline = await control.set_gateway_online("GW-A", False)
    online = await control.set_gateway_online("GW-A", True)

    assert offline["state"] == {"online": False}
    assert online["state"] == {"online": True}
    assert mqtt.connections == 2
    assert mqtt.disconnections == 1
    presence = [json.loads(item.payload) for item in mqtt.publications if item.retain]
    assert [item["status"] for item in presence] == ["ONLINE", "OFFLINE", "ONLINE"]


async def test_controller_offline_online_and_reset(
    control_parts: tuple[
        SimulatorControlPlane,
        GatewaySimulator,
        ControllerSimulator,
        RecordingMQTTClient,
    ],
) -> None:
    control, gateway, controller, mqtt = control_parts
    await gateway.start()
    controller.channels[58].output_on = True
    controller.channels[58].current_ma = 42.5

    await control.set_controller_online(controller.code, False)
    assert controller.online is False
    await control.set_controller_online(controller.code, True)
    assert controller.online is True
    await control.reset_controller(controller.code)

    assert controller.online is True
    assert all(not channel.output_on for channel in controller.channels.values())
    snapshots = [
        json.loads(item.payload)
        for item in mqtt.publications
        if item.topic.endswith("/snapshot")
    ]
    assert any(snapshot["controllers"][0]["status"] == "OFFLINE" for snapshot in snapshots)
    assert snapshots[-1]["controllers"][0]["status"] == "ONLINE"
    assert snapshots[-1]["controllers"][0]["on_channels"] == []


async def test_burned_lamp_and_settings_are_runtime_configurable(
    control_parts: tuple[
        SimulatorControlPlane,
        GatewaySimulator,
        ControllerSimulator,
        RecordingMQTTClient,
    ],
) -> None:
    control, gateway, controller, mqtt = control_parts
    await gateway.start()
    channel = controller.channels[58]
    channel.output_on = True
    channel.current_ma = 42.5

    result = await control.set_location_fault("A250", LampFault.BURNED_OUT)

    assert result["state"] == {"fault": "BURNED_OUT"}
    assert channel.output_on is True
    assert channel.current_ma == 0.0
    assert json.loads(mqtt.publications[-1].payload)["channels"] == [
        {"channel": 58, "output_state": "ON", "current_ma": 0.0}
    ]

    await control.clear_location_fault("A250")
    settings = await control.update_settings(command_latency_ms=1000, ack_drop_rate=0.5)

    assert channel.lamp_fault is None
    assert channel.current_ma == 42.5
    assert gateway.command_latency_ms == 1000
    assert gateway.ack_drop_rate == 0.5
    assert settings["settings"] == {"command_latency_ms": 1000, "ack_drop_rate": 0.5}


async def test_private_http_control_endpoints(
    control_parts: tuple[
        SimulatorControlPlane,
        GatewaySimulator,
        ControllerSimulator,
        RecordingMQTTClient,
    ],
) -> None:
    control, gateway, _, _ = control_parts
    await gateway.start()
    app = create_control_app(control)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://simulator",
    ) as client:
        response = await client.post(
            "/internal/locations/A250/fault",
            json={"fault": "BURNED_OUT"},
        )
        missing = await client.post("/internal/gateways/GW-Z/offline")
        invalid = await client.post(
            "/internal/settings",
            json={"ack_drop_rate": 1.1},
        )

    assert response.status_code == 200
    assert response.json()["state"] == {"fault": "BURNED_OUT"}
    assert missing.status_code == 404
    assert invalid.status_code == 422
