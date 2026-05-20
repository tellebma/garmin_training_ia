"""Plan orchestrator : reads profile + race_goal + activities, computes Banister
state, derives phases + sessions, writes to DB.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, cast

from garmin_sync.coach.banister import (
    BanisterState,
    compute_banister_history,
    estimate_initial_ctl_from_profile,
)
from garmin_sync.coach.phases import Phase, compute_phases
from garmin_sync.coach.tss import compute_tss
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

# Ramp rates by phase / week index
NORMAL_RAMP_RATE = 1.05  # +5% per week (normal weeks)
DELOAD_RAMP_RATE = 0.70  # -30% deload week (every 4th week)
TAPER_RAMP_RATE = 0.55  # -45% taper

DAY_NAME_TO_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def distribute_weekly_tss_by_sport(
    *,
    weekly_tss: float,
    sports_in_race: list[str],
    sports_strengths: dict[str, int],
) -> dict[str, float]:
    """Distribute weekly TSS target between sports.

    Weak sport (score 1-2) -> +20% relative share.
    Strong sport (score 4-5) -> -10% relative share.
    Normalised so the sum equals weekly_tss.
    """
    weights: dict[str, float] = {}
    for s in sports_in_race:
        score = sports_strengths.get(s, 3)
        if score <= 2:
            weights[s] = 1.20
        elif score >= 4:
            weights[s] = 0.90
        else:
            weights[s] = 1.0
    total_w = sum(weights.values())
    return {s: round(weekly_tss * w / total_w, 2) for s, w in weights.items()}


def pick_session_types_for_phase(phase: Phase) -> list[str]:
    """Return the canonical set of session types for a given phase."""
    if phase == "base":
        return ["endurance", "long", "recovery"]
    if phase == "build":
        return ["endurance", "threshold", "long"]
    if phase == "peak":
        return ["intervals", "endurance", "long"]
    # taper
    return ["endurance", "recovery"]


def _ramp_rate_for_week(week_offset: int, phase: Phase) -> float:
    """Ramp rate for a given week. Deload every 4th week (1-indexed)."""
    if phase == "taper":
        return TAPER_RAMP_RATE
    if (week_offset + 1) % 4 == 0:
        return DELOAD_RAMP_RATE
    return NORMAL_RAMP_RATE


def _placement_priority_for_day(day_idx: int) -> int:
    """Sunday (=6) gets long sessions; Mon/Thu (=0,3) get recovery; rest = mid-week."""
    if day_idx == 6:
        return 0  # long
    if day_idx in (0, 3):
        return 2  # recovery
    return 1


def _race_day_session(*, day: date, race_sport: str, week_offset: int) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        "sport": race_sport,
        "session_type": "race",
        "target_duration_s": None,
        "target_tss": None,
        "phase": "race",
        "week_offset": week_offset,
    }


def _rest_day_session(*, day: date, phase: Phase, week_offset: int) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        "sport": "rest",
        "session_type": "rest",
        "target_duration_s": 0,
        "target_tss": 0,
        "phase": phase,
        "week_offset": week_offset,
    }


_HARD_SESSION_TYPES = {"threshold", "intervals"}
_LONG_RECOVERY_TYPES = {"long", "recovery"}


def _pick_session_type(
    *,
    day_idx: int,
    types_for_phase: list[str],
    used_types: list[str],
) -> str:
    """Pick a session type respecting priority slots and avoiding back-to-back hard sessions."""
    priority = _placement_priority_for_day(day_idx)
    if priority == 0 and "long" in types_for_phase:
        return "long"
    if priority == 2 and "recovery" in types_for_phase:
        return "recovery"

    candidates = [t for t in types_for_phase if t not in _LONG_RECOVERY_TYPES]
    last = used_types[-1] if used_types else None
    if last in _HARD_SESSION_TYPES:
        candidates = [t for t in candidates if t not in _HARD_SESSION_TYPES]
    if not candidates:
        return "endurance"
    return candidates[len(used_types) % len(candidates)]


def _training_day_session(
    *,
    day: date,
    day_idx: int,
    phase: Phase,
    week_offset: int,
    types_for_phase: list[str],
    sports_in_race: list[str],
    tss_by_sport: dict[str, float],
    used_types: list[str],
    available_idx: set[int],
) -> dict[str, Any]:
    stype = _pick_session_type(
        day_idx=day_idx, types_for_phase=types_for_phase, used_types=used_types
    )
    used_types.append(stype)
    sport = sports_in_race[day_idx % len(sports_in_race)] if sports_in_race else "run"
    per_day_tss = tss_by_sport.get(sport, 0) / max(1, len(available_idx))
    duration_s = int(per_day_tss * 3600 / 50)
    return {
        "date": day.isoformat(),
        "sport": sport,
        "session_type": stype,
        "target_duration_s": duration_s,
        "target_tss": round(per_day_tss, 2),
        "phase": phase,
        "week_offset": week_offset,
    }


def _build_week_sessions(
    *,
    week_offset: int,
    phase: Phase,
    week_start: date,
    weekly_tss: float,
    sports_in_race: list[str],
    sports_strengths: dict[str, int],
    available_days: list[str],
    is_last_week: bool,
    race_date: date,
    race_sport: str,
) -> list[dict[str, Any]]:
    """Generate one week's planned sessions."""
    sessions: list[dict[str, Any]] = []
    types_for_phase = pick_session_types_for_phase(phase)
    tss_by_sport = distribute_weekly_tss_by_sport(
        weekly_tss=weekly_tss, sports_in_race=sports_in_race, sports_strengths=sports_strengths
    )
    available_idx = {DAY_NAME_TO_INDEX[d] for d in available_days if d in DAY_NAME_TO_INDEX}
    used_types: list[str] = []

    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_idx = day.weekday()

        if is_last_week and day == race_date:
            sessions.append(
                _race_day_session(day=day, race_sport=race_sport, week_offset=week_offset)
            )
            continue
        if day_idx not in available_idx:
            sessions.append(_rest_day_session(day=day, phase=phase, week_offset=week_offset))
            continue

        sessions.append(
            _training_day_session(
                day=day,
                day_idx=day_idx,
                phase=phase,
                week_offset=week_offset,
                types_for_phase=types_for_phase,
                sports_in_race=sports_in_race,
                tss_by_sport=tss_by_sport,
                used_types=used_types,
                available_idx=available_idx,
            )
        )
    return sessions


def generate_plan(user_id: str) -> dict[str, Any]:
    """Generate a training plan for the given user.

    Returns:
        {"status": "ok", "plan_id": str, "weeks_count": int, "sessions_count": int}
        {"status": "no_race_goal"} if user has no active race
        {"status": "no_profile"} if profile not found
        {"status": "race_in_past"} if race_date already past
    """
    db = get_admin_client()

    profile = cast(
        "dict[str, Any] | None",
        db.table("athlete_profiles")
        .select("user_id, hours_per_week, ftp_watts, fc_max_bpm, sports_strengths, available_days")
        .eq("user_id", user_id)
        .single()
        .execute()
        .data,
    )
    if not profile:
        return {"status": "no_profile"}

    _race_builder = (
        db.table("race_goals")
        .select("id, race_date, discipline, legs")
        .eq("user_id", user_id)
        .eq("is_primary", True)
        .maybe_single()
    )
    _race_executed = _race_builder.execute()
    race = cast("dict[str, Any] | None", _race_executed.data)  # type: ignore[union-attr]
    if not race:
        return {"status": "no_race_goal"}

    today = date.today()
    race_date = date.fromisoformat(race["race_date"])
    if race_date <= today:
        return {"status": "race_in_past"}

    # Load last 180 days of activities and compute per-day TSS
    history_start = today - timedelta(days=180)
    activities = cast(
        "list[dict[str, Any]]",
        db.table("activities")
        .select("start_time, sport, duration_s, power_avg, hr_avg")
        .eq("user_id", user_id)
        .gte("start_time", history_start.isoformat())
        .execute()
        .data
        or [],
    )

    tss_by_date: dict[date, float] = {}
    for a in activities:
        tss = compute_tss(
            duration_s=a.get("duration_s", 0),
            sport=a.get("sport", ""),
            power_avg=a.get("power_avg"),
            hr_avg=a.get("hr_avg"),
            ftp_watts=profile.get("ftp_watts"),
            fc_max_bpm=profile.get("fc_max_bpm"),
        )
        if tss is None:
            continue
        start_time_raw = a["start_time"].replace("Z", "+00:00")
        d = datetime.fromisoformat(start_time_raw).date()
        tss_by_date[d] = tss_by_date.get(d, 0.0) + tss

    # Cold start if < 14 days of activities
    if len(tss_by_date) < 14:
        init_ctl = estimate_initial_ctl_from_profile(profile.get("hours_per_week"))
        init_atl = init_ctl
    else:
        init_ctl = 0.0
        init_atl = 0.0

    states = compute_banister_history(
        tss_by_date=tss_by_date,
        start=history_start,
        end=today,
        initial_ctl=init_ctl,
        initial_atl=init_atl,
    )
    today_state: BanisterState = states[-1]

    # Compute phases and per-week sessions
    phases = compute_phases(today, race_date)
    weeks_count = len(phases)
    sports_in_race = [leg["discipline"] for leg in race["legs"]]
    race_sport = race["legs"][0]["discipline"] if race["legs"] else "run"
    sports_strengths = profile.get("sports_strengths") or {"swim": 3, "bike": 3, "run": 3}
    available_days = profile.get("available_days") or ["mon", "wed", "fri"]

    week_start = today - timedelta(days=today.weekday())

    all_sessions: list[dict[str, Any]] = []
    for offset, phase in phases:
        ramp = _ramp_rate_for_week(offset, phase)
        weekly_tss = today_state.ctl * 7 * ramp
        is_last = offset == weeks_count - 1
        sessions = _build_week_sessions(
            week_offset=offset,
            phase=phase,
            week_start=week_start + timedelta(weeks=offset),
            weekly_tss=weekly_tss,
            sports_in_race=sports_in_race,
            sports_strengths=sports_strengths,
            available_days=available_days,
            is_last_week=is_last,
            race_date=race_date,
            race_sport=race_sport,
        )
        all_sessions.extend(sessions)

    # Archive previous active plan
    db.table("training_plans").update({"status": "archived"}).eq("user_id", user_id).eq(
        "race_goal_id", race["id"]
    ).execute()

    # Insert new plan
    insert_resp = (
        db.table("training_plans")
        .insert(
            {
                "user_id": user_id,
                "race_goal_id": race["id"],
                "start_date": today.isoformat(),
                "end_date": race_date.isoformat(),
                "weeks_count": weeks_count,
                "ctl_initial": round(today_state.ctl, 2),
                "atl_initial": round(today_state.atl, 2),
                "tsb_initial": round(today_state.tsb, 2),
                "status": "active",
                "params": {"cold_start": len(tss_by_date) < 14},
            }
        )
        .execute()
    )
    plan_id = cast("list[dict[str, Any]]", insert_resp.data)[0]["id"]

    for s in all_sessions:
        s["plan_id"] = plan_id
        s["user_id"] = user_id
    if all_sessions:
        db.table("planned_sessions").insert(all_sessions).execute()

    return {
        "status": "ok",
        "plan_id": plan_id,
        "weeks_count": weeks_count,
        "sessions_count": len(all_sessions),
    }
