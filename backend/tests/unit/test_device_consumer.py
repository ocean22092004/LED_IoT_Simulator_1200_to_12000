from datetime import UTC, datetime
from uuid import UUID

import pytest

from backend.app.mqtt.consumer import parse_device_topic
from backend.app.mqtt.schemas import AckMessage

pytestmark = pytest.mark.unit


def test_parse_device_topic_extracts_site_gateway_and_event() -> None:
    assert parse_device_topic(
        "memorial/v1/sites/SITE-001/gateways/GW-A/acks"
    ) == ("SITE-001", "GW-A", "acks")


@pytest.mark.parametrize(
    "topic",
    [
        "memorial/v2/sites/SITE-001/gateways/GW-A/acks",
        "memorial/v1/sites/SITE-001/gateways/GW-A",
        "memorial/v1/sites/SITE-001/controllers/CTRL-A-01/state",
    ],
)
def test_parse_device_topic_rejects_wrong_namespace(topic: str) -> None:
    with pytest.raises(ValueError, match="topic"):
        parse_device_topic(topic)


def test_ack_schema_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AckMessage(
            command_id=UUID("4b27e51e-0d33-4a91-83a4-5d7e176179bb"),
            occurred_at=datetime(2026, 8, 26, 9, 0),
            gateway_code="GW-A",
            controller_code="CTRL-A-01",
            channel=1,
            accepted=True,
            actual_output_state="ON",
            current_ma=42.5,
            error_code=None,
            error_message=None,
        )


def test_ack_schema_accepts_aware_timestamp() -> None:
    message = AckMessage(
        command_id=UUID("4b27e51e-0d33-4a91-83a4-5d7e176179bb"),
        occurred_at=datetime(2026, 8, 26, 9, 0, tzinfo=UTC),
        gateway_code="GW-A",
        controller_code="CTRL-A-01",
        channel=1,
        accepted=True,
        actual_output_state="ON",
        current_ma=42.5,
        error_code=None,
        error_message=None,
    )

    assert message.model_dump_json().startswith('{"schema_version":1')
