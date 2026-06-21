"""Plan orchestrator : reads profile + race_goal + activities, computes Banister
state, derives phases + sessions, writes to DB.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, cast

from garmin_sync.coach.activity_review import ActivityReview, build_activity_review
from garmin_sync.coach.banister import (
    BanisterState,
    compute_banister_history,
    estimate_initial_ctl_from_profile,
)
from garmin_sync.coach.phases import Phase, compute_phases
from garmin_sync.coach.tss import compute_tss
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

DbRows = list[dict[str, Any]]

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

    Niveau par discipline (1-5) module la part : faible (1) ~+25%, fort (5) ~-15%,
    interpolation linéaire. Normalisé pour que la somme égale weekly_tss.
    """
    weights: dict[str, float] = {}
    for s in sports_in_race:
        score = sports_strengths.get(s, 3)
        # modulation continue : niveau 1 -> 1.25, niveau 3 -> 1.0, niveau 5 -> 0.85.
        weights[s] = 1.25 - (score - 1) * 0.10
    total_w = sum(weights.values())
    return {s: round(weekly_tss * w / total_w, 2) for s, w in weights.items()}


_HARD_TYPES_BY_LEVEL: dict[int, set[str]] = {
    1: set(),
    2: set(),
    3: {"threshold"},
    4: {"threshold", "intervals"},
    5: {"threshold", "intervals"},
}


def pick_session_types_for_phase(phase: Phase, *, max_level: int = 5) -> list[str]:
    """Return the canonical set of session types for a given phase.

    `max_level` (1-5) borne l'intensité : un niveau faible retire les types durs
    (threshold/intervals) au profit d'endurance/recovery.
    """
    if phase == "base":
        base = ["endurance", "long", "recovery"]
    elif phase == "build":
        base = ["endurance", "threshold", "long"]
    elif phase == "peak":
        base = ["intervals", "endurance", "long"]
    else:  # taper
        base = ["endurance", "recovery"]

    allowed_hard = _HARD_TYPES_BY_LEVEL.get(max_level, {"threshold", "intervals"})
    filtered = [t for t in base if t not in {"threshold", "intervals"} or t in allowed_hard]
    return filtered or ["endurance"]


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
        "target_elevation_gain_m": None,
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
        "target_elevation_gain_m": None,
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


# Relative TSS weights by session type. "long" gets ~50% more, "recovery"
# half, etc. — keeps the weekly TSS budget but redistributes within each sport.
_SESSION_TYPE_WEIGHT: dict[str, float] = {
    "long": 1.5,
    "threshold": 1.2,
    "intervals": 1.2,
    "endurance": 1.0,
    "recovery": 0.5,
}


# Average TSS/hour per (sport, session_type). Drives the TSS -> duration mapping.
# Same TSS budget produces different durations across sports because the
# physiological load per unit time differs (bike low cadence Z2 vs run Z2).
# Reference points (sport scientists, TR/TP heuristics):
#   - Bike Z2 endurance: IF ~0.65-0.70 -> TSS/h ~ 42-49
#   - Run Z2 endurance:  rTSS ~50-60
#   - Swim Z2:           sTSS ~55-65 (skill-limited)
#   - Intervals/threshold: IF 0.85-0.95+ -> 75-95 TSS/h
_TSS_PER_HOUR: dict[tuple[str, str], float] = {
    ("bike", "endurance"): 40.0,
    ("bike", "long"): 45.0,
    ("bike", "threshold"): 72.0,
    ("bike", "intervals"): 82.0,
    ("bike", "recovery"): 22.0,
    ("run", "endurance"): 48.0,
    ("run", "long"): 52.0,
    ("run", "threshold"): 75.0,
    ("run", "intervals"): 90.0,
    ("run", "recovery"): 30.0,
    ("swim", "endurance"): 50.0,
    ("swim", "long"): 55.0,
    ("swim", "threshold"): 72.0,
    ("swim", "intervals"): 85.0,
    ("swim", "recovery"): 35.0,
    ("brick", "endurance"): 65.0,
    ("brick", "long"): 65.0,
}
_TSS_PER_HOUR_DEFAULT = 50.0


def _tss_per_hour(sport: str, stype: str) -> float:
    return _TSS_PER_HOUR.get((sport, stype), _TSS_PER_HOUR_DEFAULT)


# TSS/h moyen pondéré d'une semaine type (Z2 dominant) pour ancrer le volume
# sur les heures déclarées, indépendamment du CTL lissé.
_AVG_WEEKLY_TSS_PER_HOUR = 45.0


def weekly_tss_floor_from_hours(hours_per_week: float | None) -> int:
    """Volume hebdo plancher dérivé des heures déclarées (avant ramp)."""
    if not hours_per_week:
        return 0
    return round(hours_per_week * _AVG_WEEKLY_TSS_PER_HOUR)


# Minimum per-sport race elevation gain (m) below which we don't bother training
# hills. A 50m run race or a 200m bike race is flat enough that "spécificité
# terrain" doesn't justify dedicated hill sessions.
_ELEVATION_THRESHOLD_M: dict[str, int] = {
    "bike": 300,
    "run": 100,
    "swim": 1_000_000,  # never
    "brick": 200,
}

# Per-session weight for distributing the weekly elevation target. Long absorbs
# most of the D+, intervals/recovery zero (intervals are typically track-based).
_ELEVATION_SESSION_WEIGHT: dict[str, float] = {
    "long": 2.0,
    "endurance": 1.0,
    "threshold": 0.3,
    "intervals": 0.0,
    "recovery": 0.0,
    "race": 1.0,
    "rest": 0.0,
}

_FIRST_WEEK_STRONG_DELOAD_SIGNALS = {"return_after_break", "load_spike", "hard_sessions_density"}
_FIRST_WEEK_LIGHT_DELOAD_SIGNALS = {"recent_long_session", "elevation_spike"}


def compute_first_week_tss_multiplier(activity_review: ActivityReview) -> float:
    """Return a conservative first-week TSS multiplier from recent coach signals."""
    names = {insight.name for insight in activity_review.insights}
    if names & _FIRST_WEEK_STRONG_DELOAD_SIGNALS:
        return 0.85
    if names & _FIRST_WEEK_LIGHT_DELOAD_SIGNALS:
        return 0.92
    return 1.0


def compute_elevation_per_sport(legs: list[dict[str, Any]]) -> dict[str, int]:
    """Sum the race's total D+ per sport from its legs.

    Returns a {sport: meters} map. Sports missing from legs default to 0.
    """
    by_sport: dict[str, int] = {}
    for leg in legs:
        sport = leg.get("discipline", "unknown")
        gain = int(leg.get("elevation_gain_m") or 0)
        by_sport[sport] = by_sport.get(sport, 0) + gain
    return by_sport


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
    sport_weight_total: dict[str, float],
    weekly_elevation_by_sport: dict[str, int],
    sport_elevation_weight_total: dict[str, float],
) -> dict[str, Any]:
    """Build one training day's session.

    Per-day TSS = sport_tss * (this_session_weight / sum_of_session_weights_for_this_sport).
    This keeps the weekly TSS budget intact while letting "long" sessions get more
    volume than e.g. "recovery".

    target_elevation_gain_m is populated only when the sport has a meaningful
    weekly D+ target (set by the caller via weekly_elevation_by_sport). Same
    redistribution scheme as TSS, but with a separate weight table (long heavy,
    intervals zero — intervals are typically track-based).
    """
    stype = _pick_session_type(
        day_idx=day_idx, types_for_phase=types_for_phase, used_types=used_types
    )
    used_types.append(stype)
    sport = sports_in_race[day_idx % len(sports_in_race)] if sports_in_race else "run"
    sport_tss = tss_by_sport.get(sport, 0)
    weight = _SESSION_TYPE_WEIGHT.get(stype, 1.0)
    total_weight = max(0.5, sport_weight_total.get(sport, 1.0))
    per_day_tss = sport_tss * weight / total_weight
    duration_s = int(per_day_tss * 3600 / _tss_per_hour(sport, stype))

    target_elevation: int | None = None
    weekly_dplus = weekly_elevation_by_sport.get(sport, 0)
    if weekly_dplus > 0:
        elev_weight = _ELEVATION_SESSION_WEIGHT.get(stype, 0.0)
        elev_total = max(0.5, sport_elevation_weight_total.get(sport, 1.0))
        if elev_weight > 0:
            target_elevation = round(weekly_dplus * elev_weight / elev_total)

    return {
        "date": day.isoformat(),
        "sport": sport,
        "session_type": stype,
        "target_duration_s": duration_s,
        "target_tss": round(per_day_tss, 2),
        "target_elevation_gain_m": target_elevation,
        "phase": phase,
        "week_offset": week_offset,
    }


def _precompute_sport_weights(
    *,
    week_start: date,
    available_idx: set[int],
    sports_in_race: list[str],
    types_for_phase: list[str],
    is_last_week: bool,
    race_date: date,
) -> dict[str, float]:
    """Walk the upcoming 7 days once to tally each sport's total session weight.

    Mirrors the assignment logic in _build_week_sessions / _pick_session_type
    so the TSS distribution in _training_day_session sums back to sport_tss.
    """
    sport_weight: dict[str, float] = dict.fromkeys(sports_in_race, 0.0)
    used_types: list[str] = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_idx = day.weekday()
        if is_last_week and day == race_date:
            continue
        if day_idx not in available_idx:
            continue
        stype = _pick_session_type(
            day_idx=day_idx, types_for_phase=types_for_phase, used_types=used_types
        )
        used_types.append(stype)
        sport = sports_in_race[day_idx % len(sports_in_race)] if sports_in_race else "run"
        sport_weight[sport] = sport_weight.get(sport, 0.0) + _SESSION_TYPE_WEIGHT.get(stype, 1.0)
    return sport_weight


def _precompute_elevation_weights(
    *,
    week_start: date,
    available_idx: set[int],
    sports_in_race: list[str],
    types_for_phase: list[str],
    is_last_week: bool,
    race_date: date,
) -> dict[str, float]:
    """Tally elevation-weight per sport for the week, using _ELEVATION_SESSION_WEIGHT."""
    sport_weight: dict[str, float] = dict.fromkeys(sports_in_race, 0.0)
    used_types: list[str] = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_idx = day.weekday()
        if is_last_week and day == race_date:
            continue
        if day_idx not in available_idx:
            continue
        stype = _pick_session_type(
            day_idx=day_idx, types_for_phase=types_for_phase, used_types=used_types
        )
        used_types.append(stype)
        sport = sports_in_race[day_idx % len(sports_in_race)] if sports_in_race else "run"
        sport_weight[sport] = sport_weight.get(sport, 0.0) + _ELEVATION_SESSION_WEIGHT.get(
            stype, 0.0
        )
    return sport_weight


def compute_weekly_elevation_targets(
    *, race_dplus_by_sport: dict[str, int], weeks_count: int
) -> dict[str, int]:
    """Spread the race's total D+ across the plan, gated by per-sport thresholds.

    Sports whose race D+ is below _ELEVATION_THRESHOLD_M get a 0 weekly target
    (no hill training needed). Above the threshold, distribute total / weeks.
    """
    if weeks_count <= 0:
        return {}
    out: dict[str, int] = {}
    for sport, total in race_dplus_by_sport.items():
        threshold = _ELEVATION_THRESHOLD_M.get(sport, 200)
        if total >= threshold:
            out[sport] = total // weeks_count
        else:
            out[sport] = 0
    return out


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
    weekly_elevation_by_sport: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Generate one week's planned sessions."""
    weekly_elevation_by_sport = weekly_elevation_by_sport or {}
    sessions: list[dict[str, Any]] = []
    types_for_phase = pick_session_types_for_phase(phase)
    tss_by_sport = distribute_weekly_tss_by_sport(
        weekly_tss=weekly_tss, sports_in_race=sports_in_race, sports_strengths=sports_strengths
    )
    available_idx = {DAY_NAME_TO_INDEX[d] for d in available_days if d in DAY_NAME_TO_INDEX}

    # First pass: tally total session-type weight per sport so the second pass
    # can divide each sport's TSS budget proportionally (long > endurance > recovery).
    sport_weight_total = _precompute_sport_weights(
        week_start=week_start,
        available_idx=available_idx,
        sports_in_race=sports_in_race,
        types_for_phase=types_for_phase,
        is_last_week=is_last_week,
        race_date=race_date,
    )
    # Same idea for elevation, but a different per-type weight table.
    sport_elev_weight_total = _precompute_elevation_weights(
        week_start=week_start,
        available_idx=available_idx,
        sports_in_race=sports_in_race,
        types_for_phase=types_for_phase,
        is_last_week=is_last_week,
        race_date=race_date,
    )
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
                sport_weight_total=sport_weight_total,
                weekly_elevation_by_sport=weekly_elevation_by_sport,
                sport_elevation_weight_total=sport_elev_weight_total,
            )
        )
    return sessions


def _compute_tss_by_date(
    activities: list[dict[str, Any]], profile: dict[str, Any]
) -> dict[date, float]:
    """Aggregate per-day TSS from a list of activity rows."""
    tss_by_date: dict[date, float] = {}
    ftp = profile.get("ftp_watts")
    fc_max = profile.get("fc_max_bpm")
    for a in activities:
        tss = compute_tss(
            duration_s=a.get("duration_s", 0),
            sport=a.get("sport", ""),
            power_avg=a.get("power_avg"),
            hr_avg=a.get("hr_avg"),
            ftp_watts=ftp,
            fc_max_bpm=fc_max,
        )
        if tss is None:
            continue
        start_time_raw = a["start_time"].replace("Z", "+00:00")
        d = datetime.fromisoformat(start_time_raw).date()
        tss_by_date[d] = tss_by_date.get(d, 0.0) + tss
    return tss_by_date


def _load_today_banister_state(
    *, db: Any, user_id: str, profile: dict[str, Any], today: date
) -> tuple[dict[date, float], BanisterState, ActivityReview]:
    """Load last 180 days of activities, derive tss_by_date and today's CTL/ATL/TSB.

    Cold-start (<14 days of activities): skip the 180-day decay simulation and
    use the profile estimate AS today's state directly. See cold-start regression
    test for the rationale.
    """
    history_start = today - timedelta(days=180)
    activities = cast(
        DbRows,
        db.table("activities")
        .select("start_time, sport, duration_s, power_avg, hr_avg, tss, elevation_gain_m")
        .eq("user_id", user_id)
        .gte("start_time", history_start.isoformat())
        .execute()
        .data
        or [],
    )
    tss_by_date = _compute_tss_by_date(activities, profile)
    activity_review = build_activity_review(activities, today=today)

    if len(tss_by_date) < 14:
        init_ctl = estimate_initial_ctl_from_profile(profile.get("hours_per_week"))
        return tss_by_date, BanisterState(ctl=init_ctl, atl=init_ctl, tsb=0.0), activity_review

    states = compute_banister_history(
        tss_by_date=tss_by_date,
        start=history_start,
        end=today,
        initial_ctl=0.0,
        initial_atl=0.0,
    )
    return tss_by_date, states[-1], activity_review


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

    tss_by_date, today_state, activity_review = _load_today_banister_state(
        db=db, user_id=user_id, profile=profile, today=today
    )
    first_week_tss_multiplier = compute_first_week_tss_multiplier(activity_review)

    # Compute phases and per-week sessions
    phases = compute_phases(today, race_date)
    weeks_count = len(phases)
    sports_in_race = [leg["discipline"] for leg in race["legs"]]
    race_sport = race["legs"][0]["discipline"] if race["legs"] else "run"
    sports_strengths = profile.get("sports_strengths") or {"swim": 3, "bike": 3, "run": 3}
    available_days = profile.get("available_days") or ["mon", "wed", "fri"]

    # Per-sport race D+ -> per-week target D+, gated by the sport's threshold.
    race_dplus_by_sport = compute_elevation_per_sport(race.get("legs") or [])
    weekly_elevation_by_sport = compute_weekly_elevation_targets(
        race_dplus_by_sport=race_dplus_by_sport, weeks_count=weeks_count
    )

    week_start = today - timedelta(days=today.weekday())

    all_sessions: list[dict[str, Any]] = []
    for offset, phase in phases:
        ramp = _ramp_rate_for_week(offset, phase)
        base_weekly = max(
            today_state.ctl * 7, weekly_tss_floor_from_hours(profile.get("hours_per_week"))
        )
        weekly_tss = base_weekly * ramp
        if offset == 0:
            weekly_tss *= first_week_tss_multiplier
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
            weekly_elevation_by_sport=weekly_elevation_by_sport,
        )
        all_sessions.extend(sessions)

    # Archive previous plans for this race and delete their planned_sessions
    # (FK has no ON DELETE CASCADE; without this, sessions of archived plans
    # remain in planned_sessions and create duplicates on /today queries).
    previous_plans_resp = (
        db.table("training_plans")
        .select("id")
        .eq("user_id", user_id)
        .eq("race_goal_id", race["id"])
        .execute()
    )
    previous_plan_ids = [p["id"] for p in cast(DbRows, previous_plans_resp.data or [])]
    if previous_plan_ids:
        db.table("planned_sessions").delete().in_("plan_id", previous_plan_ids).execute()
        db.table("training_plans").update({"status": "archived"}).in_(
            "id", previous_plan_ids
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
                "params": {
                    "cold_start": len(tss_by_date) < 14,
                    "first_week_tss_multiplier": first_week_tss_multiplier,
                    "activity_review_signals": [i.name for i in activity_review.insights],
                },
            }
        )
        .execute()
    )
    plan_id = cast(DbRows, insert_resp.data)[0]["id"]

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
