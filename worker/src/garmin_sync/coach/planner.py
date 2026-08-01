"""Plan orchestrator : reads profile + race_goal + activities, computes Banister
state, derives phases + sessions, writes to DB.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any, cast

from garmin_sync.coach.activity_review import ActivityReview, build_activity_review
from garmin_sync.coach.banister import (
    BanisterState,
    compute_banister_history,
    estimate_initial_ctl_from_profile,
)
from garmin_sync.coach.discipline_level import load_effective_strengths
from garmin_sync.coach.duration_bounds import clamp_duration_to_bounds
from garmin_sync.coach.phases import Phase, compute_phases
from garmin_sync.coach.training_days import (
    assign_sports,
    athlete_level,
    long_session_day,
    select_training_days,
    training_days_count,
)
from garmin_sync.coach.tss import compute_tss
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

DbRows = list[dict[str, Any]]

# Ramp rates by phase / week index
NORMAL_RAMP_RATE = 1.05  # +5% per week (normal weeks)
DELOAD_RAMP_RATE = 0.70  # -30% deload week (every 4th week)
TAPER_RAMP_RATE = 0.55  # -45% taper

# Weekly ramp cap per sport (guardrail against overload)
WEEKLY_RAMP_CAP: dict[str, float] = {"run": 1.10, "swim": 1.15, "bike": 1.20}

DAY_NAME_TO_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def distribute_weekly_tss_by_sport(
    *,
    weekly_tss: float,
    sports_in_race: list[str],
    sports_strengths: dict[str, int],
    progress: float = 1.0,
) -> dict[str, float]:
    """Distribue le TSS hebdo entre sports selon le niveau par discipline.

    Niveau (1-5) module la part : faible (1) ~+25 %, fort (5) ~-15 % à biais plein.
    ``progress`` (0..1) module l'amplitude du biais via ``bias_curve`` : ~moitié du
    biais en début de plan, plein en fin de build. Normalisé (somme = weekly_tss).
    """
    p = min(1.0, max(0.0, progress))
    bias = 0.5 + 0.5 * p
    weights: dict[str, float] = {}
    for s in sports_in_race:
        score = sports_strengths.get(s, 3)
        boost = 0.25 - (score - 1) * 0.10  # niveau 1 -> +0.25, 3 -> 0, 5 -> -0.15
        weights[s] = 1.0 + boost * bias
    total_w = sum(weights.values())
    return {s: round(weekly_tss * w / total_w, 2) for s, w in weights.items()}


_HARD_TYPES_BY_LEVEL: dict[int, set[str]] = {
    1: set(),
    2: set(),
    3: {"threshold", "sprint"},
    4: {"threshold", "sprint", "pma"},
    5: {"threshold", "sprint", "pma"},
}

# Types dont l'accès dépend du niveau athlète (filtrés par _HARD_TYPES_BY_LEVEL).
# "intervals" reste dans le schéma/caps pour compatibilité (séances déjà en DB) mais
# n'apparaît plus dans aucune liste `base` ci-dessous — gardé ici uniquement pour ne
# jamais le laisser passer si une future liste `base` le réintroduit par erreur.
_FILTERABLE_HARD_TYPES = {"threshold", "intervals", "sprint", "pma"}


def pick_session_types_for_phase(
    phase: Phase, *, max_level: int = 5, progress: float = 1.0
) -> list[str]:
    """Return the canonical set of session types for a given phase.

    `max_level` (1-5) borne l'intensité : un niveau faible retire les types durs
    (threshold/pma/sprint) au profit d'endurance/recovery.

    `progress` (0..1, cf. `_progress_for_offset`) gate `pma` à la 2e moitié de la
    phase build (progress >= 0.5) — trop tôt dans le plan, pma n'apparaît pas
    encore. Par défaut 1.0 pour rester rétro-compatible avec les appels existants.
    """
    if phase == "base":
        base = ["endurance", "long", "recovery"]
    elif phase == "build":
        base = ["endurance", "threshold", "long"]
        if progress >= 0.5:
            base.append("pma")
    elif phase == "peak":
        base = ["pma", "sprint", "endurance", "long"]
    else:  # taper
        base = ["endurance", "recovery", "sprint"]

    allowed_hard = _HARD_TYPES_BY_LEVEL.get(max_level, {"threshold", "sprint", "pma"})
    filtered = [t for t in base if t not in _FILTERABLE_HARD_TYPES or t in allowed_hard]
    return filtered or ["endurance"]


def compute_week_load_multipliers(phases: Sequence[tuple[int, Phase]]) -> list[float]:
    """Cumulative weekly load multiplier per week (compounding +5% ramp).

    Normal build weeks apply the current progression then compound
    ``NORMAL_RAMP_RATE`` for the next week; deload (every 4th week) and taper weeks
    apply their reduction to the current progression WITHOUT advancing it (a
    step-back that resumes the build where it left off).

    Fixes the flat-load bug: previously every normal week got a fixed 1.05x of a
    CONSTANT base_weekly, so weeks 1, 2, 5, 9… were all identical and the only
    "progression" came from CTL drift between weekly regenerations (≈ nil).
    """
    multipliers: list[float] = []
    progression = 1.0
    for offset, phase in phases:
        is_deload = phase != "taper" and (offset + 1) % 4 == 0
        if phase == "taper":
            multipliers.append(round(progression * TAPER_RAMP_RATE, 4))
        elif is_deload:
            multipliers.append(round(progression * DELOAD_RAMP_RATE, 4))
        else:
            multipliers.append(round(progression, 4))
            progression *= NORMAL_RAMP_RATE
    return multipliers


def _progress_for_offset(offset: int, phases: Sequence[tuple[int, str]]) -> float:
    """Avancement 0..1 : 0 au début, 1 à la dernière semaine de build (tenu ensuite)."""
    build_offsets = [o for o, ph in phases if ph == "build"]
    if build_offsets:
        last = max(build_offsets)
    elif phases:
        last = phases[-1][0]
    else:
        last = 0
    return min(1.0, max(0.0, offset / max(1, last)))


def cap_weekly_ramp_by_sport(
    tss_by_sport: dict[str, float],
    prev_tss_by_sport: dict[str, float] | None,
) -> dict[str, float]:
    """Borne la hausse hebdo de TSS par sport (anti-surcharge, surtout course).

    Seules les hausses sont bridées (deload/taper intacts). Sans précédent pour un
    sport, pas de cap. L'excédent n'est pas redistribué (sécurité avant volume).
    """
    if not prev_tss_by_sport:
        return dict(tss_by_sport)
    capped: dict[str, float] = {}
    for sport, tss in tss_by_sport.items():
        prev = prev_tss_by_sport.get(sport)
        if prev is None or prev <= 0:
            capped[sport] = tss
            continue
        ceiling = prev * WEEKLY_RAMP_CAP.get(sport, 1.20)
        capped[sport] = round(min(tss, ceiling), 2)
    return capped


def _placement_priority_for_day(day_idx: int, long_day_idx: int | None = None) -> int:
    """Le jour "longue" est dérivé des jours d'entraînement retenus (#122) ;
    Mon/Thu (=0,3) get recovery; rest = mid-week.

    L'ancien codage en dur `day_idx == 6` (dimanche) ne matchait jamais les jours
    choisis par ``select_training_days`` -> 0 séance longue émise depuis mai.
    """
    if long_day_idx is not None and day_idx == long_day_idx:
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


_HARD_SESSION_TYPES = {"threshold", "intervals", "pma", "sprint"}
_LONG_RECOVERY_TYPES = {"long", "recovery"}


def _pick_session_type(
    *,
    day_idx: int,
    types_for_phase: list[str],
    used_types: list[str],
    long_day_idx: int | None = None,
) -> str:
    """Pick a session type respecting priority slots and avoiding back-to-back hard sessions.

    ``types_for_phase`` est la liste de la DISCIPLINE du jour (plafond d'intensité
    par sport, cf. #121) ; ``used_types`` reste l'historique global de la semaine
    pour éviter deux séances dures d'affilée, tous sports confondus.
    """
    priority = _placement_priority_for_day(day_idx, long_day_idx)
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
    "pma": 1.2,
    "sprint": 0.9,
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
    ("bike", "pma"): 88.0,
    ("bike", "sprint"): 65.0,
    ("bike", "recovery"): 22.0,
    ("run", "endurance"): 48.0,
    ("run", "long"): 52.0,
    ("run", "threshold"): 75.0,
    ("run", "intervals"): 90.0,
    ("run", "pma"): 95.0,
    ("run", "sprint"): 70.0,
    ("run", "recovery"): 30.0,
    ("swim", "endurance"): 50.0,
    ("swim", "long"): 55.0,
    ("swim", "threshold"): 72.0,
    ("swim", "intervals"): 85.0,
    ("swim", "pma"): 88.0,
    ("swim", "sprint"): 68.0,
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
# most of the D+, intervals/recovery zero (pma/sprint are typically track-based;
# intervals is kept only for schema compatibility, no longer emitted).
_ELEVATION_SESSION_WEIGHT: dict[str, float] = {
    "long": 2.0,
    "endurance": 1.0,
    "threshold": 0.3,
    "intervals": 0.0,
    "pma": 0.0,
    "sprint": 0.0,
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
    phase: Phase,
    week_offset: int,
    stype: str,
    sport: str,
    tss_by_sport: dict[str, float],
    sport_weight_total: dict[str, float],
    weekly_elevation_by_sport: dict[str, int],
    sport_elevation_weight_total: dict[str, float],
) -> dict[str, Any]:
    """Build one training day's session.

    Per-day TSS = sport_tss * (this_session_weight / sum_of_session_weights_for_this_sport).
    This keeps the weekly TSS budget intact while letting "long" sessions get more
    volume than e.g. "recovery".

    The session type and sport are decided upstream (single-pass day plan) so the
    weight tallies and the emitted sessions never diverge. Durations are clamped to
    realistic per (sport, type, phase) bounds.

    target_elevation_gain_m is populated only when the sport has a meaningful
    weekly D+ target (set by the caller via weekly_elevation_by_sport). Same
    redistribution scheme as TSS, but with a separate weight table (long heavy,
    intervals zero — intervals are typically track-based).
    """
    sport_tss = tss_by_sport.get(sport, 0)
    weight = _SESSION_TYPE_WEIGHT.get(stype, 1.0)
    total_weight = max(0.5, sport_weight_total.get(sport, 1.0))
    per_day_tss = sport_tss * weight / total_weight
    duration_s = int(per_day_tss * 3600 / _tss_per_hour(sport, stype))
    duration_s = clamp_duration_to_bounds(sport, stype, phase, duration_s)
    # Re-derive the TSS from the (possibly clamped) duration so duration, TSS and
    # intensity stay internally consistent — the LLM prompt and the prévu/réalisé
    # comparisons read target_tss, and a stale pre-clamp value would force the
    # intensity up. Trade-off: the weekly TSS budget is no longer exactly conserved.
    per_day_tss = duration_s / 3600 * _tss_per_hour(sport, stype)

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


def _build_training_day_plan(
    *,
    week_start: date,
    training_idx: set[int],
    sport_by_day: dict[int, str],
    types_by_sport: dict[str, list[str]],
    is_last_week: bool,
    race_date: date,
    long_day_idx: int | None = None,
) -> dict[int, tuple[str, str]]:
    """Single-pass day plan: weekday index -> (sport, session_type).

    Walks the 7 days in order so `_pick_session_type`'s used_types history is
    consistent with the emission loop. Only days selected as training days
    (and not the race day) get an entry. Both the weight tallies and the emitted
    sessions derive from this map, so they can never diverge.

    ``types_by_sport`` porte le plafond d'intensité PAR discipline (#121) : le
    type du jour est tiré de la liste du sport assigné à ce jour — un niveau 1
    en course n'interdit plus le seuil en vélo.
    """
    plan: dict[int, tuple[str, str]] = {}
    used_types: list[str] = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_idx = day.weekday()
        if is_last_week and day == race_date:
            continue
        if day_idx not in training_idx:
            continue
        sport = sport_by_day.get(day_idx, "run")
        stype = _pick_session_type(
            day_idx=day_idx,
            types_for_phase=types_by_sport.get(sport, ["endurance"]),
            used_types=used_types,
            long_day_idx=long_day_idx,
        )
        used_types.append(stype)
        plan[day_idx] = (sport, stype)
    return plan


def _tally_sport_weights(
    plan: dict[int, tuple[str, str]], weight_table: dict[str, float]
) -> dict[str, float]:
    """Sum a per-session-type weight per sport over the day plan."""
    totals: dict[str, float] = {}
    for sport, stype in plan.values():
        totals[sport] = totals.get(sport, 0.0) + weight_table.get(stype, 0.0)
    return totals


# Plancher de dénominateur pour la répartition du D+. Sans lui, la cible hebdo
# explose à mesure que l'horizon rétrécit (le plan est régénéré chaque semaine) :
# 2000 m donnaient 166 m/sem à 12 semaines, 500 m à 4, 1000 m à 2 — soit l'inverse
# d'une périodisation, avec du gros dénivelé juste avant la course.
_MIN_ELEVATION_SPREAD_WEEKS = 4

# Le D+ suit la phase : on accumule en build/peak, on lève le pied en base, et on
# réduit fortement en taper (bug prod : 500 m ciblés en pleine semaine de taper).
_ELEVATION_PHASE_FACTOR: dict[str, float] = {
    "base": 0.7,
    "build": 1.0,
    "peak": 1.0,
    "taper": 0.3,
}


def compute_weekly_elevation_targets(
    *, race_dplus_by_sport: dict[str, int], weeks_count: int, phase: str = "build"
) -> dict[str, int]:
    """Weekly D+ target per sport, gated by per-sport thresholds.

    Sports whose race D+ is below ``_ELEVATION_THRESHOLD_M`` get a 0 weekly target
    (no hill training needed). Above it, the race's total D+ is spread over the
    plan — but the denominator is floored at ``_MIN_ELEVATION_SPREAD_WEEKS`` so a
    shrinking horizon can't inflate the target, and scaled by the week's phase so
    the taper actually tapers.
    """
    if weeks_count <= 0:
        return {}
    spread = max(weeks_count, _MIN_ELEVATION_SPREAD_WEEKS)
    factor = _ELEVATION_PHASE_FACTOR.get(phase, 1.0)
    out: dict[str, int] = {}
    for sport, total in race_dplus_by_sport.items():
        threshold = _ELEVATION_THRESHOLD_M.get(sport, 200)
        out[sport] = round(total * factor / spread) if total >= threshold else 0
    return out


def _build_week_sessions(
    *,
    week_offset: int,
    phase: Phase,
    week_start: date,
    sports_in_race: list[str],
    sports_strengths: dict[str, int],
    tss_by_sport: dict[str, float],
    available_days: list[str],
    hours_per_week: float | None,
    is_last_week: bool,
    race_date: date,
    race_sport: str,
    weekly_elevation_by_sport: dict[str, int] | None = None,
    progress: float = 1.0,
) -> list[dict[str, Any]]:
    """Generate one week's planned sessions.

    ``available_days`` is treated as a MASK of possible windows: the effective
    number of training days is capped by volume/level/rest-floor
    (``training_days_count``), the chosen days are spread out
    (``select_training_days``), a sport is assigned per day (``assign_sports``:
    run cap, no back-to-back run), and the resulting day plan drives both the
    weight tallies and the emitted sessions in a single pass.
    """
    weekly_elevation_by_sport = weekly_elevation_by_sport or {}
    sessions: list[dict[str, Any]] = []

    level = athlete_level(sports_strengths)
    # Plafond d'intensité PAR discipline (#121) : le min global verrouillait
    # l'intensité de TOUS les sports sur la discipline la plus faible.
    types_by_sport = {
        s: pick_session_types_for_phase(
            phase, max_level=sports_strengths.get(s, 3), progress=progress
        )
        for s in sports_in_race
    }
    available_idx = {DAY_NAME_TO_INDEX[d] for d in available_days if d in DAY_NAME_TO_INDEX}

    # Deload weeks (every 4th, except taper) need a stricter rest floor.
    is_deload = (week_offset + 1) % 4 == 0
    phase_for_rest = "deload" if is_deload and phase != "taper" else phase
    count = training_days_count(
        n_available=len(available_idx), hours=hours_per_week, level=level, phase=phase_for_rest
    )
    training_idx = select_training_days(available_idx=available_idx, count=count)
    sport_by_day = assign_sports(
        training_idx=sorted(training_idx), sports_in_race=sports_in_race, level=level
    )

    # Single-pass day plan so weight tallies and emitted sessions never diverge.
    day_plan = _build_training_day_plan(
        week_start=week_start,
        training_idx=training_idx,
        sport_by_day=sport_by_day,
        types_by_sport=types_by_sport,
        is_last_week=is_last_week,
        race_date=race_date,
        long_day_idx=long_session_day(training_idx),
    )
    sport_weight_total = _tally_sport_weights(day_plan, _SESSION_TYPE_WEIGHT)
    sport_elev_weight_total = _tally_sport_weights(day_plan, _ELEVATION_SESSION_WEIGHT)

    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_idx = day.weekday()

        if is_last_week and day == race_date:
            sessions.append(
                _race_day_session(day=day, race_sport=race_sport, week_offset=week_offset)
            )
            continue
        if day_idx not in day_plan:
            sessions.append(_rest_day_session(day=day, phase=phase, week_offset=week_offset))
            continue

        sport, stype = day_plan[day_idx]
        sessions.append(
            _training_day_session(
                day=day,
                phase=phase,
                week_offset=week_offset,
                stype=stype,
                sport=sport,
                tss_by_sport=tss_by_sport,
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
) -> tuple[dict[date, float], BanisterState, ActivityReview, list[dict[str, Any]]]:
    """Load last 180 days of activities, derive tss_by_date and today's CTL/ATL/TSB.

    Cold-start (<14 days of activities): skip the 180-day decay simulation and
    use the profile estimate AS today's state directly. See cold-start regression
    test for the rationale.

    Returns (tss_by_date, banister_state, activity_review, activities).
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
        return (
            tss_by_date,
            BanisterState(ctl=init_ctl, atl=init_ctl, tsb=0.0),
            activity_review,
            activities,
        )

    states = compute_banister_history(
        tss_by_date=tss_by_date,
        start=history_start,
        end=today,
        initial_ctl=0.0,
        initial_atl=0.0,
    )
    return tss_by_date, states[-1], activity_review, activities


def _build_all_week_sessions(
    *,
    phases: Sequence[tuple[int, Phase]],
    today_state: BanisterState,
    profile: dict[str, Any],
    first_week_tss_multiplier: float,
    sports_in_race: list[str],
    effective_strengths: dict[str, int],
    available_days: list[str],
    weeks_count: int,
    week_start: date,
    race_date: date,
    race_sport: str,
    race_dplus_by_sport: dict[str, int],
) -> list[dict[str, Any]]:
    """Build planned sessions for all weeks of the plan."""
    all_sessions: list[dict[str, Any]] = []
    prev_tss_by_sport: dict[str, float] | None = None
    load_multipliers = compute_week_load_multipliers(phases)
    for i, (offset, phase) in enumerate(phases):
        # Cible D+ recalculée par semaine : elle dépend de la phase (le taper doit
        # réellement lever le pied sur le dénivelé).
        weekly_elevation_by_sport = compute_weekly_elevation_targets(
            race_dplus_by_sport=race_dplus_by_sport, weeks_count=weeks_count, phase=phase
        )
        base_weekly = max(
            today_state.ctl * 7, weekly_tss_floor_from_hours(profile.get("hours_per_week"))
        )
        weekly_tss = base_weekly * load_multipliers[i]
        if offset == 0:
            weekly_tss *= first_week_tss_multiplier
        progress = _progress_for_offset(offset, phases)
        tss_by_sport = distribute_weekly_tss_by_sport(
            weekly_tss=weekly_tss,
            sports_in_race=sports_in_race,
            sports_strengths=effective_strengths,
            progress=progress,
        )
        tss_by_sport = cap_weekly_ramp_by_sport(tss_by_sport, prev_tss_by_sport)
        is_reduction_week = phase == "taper" or (offset + 1) % 4 == 0
        if not is_reduction_week:
            prev_tss_by_sport = tss_by_sport
        is_last = offset == weeks_count - 1
        sessions = _build_week_sessions(
            week_offset=offset,
            phase=phase,
            week_start=week_start + timedelta(weeks=offset),
            sports_in_race=sports_in_race,
            sports_strengths=effective_strengths,
            tss_by_sport=tss_by_sport,
            available_days=available_days,
            hours_per_week=profile.get("hours_per_week"),
            is_last_week=is_last,
            race_date=race_date,
            race_sport=race_sport,
            weekly_elevation_by_sport=weekly_elevation_by_sport,
            progress=progress,
        )
        all_sessions.extend(sessions)
    return all_sessions


def _workout_carry_key(session: dict[str, Any]) -> tuple[Any, ...]:
    """Identity used to reuse a workout across a regeneration.

    Same day, same sport, same type AND same target duration: anything else means
    the session actually changed and the previous workout no longer fits its
    numeric envelope.
    """
    return (
        session.get("date"),
        session.get("sport"),
        session.get("session_type"),
        session.get("target_duration_s"),
    )


def carry_over_workouts(
    new_sessions: list[dict[str, Any]], existing_sessions: Sequence[dict[str, Any]]
) -> int:
    """Copy already-generated (already PAID) workouts onto identical new sessions.

    The weekly regeneration used to drop every workout: each Monday the athlete
    found empty sessions and the LLM re-billed the exact same generations. Returns
    how many workouts were reused.
    """
    by_key = {_workout_carry_key(s): s for s in existing_sessions if s.get("workout") is not None}
    reused = 0
    for session in new_sessions:
        previous = by_key.get(_workout_carry_key(session))
        if previous is None:
            continue
        session["workout"] = previous["workout"]
        session["workout_generated_at"] = previous.get("workout_generated_at")
        reused += 1
    return reused


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

    tss_by_date, today_state, activity_review, activities = _load_today_banister_state(
        db=db, user_id=user_id, profile=profile, today=today
    )
    first_week_tss_multiplier = compute_first_week_tss_multiplier(activity_review)

    # Compute phases and per-week sessions
    phases = compute_phases(today, race_date)
    weeks_count = len(phases)
    sports_in_race = [leg["discipline"] for leg in race["legs"]]
    race_sport = race["legs"][0]["discipline"] if race["legs"] else "run"
    sports_strengths = profile.get("sports_strengths") or {"swim": 3, "bike": 3, "run": 3}
    effective_strengths = load_effective_strengths(
        db, user_id, sports_strengths, today=today, activities=activities
    )
    available_days = profile.get("available_days") or ["mon", "wed", "fri"]

    # Per-sport race D+ — la cible hebdo est dérivée par semaine (phase-aware)
    # dans _build_all_week_sessions.
    race_dplus_by_sport = compute_elevation_per_sport(race.get("legs") or [])

    # Anchor the week grid so the LAST week ENDS on race_date (race day = last day
    # of the last week). Previously week_start was pinned to the Monday of the
    # current week while phases were counted from ``today`` — the two origins
    # diverged, leaving the plan ending up to 13 days before the race with no
    # taper and no race session (prod bug 2026-07). Days before ``today`` (when the
    # grid starts slightly in the past) are dropped just before insert.
    week_start = race_date - timedelta(days=weeks_count * 7 - 1)
    all_sessions = _build_all_week_sessions(
        phases=phases,
        today_state=today_state,
        profile=profile,
        first_week_tss_multiplier=first_week_tss_multiplier,
        sports_in_race=sports_in_race,
        effective_strengths=effective_strengths,
        available_days=available_days,
        weeks_count=weeks_count,
        week_start=week_start,
        race_date=race_date,
        race_sport=race_sport,
        race_dplus_by_sport=race_dplus_by_sport,
    )

    # Drop any session dated before today: when the week grid starts a few days in
    # the past (race offset not a whole number of weeks), those days are already
    # gone and would only ever show up as empty, never-generated sessions.
    today_iso = today.isoformat()
    all_sessions = [s for s in all_sessions if s["date"] >= today_iso]

    # Reuse workouts already generated (and already billed) for identical upcoming
    # sessions, instead of re-paying the LLM for the same generations every week.
    existing_future_resp = (
        db.table("planned_sessions")
        .select("date, sport, session_type, target_duration_s, workout, workout_generated_at")
        .eq("user_id", user_id)
        .gte("date", today_iso)
        .execute()
    )
    reused_workouts = carry_over_workouts(
        all_sessions, cast(DbRows, existing_future_resp.data or [])
    )

    # Archive ALL of the user's plans, not just this race's: scoping the cleanup to
    # race_goal_id left an orphan ACTIVE plan (and duplicate sessions on /today)
    # whenever the primary race changed.
    previous_plans_resp = db.table("training_plans").select("id").eq("user_id", user_id).execute()
    previous_plan_ids = [p["id"] for p in cast(DbRows, previous_plans_resp.data or [])]
    if previous_plan_ids:
        # Only FUTURE sessions are replaced. Past sessions are the athlete's history
        # (prévu/réalisé) and are re-parented to the new plan further down — the
        # unfiltered delete used to wipe every past session on each weekly run.
        db.table("planned_sessions").delete().in_("plan_id", previous_plan_ids).gte(
            "date", today_iso
        ).execute()
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

    if previous_plan_ids:
        # Re-parent past sessions to the new plan so the athlete keeps their history:
        # the app reads planned_sessions through an INNER JOIN on the ACTIVE plan, so
        # anything left on an archived plan silently disappears from /plan and /stats.
        db.table("planned_sessions").update({"plan_id": plan_id}).in_(
            "plan_id", previous_plan_ids
        ).lt("date", today_iso).execute()

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
        "reused_workouts": reused_workouts,
    }
