"""Orchestrator : fetch pending sessions, call LLM, persist workout."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from garmin_sync.coach.activity_review import ActivityReview, build_activity_review
from garmin_sync.coach.openai_client import OpenAIError, generate_workout_for_session
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)


class SessionNotFound(Exception):
    """Raised when a session_id does not exist for the given user."""


def _load_profile_and_race(
    db: Any, user_id: str
) -> tuple[dict[str, Any], dict[str, Any] | None, int]:
    """Returns (athlete, race_or_None, weeks_to_race_or_0)."""
    profile_resp = (
        db.table("athlete_profiles")
        .select("ftp_watts, vma_kmh, fc_max_bpm, sports_strengths")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    profile = cast("dict[str, Any]", profile_resp.data or {})

    race_resp = (
        db.table("race_goals")
        .select("discipline, total_elevation_gain_m, race_date")
        .eq("user_id", user_id)
        .eq("is_primary", True)
        .maybe_single()
        .execute()
    )
    race = cast("dict[str, Any] | None", race_resp.data)

    weeks = 0
    if race and race.get("race_date"):
        race_date = date.fromisoformat(race["race_date"])
        weeks = max(0, (race_date - date.today()).days // 7)
    return profile, race, weeks


def _race_context(
    race: dict[str, Any] | None, weeks: int, activity_review: ActivityReview | None = None
) -> dict[str, Any]:
    ctx = {
        "discipline": "unknown",
        "total_elevation_gain_m": 0,
        "weeks_to_race": weeks,
    }
    if race:
        ctx = {
            "discipline": race.get("discipline", "unknown"),
            "total_elevation_gain_m": race.get("total_elevation_gain_m") or 0,
            "weeks_to_race": weeks,
        }
    if activity_review:
        ctx["activity_review"] = activity_review.to_dict()
    return ctx


def _load_activity_review(db: Any, user_id: str, today: date) -> ActivityReview:
    start = today - timedelta(days=90)
    resp = (
        db.table("activities")
        .select("start_time, sport, duration_s, distance_m, elevation_gain_m, tss, hr_avg")
        .eq("user_id", user_id)
        .gte("start_time", start.isoformat())
        .order("start_time", desc=True)
        .execute()
    )
    rows = resp.data if isinstance(resp.data, list) else []
    return build_activity_review(cast("list[dict[str, Any]]", rows), today=today)


def _activity_review_note(activity_review: ActivityReview) -> str:
    insights = [i.message for i in activity_review.insights[:3]]
    if not insights:
        return ""
    return " Revue coach récente : " + " ".join(insights)


def _session_with_activity_review_note(
    session: dict[str, Any], activity_review: ActivityReview
) -> dict[str, Any]:
    note = _activity_review_note(activity_review)
    if not note:
        return session
    return {
        **session,
        "coach_context": note.strip(),
    }


def _generate_and_persist(
    db: Any,
    session: dict[str, Any],
    athlete: dict[str, Any],
    race_ctx: dict[str, Any],
) -> bool:
    try:
        workout = generate_workout_for_session(
            session=session, athlete=athlete, race_context=race_ctx
        )
    except OpenAIError as e:
        log.exception("openai failed for session=%s: %s", session["id"], e)
        return False
    db.table("planned_sessions").update(
        {
            "workout": workout.model_dump(),
            "workout_generated_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", session["id"]).execute()
    return True


def ensure_sessions(*, user_id: str, days: int = 7) -> dict[str, int]:
    """Generate workouts for planned_sessions where workout IS NULL in [today, today+days]."""
    db = get_admin_client()
    today = date.today()
    until = today + timedelta(days=days)

    pending_resp = (
        db.table("planned_sessions")
        .select(
            "id, sport, session_type, target_duration_s, target_tss, "
            "target_elevation_gain_m, phase, date"
        )
        .eq("user_id", user_id)
        .is_("workout", "null")
        .gte("date", today.isoformat())
        .lte("date", until.isoformat())
        .execute()
    )
    pending = cast("list[dict[str, Any]]", pending_resp.data or [])

    if not pending:
        return {"generated_count": 0, "failed_count": 0, "skipped_count": 0}

    athlete, race, weeks = _load_profile_and_race(db, user_id)
    activity_review = _load_activity_review(db, user_id, today)
    race_ctx = _race_context(race, weeks, activity_review)

    generated = 0
    failed = 0
    for session in pending:
        session_for_generation = _session_with_activity_review_note(session, activity_review)
        if _generate_and_persist(db, session_for_generation, athlete, race_ctx):
            generated += 1
        else:
            failed += 1
    return {"generated_count": generated, "failed_count": failed, "skipped_count": 0}


def regenerate_session(*, user_id: str, session_id: str) -> dict[str, Any]:
    """Force regenerate one session. Returns {status, workout}."""
    db = get_admin_client()
    session_resp = (
        db.table("planned_sessions")
        .select(
            "id, sport, session_type, target_duration_s, target_tss, "
            "target_elevation_gain_m, phase, date"
        )
        .eq("id", session_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    session = cast("dict[str, Any] | None", session_resp.data)
    if not session:
        raise SessionNotFound(f"session {session_id} not found for user {user_id}")

    athlete, race, weeks = _load_profile_and_race(db, user_id)
    activity_review = _load_activity_review(db, user_id, date.today())
    race_ctx = _race_context(race, weeks, activity_review)
    session_for_generation = _session_with_activity_review_note(session, activity_review)

    workout = generate_workout_for_session(
        session=session_for_generation, athlete=athlete, race_context=race_ctx
    )
    db.table("planned_sessions").update(
        {
            "workout": workout.model_dump(),
            "workout_generated_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", session_id).execute()
    return {"status": "ok", "workout": workout.model_dump()}
