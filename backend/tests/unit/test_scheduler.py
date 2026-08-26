from datetime import timedelta

import pytest

from backend.app.config import Settings
from backend.app.workers.scheduler import build_scheduler

pytestmark = pytest.mark.unit


def test_scheduler_registers_exact_spec_intervals() -> None:
    scheduler = build_scheduler(Settings(_env_file=None))
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert set(jobs) == {
        "anniversary-sync",
        "activation-expiry",
        "state-reconciliation",
        "device-stale-sweep",
    }
    assert jobs["anniversary-sync"].trigger.interval == timedelta(seconds=60)
    assert jobs["activation-expiry"].trigger.interval == timedelta(seconds=5)
    assert jobs["state-reconciliation"].trigger.interval == timedelta(seconds=10)
    assert jobs["device-stale-sweep"].trigger.interval == timedelta(seconds=10)
