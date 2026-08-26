import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.activations.service import expire_activations
from backend.app.anniversaries.lunar import (
    LunarCalendarProvider,
    default_lunar_calendar,
)
from backend.app.anniversaries.service import sync_anniversaries_for_local_date
from backend.app.config import Settings, get_settings
from backend.app.db.session import get_session_factory
from backend.app.devices.service import StaleDeviceSweepResult, sweep_stale_devices
from backend.app.lights.reconciliation import reconcile_all

READY_FILE = Path("/tmp/scheduler-ready")


@dataclass(frozen=True)
class StartupRecoveryResult:
    anniversaries_created: int
    activations_expired: int
    stale_devices: StaleDeviceSweepResult
    locations_reconciled: int


def _now() -> datetime:
    return datetime.now(UTC)


async def run_anniversary_sync(
    *,
    now: datetime | None = None,
    provider: LunarCalendarProvider = default_lunar_calendar,
    session: AsyncSession | None = None,
) -> int:
    run_at = now or _now()
    local_date = run_at.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    return await sync_anniversaries_for_local_date(
        local_date,
        provider=provider,
        now=run_at,
        session=session,
    )


async def run_expiry_sweep(
    *,
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> int:
    return await expire_activations(now=now or _now(), session=session)


async def run_reconciliation(
    *,
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> int:
    return await reconcile_all(now=now or _now(), session=session)


async def run_stale_sweep(
    *,
    offline_after_seconds: int,
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> StaleDeviceSweepResult:
    return await sweep_stale_devices(
        now=now or _now(),
        offline_after_seconds=offline_after_seconds,
        session=session,
    )


async def _run_startup_recovery(
    *,
    now: datetime,
    provider: LunarCalendarProvider,
    offline_after_seconds: int,
    session: AsyncSession,
) -> StartupRecoveryResult:
    anniversaries_created = await run_anniversary_sync(
        now=now,
        provider=provider,
        session=session,
    )
    activations_expired = await run_expiry_sweep(now=now, session=session)
    stale_devices = await run_stale_sweep(
        now=now,
        offline_after_seconds=offline_after_seconds,
        session=session,
    )
    locations_reconciled = await run_reconciliation(now=now, session=session)
    return StartupRecoveryResult(
        anniversaries_created=anniversaries_created,
        activations_expired=activations_expired,
        stale_devices=stale_devices,
        locations_reconciled=locations_reconciled,
    )


async def run_startup_recovery(
    *,
    now: datetime | None = None,
    provider: LunarCalendarProvider = default_lunar_calendar,
    offline_after_seconds: int = 15,
    session: AsyncSession | None = None,
) -> StartupRecoveryResult:
    run_at = now or _now()
    if session is not None:
        return await _run_startup_recovery(
            now=run_at,
            provider=provider,
            offline_after_seconds=offline_after_seconds,
            session=session,
        )
    async with get_session_factory()() as owned_session:
        try:
            result = await _run_startup_recovery(
                now=run_at,
                provider=provider,
                offline_after_seconds=offline_after_seconds,
                session=owned_session,
            )
            await owned_session.commit()
        except Exception:
            await owned_session.rollback()
            raise
    return result


def build_scheduler(settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(
        timezone=ZoneInfo(settings.app_timezone),
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 30},
    )
    scheduler.add_job(
        run_anniversary_sync,
        "interval",
        seconds=60,
        id="anniversary-sync",
    )
    scheduler.add_job(
        run_expiry_sweep,
        "interval",
        seconds=5,
        id="activation-expiry",
    )
    scheduler.add_job(
        run_reconciliation,
        "interval",
        seconds=10,
        id="state-reconciliation",
    )
    scheduler.add_job(
        partial(
            run_stale_sweep,
            offline_after_seconds=settings.device_offline_after_seconds,
        ),
        "interval",
        seconds=10,
        id="device-stale-sweep",
    )
    return scheduler


async def run_scheduler() -> None:
    settings = get_settings()
    scheduler = build_scheduler(settings)
    try:
        await run_startup_recovery(
            offline_after_seconds=settings.device_offline_after_seconds
        )
        scheduler.start()
        await asyncio.to_thread(READY_FILE.touch)
        await asyncio.Event().wait()
    finally:
        await asyncio.to_thread(READY_FILE.unlink, missing_ok=True)
        if scheduler.running:
            scheduler.shutdown(wait=False)


def main() -> None:
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
