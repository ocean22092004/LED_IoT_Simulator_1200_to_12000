import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion


@dataclass(frozen=True)
class LastWill:
    topic: str
    payload: str
    qos: int
    retain: bool


@dataclass(frozen=True)
class IncomingMessage:
    topic: str
    payload: bytes


class GatewayMQTTClient(Protocol):
    async def connect(self, last_will: LastWill) -> None: ...

    async def subscribe(self, topic: str, qos: int) -> None: ...

    async def publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> None: ...

    def messages(self) -> AsyncIterator[IncomingMessage]: ...

    async def wait_for_reconnect(self) -> None: ...

    async def disconnect(self) -> None: ...


class PahoGatewayMQTTClient:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        client_id: str,
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
        self._client.on_message = self._on_message
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connect_future: asyncio.Future[None] | None = None
        self._message_queue: asyncio.Queue[IncomingMessage] | None = None
        self._reconnect_queue: asyncio.Queue[None] | None = None
        self._has_connected = False
        self._started = False
        self._publish_lock = asyncio.Lock()

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        del client, userdata, flags, properties
        if self._loop is None:
            return

        def complete_connection() -> None:
            if reason_code != 0:
                if self._connect_future is not None and not self._connect_future.done():
                    self._connect_future.set_exception(
                        ConnectionError(f"MQTT connection failed: {reason_code}")
                    )
                return
            if not self._has_connected:
                self._has_connected = True
                if self._connect_future is not None and not self._connect_future.done():
                    self._connect_future.set_result(None)
            elif self._reconnect_queue is not None:
                self._reconnect_queue.put_nowait(None)

        self._loop.call_soon_threadsafe(complete_connection)

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        del client, userdata
        if self._loop is None or self._message_queue is None:
            return
        incoming = IncomingMessage(message.topic, bytes(message.payload))
        self._loop.call_soon_threadsafe(self._message_queue.put_nowait, incoming)

    def _connect_sync(self, last_will: LastWill) -> None:
        self._client.will_set(
            last_will.topic,
            last_will.payload,
            qos=last_will.qos,
            retain=last_will.retain,
        )
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()
        self._started = True

    async def connect(self, last_will: LastWill) -> None:
        self._loop = asyncio.get_running_loop()
        self._connect_future = self._loop.create_future()
        if self._message_queue is None:
            self._message_queue = asyncio.Queue()
        if self._reconnect_queue is None:
            self._reconnect_queue = asyncio.Queue()
        self._has_connected = False
        try:
            await asyncio.to_thread(self._connect_sync, last_will)
            await asyncio.wait_for(self._connect_future, timeout=10)
        except Exception:
            if self._started:
                self._client.loop_stop()
                self._started = False
            raise

    async def subscribe(self, topic: str, qos: int) -> None:
        result, _ = self._client.subscribe(topic, qos=qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(mqtt.error_string(result))

    def _publish_sync(self, topic: str, payload: str, qos: int, retain: bool) -> None:
        result = self._client.publish(topic, payload, qos=qos, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(mqtt.error_string(result.rc))
        result.wait_for_publish(timeout=10)
        if not result.is_published():
            raise TimeoutError("MQTT publish was not acknowledged by the broker")

    async def publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> None:
        async with self._publish_lock:
            await asyncio.to_thread(self._publish_sync, topic, payload, qos, retain)

    async def messages(self) -> AsyncIterator[IncomingMessage]:
        if self._message_queue is None:
            raise RuntimeError("MQTT client is not connected")
        while True:
            yield await self._message_queue.get()

    async def wait_for_reconnect(self) -> None:
        if self._reconnect_queue is None:
            raise RuntimeError("MQTT client is not connected")
        await self._reconnect_queue.get()

    def _disconnect_sync(self) -> None:
        if not self._started:
            return
        self._client.disconnect()
        self._client.loop_stop()
        self._started = False

    async def disconnect(self) -> None:
        await asyncio.to_thread(self._disconnect_sync)
        self._has_connected = False
