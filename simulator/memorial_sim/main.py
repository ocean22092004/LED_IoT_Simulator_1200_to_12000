import asyncio
from dataclasses import dataclass
from math import ceil

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from simulator.memorial_sim.controller import ControllerSimulator
from simulator.memorial_sim.fieldbus import SimulatedFieldBus
from simulator.memorial_sim.gateway import GatewaySimulator
from simulator.memorial_sim.mqtt_client import PahoGatewayMQTTClient


class SimulatorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mqtt_host: str = "localhost"
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_username: str = "memorial"
    mqtt_password: SecretStr = SecretStr("change-me")
    simulator_site_code: str = "SITE-001"
    simulator_location_count: int = Field(default=1200, gt=0)
    simulator_locations_per_zone: int = Field(default=300, gt=0)
    simulator_controller_capacity: int = Field(default=64, gt=0)
    simulator_ack_drop_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    simulator_command_latency_ms: int = Field(default=0, ge=0)
    device_heartbeat_seconds: int = Field(default=5, gt=0)


@dataclass(frozen=True)
class GatewayDefinition:
    gateway_code: str
    controllers: tuple[ControllerSimulator, ...]


def _excel_zone_code(index: int) -> str:
    code = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        code = chr(ord("A") + remainder) + code
    return code


def build_gateway_definitions(
    *,
    location_count: int,
    locations_per_zone: int,
    controller_capacity: int,
) -> list[GatewayDefinition]:
    if min(location_count, locations_per_zone, controller_capacity) <= 0:
        raise ValueError("topology values must be positive")
    definitions: list[GatewayDefinition] = []
    zone_count = ceil(location_count / locations_per_zone)
    for zone_index in range(1, zone_count + 1):
        zone_code = _excel_zone_code(zone_index)
        locations_before_zone = (zone_index - 1) * locations_per_zone
        locations_in_zone = min(
            locations_per_zone,
            location_count - locations_before_zone,
        )
        controller_count = ceil(locations_in_zone / controller_capacity)
        controllers = tuple(
            ControllerSimulator(
                code=f"CTRL-{zone_code}-{address:02d}",
                address=address,
                channel_capacity=controller_capacity,
            )
            for address in range(1, controller_count + 1)
        )
        definitions.append(
            GatewayDefinition(
                gateway_code=f"GW-{zone_code}",
                controllers=controllers,
            )
        )
    return definitions


async def run_simulator(settings: SimulatorSettings | None = None) -> None:
    config = settings or SimulatorSettings()
    definitions = build_gateway_definitions(
        location_count=config.simulator_location_count,
        locations_per_zone=config.simulator_locations_per_zone,
        controller_capacity=config.simulator_controller_capacity,
    )
    gateways = [
        GatewaySimulator(
            site_code=config.simulator_site_code,
            gateway_code=definition.gateway_code,
            fieldbus=SimulatedFieldBus(definition.controllers),
            mqtt=PahoGatewayMQTTClient(
                host=config.mqtt_host,
                port=config.mqtt_port,
                username=config.mqtt_username,
                password=config.mqtt_password.get_secret_value(),
                client_id=f"memorial-sim-{definition.gateway_code}",
            ),
            heartbeat_seconds=config.device_heartbeat_seconds,
            command_latency_ms=config.simulator_command_latency_ms,
            ack_drop_rate=config.simulator_ack_drop_rate,
        )
        for definition in definitions
    ]
    await asyncio.gather(*(gateway.run() for gateway in gateways))


def main() -> None:
    asyncio.run(run_simulator())


if __name__ == "__main__":
    main()
