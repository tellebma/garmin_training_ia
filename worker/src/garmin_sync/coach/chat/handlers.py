"""Handlers des outils du chat coach — accès base, bornés et agrégés.

Chaque handler reçoit ``(db, user_id, **params)``. Le ``user_id`` vient toujours
du JWT vérifié, jamais du modèle (cf. :mod:`garmin_sync.coach.chat.tools`).

Ce qui ne sort jamais d'ici, par conception :

- ``athlete_profiles.lat`` / ``lon`` — coordonnées du domicile ;
- ``activities.route_polyline`` — tracé GPS complet ;
- ``activity_samples`` brut — passe par la RPC d'agrégation ``coach_activity_profile``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

# --- Plafonds serveur (non négociables par le modèle) -----------------------

MAX_ACTIVITIES = 30
MAX_HISTORY_DAYS = 365
MAX_FORM_DAYS = 120
MAX_SESSIONS = 30
MAX_FEEDBACK = 20
MAX_PROFILE_BUCKETS = 30

_SPORTS = ("swim", "bike", "run", "brick", "multi_sport", "strength_training")


class ToolError(Exception):
    """Erreur d'exécution d'un outil, renvoyée au modèle comme résultat."""


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    """Borne un entier fourni par le modèle. Toute valeur illisible retombe sur
    le défaut plutôt que de lever : le modèle hallucine parfois des chaînes."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _parse_date(value: Any, fallback: date) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return fallback


def _today() -> date:
    return datetime.now(UTC).date()


# --- Handlers ---------------------------------------------------------------


def _get_athlete_profile(db: Any, user_id: str) -> dict[str, Any]:
    """Profil sportif. Volontairement amputé de lat/lon (domicile), des colonnes
    de consentement et des curseurs techniques : rien de tout cela n'aide à
    répondre à une question d'entraînement."""
    resp = (
        db.table("athlete_profiles")
        .select(
            "first_name, dob, sex, ftp_watts, vma_kmh, fc_max_bpm, "
            "css_per_100m_s, hours_per_week, sports_strengths, available_days"
        )
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    row = dict(resp.data) if resp and resp.data else {}
    if not row:
        return {"found": False}

    # On renvoie l'âge, pas la date de naissance.
    dob = row.pop("dob", None)
    if dob:
        born = _parse_date(dob, _today())
        today = _today()
        row["age"] = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    row["found"] = True
    row["note_poids"] = "Le poids n'est pas collecté par l'app — demande-le à l'athlète si besoin."
    return row


def _get_form_state(db: Any, user_id: str, days: Any = 30) -> dict[str, Any]:
    n = _clamp(days, 1, MAX_FORM_DAYS, 30)
    start = _today() - timedelta(days=n)
    resp = (
        db.table("daily_banister_state")
        .select("date, ctl, atl, tsb, daily_tss")
        .eq("user_id", user_id)
        .gte("date", start.isoformat())
        .order("date", desc=True)
        .limit(MAX_FORM_DAYS)
        .execute()
    )
    rows = list(resp.data or [])
    return {
        "days": n,
        "latest": rows[0] if rows else None,
        "series": rows,
        "legend": (
            "ctl=forme (charge chronique), atl=fatigue (charge aiguë), tsb=fraîcheur (ctl-atl)"
        ),
    }


def _get_recovery_state(db: Any, user_id: str) -> dict[str, Any]:
    """Baselines de récupération + métriques du jour et de la veille."""
    today = _today()
    baselines = (
        db.table("recovery_baselines")
        .select("hrv, resting_hr, sleep, stress, body_battery, steps, computed_at")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    recent_metrics = (
        db.table("daily_metrics")
        .select("date, resting_hr, stress_avg, body_battery_low, body_battery_high, steps")
        .eq("user_id", user_id)
        .gte("date", (today - timedelta(days=7)).isoformat())
        .order("date", desc=True)
        .limit(7)
        .execute()
    )
    recent_hrv = (
        db.table("hrv")
        .select("date, hrv_rmssd, hrv_status, hrv_weekly_avg")
        .eq("user_id", user_id)
        .gte("date", (today - timedelta(days=7)).isoformat())
        .order("date", desc=True)
        .limit(7)
        .execute()
    )
    recent_sleep = (
        db.table("sleep")
        .select("date, sleep_duration_s, sleep_score")
        .eq("user_id", user_id)
        .gte("date", (today - timedelta(days=7)).isoformat())
        .order("date", desc=True)
        .limit(7)
        .execute()
    )
    return {
        "baselines": (baselines.data if baselines else None) or None,
        "last_7_days": {
            "daily_metrics": list(recent_metrics.data or []),
            "hrv": list(recent_hrv.data or []),
            "sleep": list(recent_sleep.data or []),
        },
    }


def _get_recent_activities(
    db: Any, user_id: str, sport: Any = None, limit: Any = 15, days: Any = 90
) -> dict[str, Any]:
    """Activités agrégées. Ni polyline ni samples : c'est ``get_activity_detail``
    qui creuse une activité précise, et lui seul."""
    n = _clamp(limit, 1, MAX_ACTIVITIES, 15)
    window = _clamp(days, 1, MAX_HISTORY_DAYS, 90)
    start = datetime.now(UTC) - timedelta(days=window)
    query = (
        db.table("activities")
        .select(
            "id, start_time, sport, duration_s, distance_m, elevation_gain_m, "
            "tss, hr_avg, hr_max, calories, pace_avg_s_per_km"
        )
        .eq("user_id", user_id)
        .gte("start_time", start.isoformat())
    )
    if sport and str(sport) in _SPORTS:
        query = query.eq("sport", str(sport))
    resp = query.order("start_time", desc=True).limit(n).execute()
    rows = list(resp.data or [])
    return {
        "count": len(rows),
        "limit_applied": n,
        "activities": rows,
        "hint": "Utilise get_activity_detail avec un id pour analyser une sortie en détail.",
    }


def _get_activity_detail(db: Any, user_id: str, activity_id: Any, buckets: Any = 20) -> Any:
    """Découpe une activité en tranches agrégées via la RPC coach_activity_profile.

    L'agrégation se fait en base : une sortie longue porte plusieurs milliers de
    samples, impossibles à envoyer au modèle.
    """
    if not activity_id:
        raise ToolError("activity_id est requis (utilise get_recent_activities pour en obtenir un)")
    n = _clamp(buckets, 4, MAX_PROFILE_BUCKETS, 20)
    header = (
        db.table("activities")
        .select(
            "id, start_time, sport, duration_s, distance_m, elevation_gain_m, tss, hr_avg, hr_max"
        )
        .eq("user_id", user_id)
        .eq("id", str(activity_id))
        .maybe_single()
        .execute()
    )
    if not header or not header.data:
        raise ToolError("Activité introuvable pour cet athlète")
    profile = db.rpc(
        "coach_activity_profile",
        {"p_user_id": user_id, "p_activity_id": str(activity_id), "p_buckets": n},
    ).execute()
    return {
        "activity": header.data,
        "profile": list(profile.data or []),
        "legend": "Tranches d'effectif égal. elevation/hr/speed sont des agrégats par tranche.",
    }


def _get_planned_sessions(db: Any, user_id: str, from_date: Any = None, to_date: Any = None) -> Any:
    today = _today()
    start = _parse_date(from_date, today)
    end = _parse_date(to_date, today + timedelta(days=14))
    if end < start:
        start, end = end, start
    resp = (
        db.table("planned_sessions")
        .select(
            "id, date, sport, session_type, target_duration_s, target_tss, "
            "target_elevation_gain_m, phase, notes"
        )
        .eq("user_id", user_id)
        .gte("date", start.isoformat())
        .lte("date", end.isoformat())
        .order("date")
        .limit(MAX_SESSIONS)
        .execute()
    )
    return {"from": start.isoformat(), "to": end.isoformat(), "sessions": list(resp.data or [])}


def _get_race_goal(db: Any, user_id: str) -> dict[str, Any]:
    resp = (
        db.table("race_goals")
        .select(
            "name, race_date, discipline, location, target_time_seconds, "
            "total_distance_km, total_elevation_gain_m, legs, is_primary, prep_start_date"
        )
        .eq("user_id", user_id)
        .order("race_date")
        .limit(5)
        .execute()
    )
    rows = list(resp.data or [])
    today = _today()
    for row in rows:
        race_date = _parse_date(row.get("race_date"), today)
        row["days_until"] = (race_date - today).days
    return {"races": rows}


def _get_activity_feedback(db: Any, user_id: str, limit: Any = 10) -> dict[str, Any]:
    """Ressentis déclarés par l'athlète.

    ``comment`` et ``pain_area`` sont du texte libre saisi par l'utilisateur :
    l'appelant doit les traiter comme des données, jamais comme des instructions
    (cf. délimitation dans le prompt système).
    """
    n = _clamp(limit, 1, MAX_FEEDBACK, 10)
    resp = (
        db.table("activity_feedback")
        .select(
            "activity_id, created_at, rpe, fatigue, soreness, pain, mood, "
            "perceived_difficulty, pain_area, comment"
        )
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(n)
        .execute()
    )
    return {
        "feedback": list(resp.data or []),
        "legend": "rpe/fatigue/soreness/pain/mood sont des échelles déclaratives 1-5.",
    }
