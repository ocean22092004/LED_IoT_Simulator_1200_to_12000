import asyncio
import random
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError

from backend.app.common.enums import DesiredState
from backend.app.mqtt.topics import (
    ack_topic,
    command_topic,
    heartbeat_topic,
    presence_topic,
    snapshot_topic,
)
from simulator.memorial_sim.fieldbus import FieldBus
from simulator.memorial_sim.mqtt_client import GatewayMQTTClient, LastWill
from simulator.memorial_sim.schemas import (
    AckMessage,
    CommandMessage,
    ControllerHeartbeat,
    ControllerSnapshotMessage,
    DeviceStatus,
    HeartbeatMessage,
    PresenceMessage,
    SnapshotMessage,
)

MINIMUM_DEDUPE_SIZE = 1_000
DEDUPE_TTL_SECONDS = 24 * 60 * 60


class GatewaySimulator:
    def __init__(
        self,
        *,
        site_code: str,
        gateway_code: str,
        fieldbus: FieldBus,
        mqtt: GatewayMQTTClient,
        heartbeat_seconds: float = 5.0,
        command_latency_ms: int = 0,
        ack_drop_rate: float = 0.0,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        random_source: random.Random | None = None,
    ) -> None:
        if heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        if command_latency_ms < 0:
            raise ValueError("command_latency_ms must not be negative")
        if not 0.0 <= ack_drop_rate <= 1.0:
            raise ValueError("ack_drop_rate must be between 0 and 1")
        self.site_code = site_code
        self.gateway_code = gateway_code
        self.fieldbus = fieldbus
        self.mqtt = mqtt
        self.heartbeat_seconds = heartbeat_seconds
        self.command_latency_ms = command_latency_ms
        self.ack_drop_rate = ack_drop_rate
        self._now = now or (lambda: datetime.now(UTC))
        self._monotonic = monotonic or time.monotonic
        self._random = random_source or random.Random()
        self._started_at = self._monotonic()
        self._dedupe: OrderedDict[UUID, tuple[float, AckMessage]] = OrderedDict()

    def _presence(self, status: DeviceStatus) -> PresenceMessage:
        return PresenceMessage(
            gateway_code=self.gateway_code,
            status=status,
            occurred_at=self._now(),
        )

    async def _publish_presence(self, status: DeviceStatus) -> None:
        await self.mqtt.publish(
            presence_topic(self.site_code, self.gateway_code),
            self._presence(status).model_dump_json(),
            qos=1,
            retain=True,
        )

    async def publish_snapshot(self) -> None:
        controller_snapshots = await self.fieldbus.snapshot()
        message = SnapshotMessage(
            gateway_code=self.gateway_code,
            occurred_at=self._now(),
            controllers=[
                ControllerSnapshotMessage(
                    code=controller.code,
                    status=controller.status,
                    on_channels=list(controller.on_channels),
                    failed_lamp_channels=list(controller.failed_lamp_channels),
                )
                for controller in controller_snapshots
            ],
        )
        await self.mqtt.publish(
            snapshot_topic(self.site_code, self.gateway_code),
            message.model_dump_json(),
            qos=1,
            retain=False,
        )

    async def publish_heartbeat(self) -> None:
        controller_snapshots = await self.fieldbus.snapshot()
        message = HeartbeatMessage(
            gateway_code=self.gateway_code,
            occurred_at=self._now(),
            uptime_s=max(0, int(self._monotonic() - self._started_at)),
            controllers=[
                ControllerHeartbeat(code=controller.code, status=controller.status)
                for controller in controller_snapshots
            ],
        )
        await self.mqtt.publish(
            heartbeat_topic(self.site_code, self.gateway_code),
            message.model_dump_json(),
            qos=1,
            retain=False,
        )

    async def _announce_connected(self) -> None:
        await self.mqtt.subscribe(command_topic(self.site_code, self.gateway_code), qos=1)
        await self._publish_presence("ONLINE")
        await self.publish_snapshot()

    async def start(self) -> None:
        offline = self._presence("OFFLINE")
        await self.mqtt.connect(
            LastWill(
                topic=presence_topic(self.site_code, self.gateway_code),
                payload=offline.model_dump_json(),
                qos=1,
                retain=True,
            )
        )
        await self._announce_connected()

    def _remember(self, ack: AckMessage) -> None:
        observed_at = self._monotonic()
        self._dedupe[ack.command_id] = (observed_at, ack)
        self._dedupe.move_to_end(ack.command_id)
        while len(self._dedupe) > MINIMUM_DEDUPE_SIZE:
            _, (oldest_at, _) = next(iter(self._dedupe.items()))
            if observed_at - oldest_at <= DEDUPE_TTL_SECONDS:
                break
            self._dedupe.popitem(last=False)

    async def _publish_ack(self, ack: AckMessage) -> None:
        if self._random.random() < self.ack_drop_rate:
            return
        await self.mqtt.publish(
            ack_topic(self.site_code, self.gateway_code),
            ack.model_dump_json(),
            qos=1,
            retain=False,
        )

    async def handle_command(self, payload: str | bytes) -> bool:
        try:
            command = CommandMessage.model_validate_json(payload)
        except ValidationError:
            return False
        if command.site_code != self.site_code or command.gateway_code != self.gateway_code:
            return False

        cached = self._dedupe.get(command.command_id)
        if cached is not None:
            self._dedupe.move_to_end(command.command_id)
            await self._publish_ack(cached[1])
            return True

        if self.command_latency_ms:
            await asyncio.sleep(self.command_latency_ms / 1_000)
        result = await self.fieldbus.set_output(
            command.controller_code,
            command.channel,
            command.target_state is DesiredState.ON,
            command.command_id,
        )
        ack = AckMessage(
            command_id=result.command_id,
            occurred_at=self._now(),
            gateway_code=self.gateway_code,
            controller_code=result.controller_code,
            channel=result.channel,
            accepted=result.accepted,
            actual_output_state=result.actual_output_state,
            current_ma=result.current_ma,
            error_code=result.error_code,
            error_message=result.error_message,
        )
        self._remember(ack)
        await self._publish_ack(ack)
        return True

    async def _message_loop(self) -> None:
        expected_topic = command_topic(self.site_code, self.gateway_code)
        async for message in self.mqtt.messages():
            if message.topic == expected_topic:
                await self.handle_command(message.payload)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            try:
                await self.publish_heartbeat()
            except (ConnectionError, OSError, TimeoutError):
                continue

    async def _reconnect_loop(self) -> None:
        while True:
            await self.mqtt.wait_for_reconnect()
            await self._announce_connected()

    async def run(self) -> None:
        await self.start()
        try:
            await asyncio.gather(
                self._message_loop(),
                self._heartbeat_loop(),
                self._reconnect_loop(),
            )
        finally:
            try:
                await self._publish_presence("OFFLINE")
            finally:
                await self.mqtt.disconnect()
