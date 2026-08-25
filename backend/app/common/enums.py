from enum import StrEnum

from sqlalchemy import Enum as SqlEnum


class DeviceStatus(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class DesiredState(StrEnum):
    ON = "ON"
    OFF = "OFF"


class ActualState(StrEnum):
    ON = "ON"
    OFF = "OFF"
    UNKNOWN = "UNKNOWN"


class ControllerOutputState(StrEnum):
    ON = "ON"
    OFF = "OFF"
    UNKNOWN = "UNKNOWN"


class LampHealth(StrEnum):
    OK = "OK"
    SUSPECTED_FAILED = "SUSPECTED_FAILED"
    UNKNOWN = "UNKNOWN"


class ActivationReason(StrEnum):
    ANNIVERSARY = "ANNIVERSARY"
    VISIT = "VISIT"
    MANUAL_ON = "MANUAL_ON"


class CommandStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    ACKED = "ACKED"
    FAILED = "FAILED"


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    STAFF = "STAFF"
    TECHNICIAN = "TECHNICIAN"


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_type]


DEVICE_STATUS_DB = SqlEnum(
    DeviceStatus,
    name="device_status",
    values_callable=enum_values,
    validate_strings=True,
)
DESIRED_STATE_DB = SqlEnum(
    DesiredState,
    name="desired_state",
    values_callable=enum_values,
    validate_strings=True,
)
ACTUAL_STATE_DB = SqlEnum(
    ActualState,
    name="actual_state",
    values_callable=enum_values,
    validate_strings=True,
)
CONTROLLER_OUTPUT_STATE_DB = SqlEnum(
    ControllerOutputState,
    name="controller_output_state",
    values_callable=enum_values,
    validate_strings=True,
)
LAMP_HEALTH_DB = SqlEnum(
    LampHealth,
    name="lamp_health",
    values_callable=enum_values,
    validate_strings=True,
)
ACTIVATION_REASON_DB = SqlEnum(
    ActivationReason,
    name="activation_reason",
    values_callable=enum_values,
    validate_strings=True,
)
COMMAND_STATUS_DB = SqlEnum(
    CommandStatus,
    name="command_status",
    values_callable=enum_values,
    validate_strings=True,
)
USER_ROLE_DB = SqlEnum(
    UserRole,
    name="user_role",
    values_callable=enum_values,
    validate_strings=True,
)
