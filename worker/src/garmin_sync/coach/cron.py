"""Cron entry point — regenerate plans weekly for all active users.

Usage : python -m garmin_sync.coach.cron

Triggered by systemd timer on UNRAID server (see worker/deploy/README.md).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import Any, cast

from garmin_sync.coach.planner import generate_plan
from garmin_sync.coach.sessions import ensure_sessions
from garmin_sync.observability import capture
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

# Below this age (in days) since the last successful activities sync, a user is
# considered "fresh" and gets their plan regenerated normally. Above it, the
# coach cannot tell "athlete stopped training" from "we stopped receiving their
# data" (#126), so regeneration is skipped and an alert is raised instead.
#
# Activities/sleep crons run 3x/day and always bump `last_activities_sync_at`
# on a successful sync — even on a rest day with zero new activities. 3 days
# therefore already covers 6+ missed sync windows plus a full Garmin rate-limit
# block (up to 24h, see CLAUDE.md pitfalls), while catching real breakage well
# before the next Sunday regeneration — instead of the 19 days seen in prod.
GARMIN_SYNC_STALE_DAYS = 3


class GarminSyncStaleError(RuntimeError):
    """Raised only to carry a structured message into observability.capture()."""


def _last_synced_at(row: dict[str, Any] | None) -> datetime | None:
    """Best signal of "are we still receiving this user's Garmin data" — the
    activities sync timestamp (falls back to the generic full-sync one)."""
    if not row:
        return None
    raw = row.get("last_activities_sync_at") or row.get("last_sync_at")
    if not raw:
        return None
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


def _fetch_garmin_credentials(db: Any, user_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not user_ids:
        return {}
    resp = (
        db.table("garmin_credentials")
        .select("user_id, last_activities_sync_at, last_sync_at")
        .in_("user_id", user_ids)
        .execute()
    )
    rows = cast("list[dict[str, Any]]", resp.data or [])
    return {str(row["user_id"]): row for row in rows}


def run_weekly_cron() -> dict[str, Any]:
    """For each user with an active future race_goal, regenerate the plan and
    generate the upcoming workouts.

    La génération de workouts n'était déclenchée que par l'ouverture de /today :
    un utilisateur qui n'ouvre pas l'app n'avait jamais de séance générée (moitié
    des séances prod restaient workout=NULL). On la déclenche donc ici aussi.

    Garde-fou #126 : un utilisateur dont le sync Garmin est mort depuis plus de
    GARMIN_SYNC_STALE_DAYS n'a pas son plan régénéré sur des données périmées —
    on remonte l'état dans le résultat et on alerte au lieu de rester silencieux.
    """
    db = get_admin_client()
    today_iso = date.today().isoformat()
    users_resp = (
        db.table("race_goals")
        .select("user_id")
        .eq("is_primary", True)
        .gte("race_date", today_iso)
        .execute()
    )
    users = cast("list[dict[str, Any]]", users_resp.data or [])
    user_ids = list({u["user_id"] for u in users})

    creds_by_user = _fetch_garmin_credentials(db, user_ids)
    now = datetime.now(UTC)

    results: dict[str, dict[str, Any]] = {}
    skipped_stale = 0
    for uid in user_ids:
        last_synced_at = _last_synced_at(creds_by_user.get(uid))
        if last_synced_at is not None:
            days_since_sync = (now - last_synced_at).days
            if days_since_sync > GARMIN_SYNC_STALE_DAYS:
                skipped_stale += 1
                results[uid] = {
                    "status": "stale_data_skipped",
                    "days_since_sync": days_since_sync,
                    "last_sync_at": last_synced_at.isoformat(),
                    "ensure_sessions": {"status": "skipped_stale_data"},
                }
                capture(
                    GarminSyncStaleError(
                        f"Sync Garmin périmé depuis {days_since_sync} j pour "
                        f"user={uid} — plan non régénéré (#126)"
                    ),
                    where="coach_weekly_cron",
                    level="warning",
                    user_id=uid,
                    days_since_sync=days_since_sync,
                )
                continue

        try:
            results[uid] = generate_plan(uid)
        except Exception as e:
            log.exception("Plan regeneration failed for user=%s", uid)
            results[uid] = {"status": "exception", "type": type(e).__name__}
            continue
        try:
            results[uid]["ensure_sessions"] = ensure_sessions(user_id=uid)
        except Exception as e:
            log.exception("Workout generation failed for user=%s", uid)
            results[uid]["ensure_sessions"] = {
                "status": "exception",
                "type": type(e).__name__,
            }
    return {"total_users": len(user_ids), "skipped_stale": skipped_stale, "results": results}


if __name__ == "__main__":
    print(json.dumps(run_weekly_cron(), indent=2))
