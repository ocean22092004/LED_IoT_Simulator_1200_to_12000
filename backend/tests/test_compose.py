import os
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.docker
def test_compose_forwards_api_and_command_worker_configuration():
    environment = os.environ | {
        "DATABASE_URL": "postgresql+asyncpg://override:override@db.example:5432/override",
        "JWT_EXPIRE_MINUTES": "321",
        "SIMULATOR_LOCATION_COUNT": "12000",
        "SIMULATOR_ZONES": "A,B,C",
        "SIMULATOR_LOCATIONS_PER_ZONE": "250",
        "SIMULATOR_CONTROLLER_CAPACITY": "32",
        "DEVICE_HEARTBEAT_SECONDS": "7",
        "DEVICE_OFFLINE_AFTER_SECONDS": "21",
        "COMMAND_ACK_TIMEOUT_SECONDS": "9",
    }
    completed = subprocess.run(
        ["docker", "compose", "config"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    compose = yaml.safe_load(completed.stdout)
    api = compose["services"]["api"]
    expected_environment = {
        "DATABASE_URL": environment["DATABASE_URL"],
        "JWT_EXPIRE_MINUTES": "321",
        "SIMULATOR_LOCATION_COUNT": "12000",
        "SIMULATOR_ZONES": "A,B,C",
        "SIMULATOR_LOCATIONS_PER_ZONE": "250",
        "SIMULATOR_CONTROLLER_CAPACITY": "32",
        "DEVICE_HEARTBEAT_SECONDS": "7",
        "DEVICE_OFFLINE_AFTER_SECONDS": "21",
        "COMMAND_ACK_TIMEOUT_SECONDS": "9",
    }
    assert {
        key: api["environment"][key]
        for key in expected_environment
        if key in api["environment"]
    } == expected_environment
    assert set(api["depends_on"]) == {"postgres"}

    worker = compose["services"]["command-worker"]
    assert worker["command"] == ["python", "-m", "backend.app.workers.command_worker"]
    assert worker["environment"]["DATABASE_URL"] == environment["DATABASE_URL"]
    assert worker["environment"]["MQTT_HOST"] == "mosquitto"
    assert set(worker["depends_on"]) == {"postgres", "mosquitto"}
    assert worker["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert worker["depends_on"]["mosquitto"]["condition"] == "service_healthy"
