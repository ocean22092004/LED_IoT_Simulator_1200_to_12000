import asyncio
import logging
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import get_settings
from backend.app.mqtt.consumer import PahoMQTTConsumer, route_device_message
from backend.app.mqtt.topics import (
    ack_topic_filter,
    controller_state_topic_filter,
    controller_telemetry_topic_filter,
    heartbeat_topic_filter,
    presence_topic_filter,
    snapshot_topic_filter,
)

LOGGER = logging.getLogger(__name__)
READY_FILE = Path("/tmp/device-consumer-ready")
SUBSCRIPTIONS = (
    (ack_topic_filter(), 1),
    (heartbeat_topic_filter(), 1),
    (presence_topic_filter(), 1),
    (snapshot_topic_filter(), 1),
    (controller_state_topic_filter(), 1),
    (controller_telemetry_topic_filter(), 1),
)


async def run_device_consumer() -> None:
    settings = get_settings()
    consumer = PahoMQTTConsumer(
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        username=settings.mqtt_username,
        password=settings.mqtt_password.get_secret_value(),
    )
    try:
        await consumer.start(SUBSCRIPTIONS)
        await asyncio.to_thread(READY_FILE.touch)
        async for message in consumer.messages():
            try:
                await route_device_message(message.topic, message.payload)
            except ValueError:
                LOGGER.warning("Rejected invalid MQTT device event on %s", message.topic)
            except SQLAlchemyError:
                LOGGER.exception("Database error while consuming %s", message.topic)
                await asyncio.sleep(1)
    finally:
        await asyncio.to_thread(READY_FILE.unlink, missing_ok=True)
        await consumer.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_device_consumer())


if __name__ == "__main__":
    main()
