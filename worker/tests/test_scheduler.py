from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_scheduler_singleton() -> None:
    """Ensure each test starts with no global scheduler."""
    import garmin_sync.scheduler as sched_mod

    if sched_mod._scheduler is not None and sched_mod._scheduler.running:
        sched_mod._scheduler.shutdown(wait=False)
    sched_mod._scheduler = None
    yield
    if sched_mod._scheduler is not None and sched_mod._scheduler.running:
        sched_mod._scheduler.shutdown(wait=False)
    sched_mod._scheduler = None


def test_init_scheduler_registers_six_jobs_with_expected_ids() -> None:
    from garmin_sync.scheduler import init_scheduler, shutdown_scheduler

    sched = init_scheduler()
    try:
        ids = sorted(j.id for j in sched.get_jobs())
        assert ids == sorted(
            [
                "billing_sync",
                "sleep_sync",
                "activities_midday",
                "activities_evening",
                "profile_sync",
                "plan_regen",
            ]
        )
    finally:
        shutdown_scheduler()


def test_init_scheduler_is_idempotent() -> None:
    """Calling init_scheduler twice returns the same already-running scheduler."""
    from garmin_sync.scheduler import init_scheduler, shutdown_scheduler

    s1 = init_scheduler()
    s2 = init_scheduler()
    try:
        assert s1 is s2
        assert s1.running
    finally:
        shutdown_scheduler()


def test_shutdown_scheduler_stops_running_scheduler() -> None:
    from garmin_sync.scheduler import init_scheduler, shutdown_scheduler

    sched = init_scheduler()
    assert sched.running
    shutdown_scheduler()
    assert not sched.running


def test_wrap_job_swallows_exceptions() -> None:
    """A job that crashes must NOT propagate up to the scheduler (would deadlock)."""
    from garmin_sync.scheduler import _wrap_job

    def crash() -> None:
        raise RuntimeError("boom")

    wrapped = _wrap_job("crash", crash)
    # Must not raise
    wrapped()


def test_jobs_resolve_to_real_cron_callables() -> None:
    """Sanity: the job functions imported are the actual cron entry points."""
    from garmin_sync.billing_sync import run_billing_sync_cron
    from garmin_sync.coach.cron import run_weekly_cron
    from garmin_sync.cron import (
        run_activities_cron,
        run_profile_sync_cron,
        run_sleep_cron,
    )

    assert callable(run_billing_sync_cron)
    assert callable(run_sleep_cron)
    assert callable(run_activities_cron)
    assert callable(run_profile_sync_cron)
    assert callable(run_weekly_cron)


@patch("garmin_sync.scheduler.BackgroundScheduler")
def test_init_scheduler_uses_utc_timezone(mock_scheduler_cls: object) -> None:
    from garmin_sync.scheduler import init_scheduler, shutdown_scheduler

    init_scheduler()
    shutdown_scheduler()
    # First positional or kwargs arg should set timezone=UTC
    call_kwargs = mock_scheduler_cls.call_args.kwargs  # type: ignore[attr-defined]
    assert call_kwargs["timezone"] == "UTC"
