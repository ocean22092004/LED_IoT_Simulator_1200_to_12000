TOPIC_PREFIX = "memorial/v1"


def _segment(value: str, name: str) -> str:
    if not value or any(character in value for character in "/+#"):
        raise ValueError(f"{name} must be a non-empty MQTT topic segment")
    return value


def command_topic(site_code: str, gateway_code: str) -> str:
    site = _segment(site_code, "site_code")
    gateway = _segment(gateway_code, "gateway_code")
    return f"{TOPIC_PREFIX}/sites/{site}/gateways/{gateway}/commands"


def ack_topic_filter() -> str:
    return f"{TOPIC_PREFIX}/sites/+/gateways/+/acks"


def heartbeat_topic_filter() -> str:
    return f"{TOPIC_PREFIX}/sites/+/gateways/+/heartbeat"


def presence_topic_filter() -> str:
    return f"{TOPIC_PREFIX}/sites/+/gateways/+/presence"


def snapshot_topic_filter() -> str:
    return f"{TOPIC_PREFIX}/sites/+/gateways/+/snapshot"


def controller_state_topic_filter() -> str:
    return f"{TOPIC_PREFIX}/sites/+/gateways/+/controllers/+/state"


def controller_telemetry_topic_filter() -> str:
    return f"{TOPIC_PREFIX}/sites/+/gateways/+/controllers/+/telemetry"
