import asyncio
from collections.abc import Awaitable, Iterable, Mapping
from dataclasses import dataclass
from math import ceil
from typing import Any, Literal, Self

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from simulator.memorial_sim.controller import ControllerSimulator
from simulator.memorial_sim.gateway import GatewaySimulator
from simulator.memorial_sim.lamp import LampFault


class FaultTargetNotFound(LookupError):
    """Raised when a simulator control target does not exist."""


@dataclass(frozen=True)
class LocationTarget:
    gateway_code: str
    controller_code: str
    channel: int


def _excel_zone_code(index: int) -> str:
    code = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        code = chr(ord("A") + remainder) + code
    return code


def build_location_targets(
    *,
    location_count: int,
    locations_per_zone: int,
    controller_capacity: int,
) -> dict[str, LocationTarget]:
    if min(location_count, locations_per_zone, controller_capacity) <= 0:
        raise ValueError("topology values must be positive")
    targets: dict[str, LocationTarget] = {}
    zone_count = ceil(location_count / locations_per_zone)
    for zone_index in range(1, zone_count + 1):
        zone_code = _excel_zone_code(zone_index)
        locations_before_zone = (zone_index - 1) * locations_per_zone
        locations_in_zone = min(
            locations_per_zone,
            location_count - locations_before_zone,
        )
        for index_in_zone in range(1, locations_in_zone + 1):
            controller_address = (index_in_zone - 1) // controller_capacity + 1
            channel = (index_in_zone - 1) % controller_capacity + 1
            targets[f"{zone_code}{index_in_zone:03d}"] = LocationTarget(
                gateway_code=f"GW-{zone_code}",
                controller_code=f"CTRL-{zone_code}-{controller_address:02d}",
                channel=channel,
            )
    return targets


class FaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fault: Literal["BURNED_OUT", "STUCK_OFF"] = "BURNED_OUT"


class SimulatorSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_latency_ms: int | None = Field(default=None, ge=0)
    ack_drop_rate: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_setting(self) -> Self:
        if self.command_latency_ms is None and self.ack_drop_rate is None:
            raise ValueError("at least one simulator setting is required")
        return self


class SimulatorControlPlane:
    def __init__(
        self,
        *,
        gateways: Iterable[GatewaySimulator],
        controllers: Iterable[ControllerSimulator],
        controller_gateways: Mapping[str, str],
        locations: Mapping[str, LocationTarget],
        reset_offline_seconds: float = 0.1,
    ) -> None:
        self.gateways = {gateway.gateway_code: gateway for gateway in gateways}
        self.controllers = {controller.code: controller for controller in controllers}
        self.controller_gateways = dict(controller_gateways)
        self.locations = dict(locations)
        self.reset_offline_seconds = reset_offline_seconds
        self._lock = asyncio.Lock()
        if reset_offline_seconds < 0:
            raise ValueError("reset_offline_seconds must not be negative")

    def _gateway(self, code: str) -> GatewaySimulator:
        gateway = self.gateways.get(code)
        if gateway is None:
            raise FaultTargetNotFound(f"gateway {code!r} was not found")
        return gateway

    def _controller(self, code: str) -> tuple[ControllerSimulator, GatewaySimulator]:
        controller = self.controllers.get(code)
        gateway_code = self.controller_gateways.get(code)
        if controller is None or gateway_code is None:
            raise FaultTargetNotFound(f"controller {code!r} was not found")
        return controller, self._gateway(gateway_code)

    def _location(
        self,
        code: str,
    ) -> tuple[LocationTarget, ControllerSimulator, GatewaySimulator]:
        target = self.locations.get(code)
        if target is None:
            raise FaultTargetNotFound(f"location {code!r} was not found")
        controller, gateway = self._controller(target.controller_code)
        return target, controller, gateway

    async def set_gateway_online(self, code: str, online: bool) -> dict[str, Any]:
        async with self._lock:
            gateway = self._gateway(code)
            await gateway.set_online(online)
            return {
                "status": "ok",
                "target": {"type": "gateway", "code": code},
                "state": {"online": gateway.is_online},
            }

    async def set_controller_online(self, code: str, online: bool) -> dict[str, Any]:
        async with self._lock:
            controller, gateway = self._controller(code)
            controller.online = online
            if gateway.is_online:
                await gateway.publish_heartbeat()
                await gateway.publish_snapshot()
            return {
                "status": "ok",
                "target": {"type": "controller", "code": code},
                "state": {"online": controller.online},
            }

    async def set_location_fault(
        self,
        code: str,
        fault: LampFault,
    ) -> dict[str, Any]:
        async with self._lock:
            target, controller, gateway = self._location(code)
            channel = controller.channels[target.channel]
            channel.lamp_fault = fault
            if channel.output_on:
                channel.current_ma = 0.0
            if gateway.is_online and controller.online:
                await gateway.publish_channel_telemetry(controller.code, target.channel)
            return {
                "status": "ok",
                "target": {"type": "location", "code": code},
                "state": {"fault": fault.value},
            }

    async def clear_location_fault(self, code: str) -> dict[str, Any]:
        async with self._lock:
            target, controller, gateway = self._location(code)
            channel = controller.channels[target.channel]
            channel.lamp_fault = None
            channel.current_ma = 42.5 if channel.output_on else 0.0
            if gateway.is_online and controller.online:
                await gateway.publish_channel_telemetry(controller.code, target.channel)
            return {
                "status": "ok",
                "target": {"type": "location", "code": code},
                "state": {"fault": None},
            }

    async def reset_controller(self, code: str) -> dict[str, Any]:
        async with self._lock:
            controller, gateway = self._controller(code)
            controller.online = False
            for channel in controller.channels.values():
                channel.output_on = False
                channel.current_ma = 0.0
            if gateway.is_online:
                await gateway.publish_heartbeat()
                await gateway.publish_snapshot()
            try:
                await asyncio.sleep(self.reset_offline_seconds)
            finally:
                controller.online = True
            if gateway.is_online:
                await gateway.publish_heartbeat()
                await gateway.publish_snapshot()
            return {
                "status": "ok",
                "target": {"type": "controller", "code": code},
                "state": {"online": True, "outputs": "OFF"},
            }

    async def update_settings(
        self,
        *,
        command_latency_ms: int | None,
        ack_drop_rate: float | None,
    ) -> dict[str, Any]:
        async with self._lock:
            for gateway in self.gateways.values():
                if command_latency_ms is not None:
                    gateway.command_latency_ms = command_latency_ms
                if ack_drop_rate is not None:
                    gateway.ack_drop_rate = ack_drop_rate
            first_gateway = next(iter(self.gateways.values()), None)
            return {
                "status": "ok",
                "settings": {
                    "command_latency_ms": (
                        first_gateway.command_latency_ms if first_gateway else command_latency_ms
                    ),
                    "ack_drop_rate": (
                        first_gateway.ack_drop_rate if first_gateway else ack_drop_rate
                    ),
                },
            }


def create_control_app(control_plane: SimulatorControlPlane) -> FastAPI:
    app = FastAPI(title="Memorial Simulator Internal Control")

    async def execute(operation: Awaitable[dict[str, Any]]) -> dict[str, Any]:
        try:
            result: dict[str, Any] = await operation
            return result
        except FaultTargetNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/gateways/{code}/offline")
    async def gateway_offline(code: str) -> dict[str, Any]:
        return await execute(control_plane.set_gateway_online(code, False))

    @app.post("/internal/gateways/{code}/online")
    async def gateway_online(code: str) -> dict[str, Any]:
        return await execute(control_plane.set_gateway_online(code, True))

    @app.post("/internal/controllers/{code}/offline")
    async def controller_offline(code: str) -> dict[str, Any]:
        return await execute(control_plane.set_controller_online(code, False))

    @app.post("/internal/controllers/{code}/online")
    async def controller_online(code: str) -> dict[str, Any]:
        return await execute(control_plane.set_controller_online(code, True))

    @app.post("/internal/locations/{code}/fault")
    async def location_fault(code: str, payload: FaultRequest) -> dict[str, Any]:
        return await execute(
            control_plane.set_location_fault(code, LampFault(payload.fault))
        )

    @app.delete("/internal/locations/{code}/fault")
    async def location_fault_clear(code: str) -> dict[str, Any]:
        return await execute(control_plane.clear_location_fault(code))

    @app.post("/internal/controllers/{code}/reset")
    async def controller_reset(code: str) -> dict[str, Any]:
        return await execute(control_plane.reset_controller(code))

    @app.post("/internal/settings")
    async def settings(payload: SimulatorSettingsRequest) -> dict[str, Any]:
        return await control_plane.update_settings(
            command_latency_ms=payload.command_latency_ms,
            ack_drop_rate=payload.ack_drop_rate,
        )

    return app
