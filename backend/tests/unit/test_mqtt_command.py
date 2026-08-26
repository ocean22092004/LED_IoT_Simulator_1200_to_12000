from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.common.enums import DesiredState
from backend.app.mqtt.schemas import LightCommandMessage
from backend.app.mqtt.topics import (
    ack_topic_filter,
    command_topic,
    heartbeat_topic_filter,
    presence_topic_filter,
    snapshot_topic_filter,
)

pytestmark = pytest.mark.unit
COMMAND_ID = UUID("4b27e51e-0d33-4a91-83a4-5d7e176179bb")


def test_command_topic_and_consumer_filters_follow_namespace() -> None:
    assert command_topic("SITE-001", "GW-A") == (
        "memorial/v1/sites/SITE-001/gateways/GW-A/commands"
    )
    assert ack_topic_filter() == "memorial/v1/sites/+/gateways/+/acks"
    assert heartbeat_topic_filter() == "memorial/v1/sites/+/gateways/+/heartbeat"
    assert presence_topic_filter() == "memorial/v1/sites/+/gateways/+/presence"
    assert snapshot_topic_filter() == "memorial/v1/sites/+/gateways/+/snapshot"


@pytest.mark.parametrize("invalid_segment", ["", "GW/A", "GW+", "GW#"])
def test_topic_segment_rejects_empty_wildcard_or_separator(invalid_segment: str) -> None:
    with pytest.raises(ValueError):
        command_topic("SITE-001", invalid_segment)


def test_command_schema_serializes_exact_contract_and_round_trips() -> None:
    message = LightCommandMessage(
        command_id=COMMAND_ID,
        issued_at=datetime(2026, 8, 21, 8, 0, tzinfo=UTC),
        site_code="SITE-001",
        gateway_code="GW-A",
        controller_code="CTRL-A-04",
        channel=58,
        target_state=DesiredState.ON,
        location_code="A250",
        reason="VISIT",
    )

    payload = message.model_dump_json()

    assert payload == (
        '{"schema_version":1,'
        '"command_id":"4b27e51e-0d33-4a91-83a4-5d7e176179bb",'
        '"issued_at":"2026-08-21T08:00:00Z",'
        '"site_code":"SITE-001",'
        '"gateway_code":"GW-A",'
        '"controller_code":"CTRL-A-04",'
        '"channel":58,'
        '"target_state":"ON",'
        '"location_code":"A250",'
        '"reason":"VISIT"}'
    )
    assert LightCommandMessage.model_validate_json(payload) == message


def test_command_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        LightCommandMessage.model_validate(
            {
                "schema_version": 1,
                "command_id": str(COMMAND_ID),
                "issued_at": "2026-08-21T08:00:00Z",
                "site_code": "SITE-001",
                "gateway_code": "GW-A",
                "controller_code": "CTRL-A-04",
                "channel": 58,
                "target_state": "ON",
                "location_code": "A250",
                "reason": "VISIT",
                "unexpected": True,
            }
        )
