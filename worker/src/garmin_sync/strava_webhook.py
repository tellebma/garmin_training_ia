"""Strava webhook business logic: subscription challenge + event dispatch."""

from __future__ import annotations

import logging
from typing import Any

from garmin_sync import strava_sync, supabase_client
from garmin_sync.config import get_settings

log = logging.getLogger(__name__)


def verify_challenge(*, mode: str | None, token: str | None, challenge: str | None) -> str | None:
    if mode != "subscribe" or not token or not challenge:
        return None
    settings = get_settings()
    if not settings.strava_configured:
        return None
    expected = settings.strava_webhook_verify_token.get_secret_value()
    if token != expected:
        return None
    return challenge


def _resolve_user_id(owner_id: int) -> str | None:
    db: Any = supabase_client.get_admin_client()
    resp = (
        db.table("athlete_strava_credentials")
        .select("user_id")
        .eq("strava_athlete_id", owner_id)
        .maybe_single()
        .execute()
    )
    row: dict[str, Any] | None = resp.data if resp else None
    return row["user_id"] if row else None


def handle_event(payload: dict[str, Any]) -> dict[str, Any]:
    owner_id = payload.get("owner_id")
    object_type = payload.get("object_type")
    aspect_type = payload.get("aspect_type")

    if object_type == "athlete" and (payload.get("updates") or {}).get("authorized") == "false":
        db: Any = supabase_client.get_admin_client()
        db.table("athlete_strava_credentials").delete().eq("strava_athlete_id", owner_id).execute()
        return {"status": "deauthorized"}

    if object_type != "activity" or owner_id is None:
        return {"status": "ignored"}

    user_id = _resolve_user_id(int(owner_id))
    if user_id is None:
        log.info("Strava webhook: unknown owner_id=%s, ignoring", owner_id)
        return {"status": "unknown_athlete"}

    activity_id = int(payload["object_id"])

    if aspect_type in ("create", "update"):
        return strava_sync.store_activity_from_webhook(user_id, activity_id)

    if aspect_type == "delete":
        return strava_sync.delete_activity_from_webhook(user_id, activity_id)

    return {"status": "ignored"}
