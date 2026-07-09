"""In-container job scheduler — replaces the host-side systemd timers.

The scheduler starts with the FastAPI app (lifespan startup), runs jobs in
background threads, and stops cleanly on shutdown. All schedule definitions
live HERE, in the codebase, versioned with the worker — operator just runs
`docker compose pull && docker compose up -d` to pick up schedule changes.

Schedule (UTC):
    - 05:00 daily       : OpenAI ground-truth billing pull (E18 finops)
    - 08:00 daily       : sleep + HRV + daily metrics
    - 13:00 daily       : activities + daily metrics
    - 18:00 daily       : activities + daily metrics
    - Mon 06:00         : profile refresh (FTP / VMA / FCmax)
    - Sun 22:00         : weekly plan regeneration

Jobs are non-overlapping (max_instances=1) and missed jobs are NOT made up
on restart (misfire_grace_time short) — the daily/weekly cadence will
naturally re-cover via the next scheduled fire.
"""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from garmin_sync.observability import capture

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _wrap_job(name: str, runner: Any) -> Any:
    """Wrap a job runner so errors are logged without crashing the scheduler."""

    def _job() -> None:
        log.info("scheduler: starting job=%s", name)
        try:
            result = runner()
            log.info("scheduler: job=%s done result=%s", name, result)
        except Exception as exc:
            log.exception("scheduler: job=%s crashed", name)
            capture(exc, where="scheduler", job=name)

    _job.__name__ = f"scheduled_{name}"
    return _job


def init_scheduler() -> BackgroundScheduler:
    """Build and start the BackgroundScheduler. Idempotent."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    from garmin_sync.billing_sync import run_billing_sync_cron
    from garmin_sync.coach.cron import run_weekly_cron as coach_weekly
    from garmin_sync.cron import (
        run_activities_cron,
        run_profile_sync_cron,
        run_sleep_cron,
    )

    sched = BackgroundScheduler(
        timezone="UTC",
        job_defaults={
            "coalesce": True,  # collapse missed runs into a single one
            "max_instances": 1,  # never start the same job twice in parallel
            "misfire_grace_time": 600,  # 10 min — if missed, fire late once, else skip
        },
    )

    sched.add_job(
        _wrap_job("billing_sync", run_billing_sync_cron),
        CronTrigger(hour=5, minute=0, timezone="UTC"),
        id="billing_sync",
        replace_existing=True,
    )
    sched.add_job(
        _wrap_job("sleep_sync", run_sleep_cron),
        CronTrigger(hour=8, minute=0, timezone="UTC"),
        id="sleep_sync",
        replace_existing=True,
    )
    sched.add_job(
        _wrap_job("activities_midday", run_activities_cron),
        CronTrigger(hour=13, minute=0, timezone="UTC"),
        id="activities_midday",
        replace_existing=True,
    )
    sched.add_job(
        _wrap_job("activities_evening", run_activities_cron),
        CronTrigger(hour=18, minute=0, timezone="UTC"),
        id="activities_evening",
        replace_existing=True,
    )
    sched.add_job(
        _wrap_job("profile_sync", run_profile_sync_cron),
        CronTrigger(day_of_week="mon", hour=6, minute=0, timezone="UTC"),
        id="profile_sync",
        replace_existing=True,
    )
    sched.add_job(
        _wrap_job("plan_regen", coach_weekly),
        CronTrigger(day_of_week="sun", hour=22, minute=0, timezone="UTC"),
        id="plan_regen",
        replace_existing=True,
    )

    sched.start()
    _scheduler = sched
    log.info(
        "scheduler: started with %d jobs: %s",
        len(sched.get_jobs()),
        [j.id for j in sched.get_jobs()],
    )
    return sched


def shutdown_scheduler() -> None:
    """Stop the scheduler. Called from FastAPI lifespan shutdown."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("scheduler: stopped")
    _scheduler = None
