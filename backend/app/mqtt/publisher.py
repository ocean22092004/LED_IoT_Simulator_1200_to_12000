import asyncio
from typing import Protocol

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from backend.app.config import Settings


class MQTTPublisher(Protocol):
    async def publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> None: ...


class PahoMQTTPublisher:
    def __init__(self, settings: Settings) -> None:
        self._host = settings.mqtt_host
        self._port = settings.mqtt_port
        self._client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id="memorial-command-worker",
            protocol=mqtt.MQTTv311,
        )
        self._client.username_pw_set(
            settings.mqtt_username,
            settings.mqtt_password.get_secret_value(),
        )
        self._started = False
        self._lock = asyncio.Lock()

    def _start_sync(self) -> None:
        if self._started:
            return
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()
        self._started = True

    async def start(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._start_sync)

    def _publish_sync(
        self,
        topic: str,
        payload: str,
        qos: int,
        retain: bool,
    ) -> None:
        self._start_sync()
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
        async with self._lock:
            await asyncio.to_thread(
                self._publish_sync,
                topic,
                payload,
                qos,
                retain,
            )

    def _close_sync(self) -> None:
        if not self._started:
            return
        self._client.disconnect()
        self._client.loop_stop()
        self._started = False

    async def close(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._close_sync)
