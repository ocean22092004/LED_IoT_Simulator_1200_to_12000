import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.common.enums import (
    ActualState,
    CommandStatus,
    ControllerOutputState,
    DeviceStatus,
    LampHealth,
)
from backend.app.db.models.command import LightCommand
from backend.app.db.models.device import Controller, Gateway
from backend.app.db.models.device_event import DeviceEvent
from backend.app.db.models.lamp_state import LampState
from backend.app.db.models.location import Location
from backend.app.db.models.site import Site
from backend.app.db.session import get_session_factory
from backend.app.mqtt.schemas import (
    AckMessage,
    HeartbeatMessage,
    PresenceMessage,
    SnapshotMessage,
    TelemetryMessage,
)


def _aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _received_at(value: datetime | None) -> datetime:
    received = value or datetime.now(UTC)
    _aware(received, "received_at")
    return received


async def _find_gateway(
    session: AsyncSession,
    gateway_code: str,
    site_code: str | None,
) -> tuple[Gateway, Site]:
    statement = select(Gateway).join(Site, Site.id == Gateway.site_id).where(
        Gateway.code == gateway_code
    )
    if site_code is not None:
        statement = statement.where(Site.code == site_code)
    gateways = list(await session.scalars(statement.with_for_update()))
    if len(gateways) != 1:
        raise ValueError(
            f"gateway {gateway_code!r} was not found or is ambiguous for site {site_code!r}"
        )
    gateway = gateways[0]
    site = await session.get(Site, gateway.site_id)
    if site is None:
        raise ValueError(f"site for gateway {gateway_code!r} was not found")
    return gateway, site


async def _find_controller(
    session: AsyncSession,
    gateway: Gateway,
    controller_code: str,
) -> Controller:
    controller = await session.scalar(
        select(Controller)
        .where(
            Controller.gateway_id == gateway.id,
            Controller.code == controller_code,
        )
        .with_for_update()
    )
    if controller is None:
        raise ValueError(
            f"controller {controller_code!r} was not found on gateway {gateway.code!r}"
        )
    return controller


def _event_payload(message: BaseModel) -> dict[str, Any]:
    return message.model_dump(mode="json")


def _record_event(
    session: AsyncSession,
    *,
    site: Site,
    gateway: Gateway,
    event_type: str,
    occurred_at: datetime,
    received_at: datetime,
    payload: BaseModel,
    controller: Controller | None = None,
    location_id: Any = None,
) -> None:
    session.add(
        DeviceEvent(
            site_id=site.id,
            gateway_id=gateway.id,
            controller_id=controller.id if controller is not None else None,
            location_id=location_id,
            event_type=event_type,
            occurred_at=occurred_at,
            received_at=received_at,
            payload=_event_payload(payload),
        )
    )


def _apply_lamp_report(
    lamp: LampState,
    *,
    actual_state: ActualState,
    output_state: ControllerOutputState,
    health: LampHealth,
    current_ma: Decimal | None,
    occurred_at: datetime,
) -> None:
    old_values = (
        lamp.actual_state,
        lamp.controller_output_state,
        lamp.lamp_health,
        lamp.current_ma,
    )
    if lamp.actual_state is not actual_state:
        lamp.actual_changed_at = occurred_at
    lamp.actual_state = actual_state
    lamp.controller_output_state = output_state
    lamp.lamp_health = health
    lamp.current_ma = current_ma
    lamp.last_device_report_at = occurred_at
    new_values = (actual_state, output_state, health, current_ma)
    if old_values != new_values:
        lamp.version += 1


async def _lamp_states_for_gateway(
    session: AsyncSession,
    gateway_id: Any,
) -> list[LampState]:
    return list(
        await session.scalars(
            select(LampState)
            .join(Location, Location.id == LampState.location_id)
            .where(Location.gateway_id == gateway_id)
            .with_for_update()
        )
    )


async def _lamp_states_for_controller(
    session: AsyncSession,
    controller_id: Any,
) -> list[tuple[LampState, int]]:
    rows = (
        await session.execute(
            select(LampState, Location.channel_number)
            .join(Location, Location.id == LampState.location_id)
            .where(Location.controller_id == controller_id)
            .with_for_update()
        )
    ).all()
    return [(lamp, channel) for lamp, channel in rows]


def _mark_unknown(lamps: Sequence[LampState], occurred_at: datetime) -> None:
    for lamp in lamps:
        _apply_lamp_report(
            lamp,
            actual_state=ActualState.UNKNOWN,
            output_state=ControllerOutputState.UNKNOWN,
            health=LampHealth.UNKNOWN,
            current_ma=None,
            occurred_at=occurred_at,
        )


async def _mark_controller_unknown(
    session: AsyncSession,
    controller: Controller,
    occurred_at: datetime,
) -> None:
    rows = await _lamp_states_for_controller(session, controller.id)
    _mark_unknown([lamp for lamp, _ in rows], occurred_at)


async def _handle_ack(
    payload: AckMessage,
    site_code: str | None,
    received_at: datetime,
    session: AsyncSession,
) -> None:
    command = await session.get(LightCommand, payload.command_id, with_for_update=True)
    if command is None:
        raise ValueError(f"command {payload.command_id} was not found")
    gateway = await session.get(Gateway, command.gateway_id, with_for_update=True)
    controller = await session.get(Controller, command.controller_id, with_for_update=True)
    location = await session.get(Location, command.location_id)
    lamp = await session.get(LampState, command.location_id, with_for_update=True)
    if gateway is None or controller is None or location is None or lamp is None:
        raise ValueError(f"mapping for command {payload.command_id} is incomplete")
    site = await session.get(Site, gateway.site_id)
    if site is None:
        raise ValueError(f"site for command {payload.command_id} was not found")
    if site_code is not None and site.code != site_code:
        raise ValueError("ACK site does not match command mapping")
    if (
        payload.gateway_code != gateway.code
        or payload.controller_code != controller.code
        or payload.channel != command.channel_number
        or location.gateway_id != command.gateway_id
        or location.controller_id != command.controller_id
    ):
        raise ValueError("ACK mapping does not match command mapping")

    gateway.status = DeviceStatus.ONLINE
    gateway.last_seen_at = received_at
    if payload.error_code == "CONTROLLER_OFFLINE":
        controller.status = DeviceStatus.OFFLINE
        await _mark_controller_unknown(session, controller, payload.occurred_at)
    else:
        controller.status = DeviceStatus.ONLINE
        controller.last_seen_at = received_at

    command.acked_at = payload.occurred_at
    if payload.accepted:
        command.status = CommandStatus.ACKED
        command.last_error = None
        reported_actual = payload.actual_output_state
    else:
        command.status = CommandStatus.FAILED
        parts = [value for value in (payload.error_code, payload.error_message) if value]
        command.last_error = ": ".join(parts) or "Device rejected command"
        reported_actual = (
            ActualState.OFF
            if payload.actual_output_state is ActualState.OFF
            else ActualState.UNKNOWN
        )

    if reported_actual is ActualState.UNKNOWN:
        _apply_lamp_report(
            lamp,
            actual_state=ActualState.UNKNOWN,
            output_state=ControllerOutputState.UNKNOWN,
            health=LampHealth.UNKNOWN,
            current_ma=None,
            occurred_at=payload.occurred_at,
        )
    else:
        output_state = ControllerOutputState(reported_actual.value)
        current = Decimal(str(payload.current_ma)) if payload.current_ma is not None else None
        if reported_actual is ActualState.ON:
            health = (
                LampHealth.SUSPECTED_FAILED
                if current is not None and current <= 0
                else LampHealth.OK
            )
        else:
            health = lamp.lamp_health
        _apply_lamp_report(
            lamp,
            actual_state=reported_actual,
            output_state=output_state,
            health=health,
            current_ma=current,
            occurred_at=payload.occurred_at,
        )

    _record_event(
        session,
        site=site,
        gateway=gateway,
        controller=controller,
        location_id=location.id,
        event_type="ACK",
        occurred_at=payload.occurred_at,
        received_at=received_at,
        payload=payload,
    )
    await session.flush()


async def handle_ack(
    payload: AckMessage,
    *,
    site_code: str | None = None,
    received_at: datetime | None = None,
    session: AsyncSession | None = None,
) -> None:
    received = _received_at(received_at)
    if session is not None:
        await _handle_ack(payload, site_code, received, session)
        return
    async with get_session_factory()() as owned_session:
        try:
            await _handle_ack(payload, site_code, received, owned_session)
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise


async def _handle_presence(
    payload: PresenceMessage,
    site_code: str | None,
    received_at: datetime,
    session: AsyncSession,
) -> None:
    gateway, site = await _find_gateway(session, payload.gateway_code, site_code)
    gateway.status = DeviceStatus(payload.status)
    if gateway.status is DeviceStatus.ONLINE:
        gateway.last_seen_at = received_at
    else:
        controllers = list(
            await session.scalars(
                select(Controller)
                .where(Controller.gateway_id == gateway.id)
                .with_for_update()
            )
        )
        for controller in controllers:
            controller.status = DeviceStatus.OFFLINE
        _mark_unknown(
            await _lamp_states_for_gateway(session, gateway.id),
            payload.occurred_at,
        )
    _record_event(
        session,
        site=site,
        gateway=gateway,
        event_type="PRESENCE",
        occurred_at=payload.occurred_at,
        received_at=received_at,
        payload=payload,
    )
    await session.flush()


async def handle_presence(
    payload: PresenceMessage,
    *,
    site_code: str | None = None,
    received_at: datetime | None = None,
    session: AsyncSession | None = None,
) -> None:
    received = _received_at(received_at)
    if session is not None:
        await _handle_presence(payload, site_code, received, session)
        return
    async with get_session_factory()() as owned_session:
        try:
            await _handle_presence(payload, site_code, received, owned_session)
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise


async def _handle_heartbeat(
    payload: HeartbeatMessage,
    site_code: str | None,
    received_at: datetime,
    session: AsyncSession,
) -> None:
    gateway, site = await _find_gateway(session, payload.gateway_code, site_code)
    gateway.status = DeviceStatus.ONLINE
    gateway.last_seen_at = received_at
    codes = [item.code for item in payload.controllers]
    if len(codes) != len(set(codes)):
        raise ValueError("heartbeat controller codes must be unique")
    for report in payload.controllers:
        controller = await _find_controller(session, gateway, report.code)
        controller.status = DeviceStatus(report.status)
        controller.last_seen_at = received_at
        if controller.status is DeviceStatus.OFFLINE:
            await _mark_controller_unknown(session, controller, payload.occurred_at)
    _record_event(
        session,
        site=site,
        gateway=gateway,
        event_type="HEARTBEAT",
        occurred_at=payload.occurred_at,
        received_at=received_at,
        payload=payload,
    )
    await session.flush()


async def handle_heartbeat(
    payload: HeartbeatMessage,
    *,
    site_code: str | None = None,
    received_at: datetime | None = None,
    session: AsyncSession | None = None,
) -> None:
    received = _received_at(received_at)
    if session is not None:
        await _handle_heartbeat(payload, site_code, received, session)
        return
    async with get_session_factory()() as owned_session:
        try:
            await _handle_heartbeat(payload, site_code, received, owned_session)
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise


async def _handle_snapshot(
    payload: SnapshotMessage,
    site_code: str | None,
    received_at: datetime,
    session: AsyncSession,
) -> None:
    gateway, site = await _find_gateway(session, payload.gateway_code, site_code)
    gateway.status = DeviceStatus.ONLINE
    gateway.last_seen_at = received_at
    codes = [item.code for item in payload.controllers]
    if len(codes) != len(set(codes)):
        raise ValueError("snapshot controller codes must be unique")
    for report in payload.controllers:
        controller = await _find_controller(session, gateway, report.code)
        controller.status = DeviceStatus(report.status)
        controller.last_seen_at = received_at
        rows = await _lamp_states_for_controller(session, controller.id)
        if controller.status is DeviceStatus.OFFLINE:
            _mark_unknown([lamp for lamp, _ in rows], payload.occurred_at)
            continue
        on_channels = set(report.on_channels)
        failed_channels = set(report.failed_lamp_channels)
        for lamp, channel in rows:
            is_on = channel in on_channels
            is_failed = channel in failed_channels
            if is_failed:
                current: Decimal | None = Decimal("0")
            elif is_on and lamp.current_ma is not None and lamp.current_ma > 0:
                current = lamp.current_ma
            elif is_on:
                current = None
            else:
                current = Decimal("0")
            _apply_lamp_report(
                lamp,
                actual_state=ActualState.ON if is_on else ActualState.OFF,
                output_state=(
                    ControllerOutputState.ON if is_on else ControllerOutputState.OFF
                ),
                health=(
                    LampHealth.SUSPECTED_FAILED if is_failed else LampHealth.OK
                ),
                current_ma=current,
                occurred_at=payload.occurred_at,
            )
    _record_event(
        session,
        site=site,
        gateway=gateway,
        event_type="SNAPSHOT",
        occurred_at=payload.occurred_at,
        received_at=received_at,
        payload=payload,
    )
    await session.flush()


async def handle_snapshot(
    payload: SnapshotMessage,
    *,
    site_code: str | None = None,
    received_at: datetime | None = None,
    session: AsyncSession | None = None,
) -> None:
    received = _received_at(received_at)
    if session is not None:
        await _handle_snapshot(payload, site_code, received, session)
        return
    async with get_session_factory()() as owned_session:
        try:
            await _handle_snapshot(payload, site_code, received, owned_session)
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise


async def _handle_telemetry(
    payload: TelemetryMessage,
    site_code: str | None,
    received_at: datetime,
    session: AsyncSession,
) -> None:
    gateway, site = await _find_gateway(session, payload.gateway_code, site_code)
    controller = await _find_controller(session, gateway, payload.controller_code)
    gateway.status = DeviceStatus.ONLINE
    gateway.last_seen_at = received_at
    controller.status = DeviceStatus.ONLINE
    controller.last_seen_at = received_at

    reports = {report.channel: report for report in payload.channels}
    if len(reports) != len(payload.channels):
        raise ValueError("telemetry channel numbers must be unique")
    rows = await _lamp_states_for_controller(session, controller.id)
    locations_by_channel = {channel: lamp for lamp, channel in rows}
    unknown_channels = set(reports) - set(locations_by_channel)
    if unknown_channels:
        raise ValueError(
            f"telemetry contains unmapped channels: {sorted(unknown_channels)}"
        )

    for channel, report in reports.items():
        lamp = locations_by_channel[channel]
        current = Decimal(str(report.current_ma)) if report.current_ma is not None else None
        if report.output_state is ActualState.UNKNOWN:
            health = LampHealth.UNKNOWN
            output_state = ControllerOutputState.UNKNOWN
        elif report.output_state is ActualState.ON:
            health = (
                LampHealth.SUSPECTED_FAILED
                if current is not None and current <= 0
                else LampHealth.OK
            )
            output_state = ControllerOutputState.ON
        else:
            # Near-zero current while output is OFF cannot diagnose a failed lamp.
            health = lamp.lamp_health
            output_state = ControllerOutputState.OFF
        _apply_lamp_report(
            lamp,
            actual_state=report.output_state,
            output_state=output_state,
            health=health,
            current_ma=current,
            occurred_at=payload.occurred_at,
        )

    _record_event(
        session,
        site=site,
        gateway=gateway,
        controller=controller,
        event_type="TELEMETRY",
        occurred_at=payload.occurred_at,
        received_at=received_at,
        payload=payload,
    )
    await session.flush()


async def handle_telemetry(
    payload: TelemetryMessage,
    *,
    site_code: str | None = None,
    received_at: datetime | None = None,
    session: AsyncSession | None = None,
) -> None:
    received = _received_at(received_at)
    if session is not None:
        await _handle_telemetry(payload, site_code, received, session)
        return
    async with get_session_factory()() as owned_session:
        try:
            await _handle_telemetry(payload, site_code, received, owned_session)
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise


def parse_device_topic(topic: str) -> tuple[str, str, str]:
    parts = topic.split("/")
    if (
        len(parts) < 7
        or parts[:3] != ["memorial", "v1", "sites"]
        or parts[4] != "gateways"
        or not parts[3]
        or not parts[5]
    ):
        raise ValueError(f"invalid device topic: {topic}")
    if len(parts) == 7 and parts[6] in {"acks", "heartbeat", "presence", "snapshot"}:
        return parts[3], parts[5], parts[6]
    if (
        len(parts) == 9
        and parts[6] == "controllers"
        and parts[7]
        and parts[8] in {"state", "telemetry"}
    ):
        return parts[3], parts[5], "/".join(parts[6:])
    raise ValueError(f"invalid device topic: {topic}")


async def route_device_message(topic: str, payload: bytes) -> bool:
    site_code, gateway_code, event = parse_device_topic(topic)
    if event == "acks":
        ack = AckMessage.model_validate_json(payload)
        if ack.gateway_code != gateway_code:
            raise ValueError("ACK gateway does not match MQTT topic")
        await handle_ack(ack, site_code=site_code)
        return True
    if event == "heartbeat":
        heartbeat = HeartbeatMessage.model_validate_json(payload)
        if heartbeat.gateway_code != gateway_code:
            raise ValueError("heartbeat gateway does not match MQTT topic")
        await handle_heartbeat(heartbeat, site_code=site_code)
        return True
    if event == "presence":
        presence = PresenceMessage.model_validate_json(payload)
        if presence.gateway_code != gateway_code:
            raise ValueError("presence gateway does not match MQTT topic")
        await handle_presence(presence, site_code=site_code)
        return True
    if event == "snapshot":
        snapshot = SnapshotMessage.model_validate_json(payload)
        if snapshot.gateway_code != gateway_code:
            raise ValueError("snapshot gateway does not match MQTT topic")
        await handle_snapshot(snapshot, site_code=site_code)
        return True
    if event.startswith("controllers/") and event.endswith("/telemetry"):
        topic_controller = event.split("/")[1]
        telemetry = TelemetryMessage.model_validate_json(payload)
        if telemetry.gateway_code != gateway_code:
            raise ValueError("telemetry gateway does not match MQTT topic")
        if telemetry.controller_code != topic_controller:
            raise ValueError("telemetry controller does not match MQTT topic")
        await handle_telemetry(telemetry, site_code=site_code)
        return True
    return False


@dataclass(frozen=True)
class IncomingDeviceMessage:
    topic: str
    payload: bytes


class PahoMQTTConsumer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        client_id: str = "memorial-device-consumer",
    ) -> None:
        self._host = host
        self._port = port
        self._client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
        self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect
        self._client.on_subscribe = self._on_subscribe
        self._client.on_message = self._on_message
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready_future: asyncio.Future[None] | None = None
        self._queue: asyncio.Queue[IncomingDeviceMessage] | None = None
        self._subscriptions: Sequence[tuple[str, int]] = ()
        self._pending_subscription_ids: set[int] = set()
        self._started = False

    def _complete_ready(self, error: Exception | None = None) -> None:
        if self._ready_future is None or self._ready_future.done():
            return
        if error is None:
            self._ready_future.set_result(None)
        else:
            self._ready_future.set_exception(error)

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        del userdata, flags, properties
        if self._loop is None:
            return
        if reason_code != 0:
            self._loop.call_soon_threadsafe(
                self._complete_ready,
                ConnectionError(f"MQTT connection failed: {reason_code}"),
            )
            return
        self._pending_subscription_ids.clear()
        for topic, qos in self._subscriptions:
            result, message_id = client.subscribe(topic, qos=qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                self._loop.call_soon_threadsafe(
                    self._complete_ready,
                    ConnectionError(mqtt.error_string(result)),
                )
                return
            if message_id is None:
                self._loop.call_soon_threadsafe(
                    self._complete_ready,
                    ConnectionError("MQTT subscribe did not return a message id"),
                )
                return
            self._pending_subscription_ids.add(message_id)
        if not self._pending_subscription_ids:
            self._loop.call_soon_threadsafe(self._complete_ready)

    def _on_subscribe(
        self,
        client: mqtt.Client,
        userdata: Any,
        message_id: int,
        reason_codes: Any,
        properties: Any,
    ) -> None:
        del client, userdata, reason_codes, properties
        self._pending_subscription_ids.discard(message_id)
        if not self._pending_subscription_ids and self._loop is not None:
            self._loop.call_soon_threadsafe(self._complete_ready)

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        del client, userdata
        if self._loop is None or self._queue is None:
            return
        incoming = IncomingDeviceMessage(message.topic, bytes(message.payload))
        self._loop.call_soon_threadsafe(self._queue.put_nowait, incoming)

    def _start_sync(self) -> None:
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()
        self._started = True

    async def start(self, subscriptions: Sequence[tuple[str, int]]) -> None:
        self._loop = asyncio.get_running_loop()
        self._ready_future = self._loop.create_future()
        self._queue = asyncio.Queue()
        self._subscriptions = subscriptions
        try:
            await asyncio.to_thread(self._start_sync)
            await asyncio.wait_for(self._ready_future, timeout=10)
        except Exception:
            if self._started:
                self._client.loop_stop()
                self._started = False
            raise

    async def messages(self) -> AsyncIterator[IncomingDeviceMessage]:
        if self._queue is None:
            raise RuntimeError("MQTT consumer is not started")
        while True:
            yield await self._queue.get()

    def _close_sync(self) -> None:
        if not self._started:
            return
        self._client.disconnect()
        self._client.loop_stop()
        self._started = False

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)
