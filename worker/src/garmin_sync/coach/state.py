"""Materialize daily Banister state (CTL/ATL/TSB) for fast frontend reads.

Recompute by walking the last ``days_back`` days of TSS from activities and
upserting daily_banister_state. Called at the end of run_sync_for_user after
activities have been inserted.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, cast

from garmin_sync.coach.banister import (
    cold_start_state,
    compute_banister_history,
    is_cold_start,
)
from garmin_sync.coach.tss import compute_tss, resolve_fc_max_bpm
from garmin_sync.supabase_client import get_admin_client


def recompute_daily_state(user_id: str, days_back: int = 180) -> dict[str, int]:
    """Recompute CTL/ATL/TSB for the last ``days_back`` days and upsert."""
    db = get_admin_client()
    today = date.today()
    start = today - timedelta(days=days_back)

    profile_resp = (
        db.table("athlete_profiles")
        .select("hours_per_week, ftp_watts, fc_max_bpm")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    profile = cast("dict[str, Any]", profile_resp.data or {})

    activities_resp = (
        db.table("activities")
        .select("start_time, sport, duration_s, power_avg, hr_avg, hr_max")
        .eq("user_id", user_id)
        .gte("start_time", start.isoformat())
        .execute()
    )
    activities = cast("list[dict[str, Any]]", activities_resp.data or [])
    fc_max = resolve_fc_max_bpm(profile.get("fc_max_bpm"), activities, today=today)

    tss_by_date: dict[date, float] = {}
    for a in activities:
        tss = compute_tss(
            duration_s=a.get("duration_s") or 0,
            sport=a.get("sport") or "",
            power_avg=a.get("power_avg"),
            hr_avg=a.get("hr_avg"),
            ftp_watts=profile.get("ftp_watts"),
            fc_max_bpm=fc_max,
        )
        if tss is None:
            continue
        raw_start = a["start_time"].replace("Z", "+00:00")
        d = datetime.fromisoformat(raw_start).date()
        tss_by_date[d] = tss_by_date.get(d, 0.0) + tss

    n_days = (today - start).days + 1
    if is_cold_start(tss_by_date):
        # Cold start (issue #134): the profile estimate is TODAY's form, shared
        # with the planner via cold_start_state. Materialize it as a flat
        # baseline — simulating 180 days of decay from a fabricated seed is
        # exactly the bug this replaces (CTL≈0 in the app vs full estimate in
        # the plan). daily_tss still reflects the real (sparse) activities.
        states = [cold_start_state(profile.get("hours_per_week"))] * n_days
    else:
        states = compute_banister_history(
            tss_by_date=tss_by_date,
            start=start,
            end=today,
            initial_ctl=0.0,
            initial_atl=0.0,
        )

    rows: list[dict[str, Any]] = []
    for i, s in enumerate(states):
        current = start + timedelta(days=i)
        rows.append(
            {
                "user_id": user_id,
                "date": current.isoformat(),
                "ctl": round(s.ctl, 2),
                "atl": round(s.atl, 2),
                "tsb": round(s.tsb, 2),
                "daily_tss": tss_by_date.get(current),
            }
        )

    if rows:
        db.table("daily_banister_state").upsert(rows, on_conflict="user_id,date").execute()

    return {"rows_upserted": len(rows)}
