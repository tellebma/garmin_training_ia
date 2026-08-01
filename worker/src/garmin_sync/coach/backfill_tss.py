"""Backfill / recompute activity TSS, then refresh daily_banister_state.

Two modes:
- default        : only activities where tss IS NULL (original behavior);
- --recompute-all: every activity — needed after a TSS formula change such as
  issue #120 (power tier dead for sport='bike', fc_max fallback) and issue #133
  (reduced load factor for non swim/bike/run sports).

Idempotent — a row whose recomputed TSS equals the stored value is skipped.
After the updates, daily_banister_state is recomputed for each touched user
(disable with --skip-state).

Usage : python -m garmin_sync.coach.backfill_tss [--recompute-all] [--skip-state]
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, cast

from garmin_sync.coach.state import recompute_daily_state
from garmin_sync.coach.tss import compute_tss, resolve_fc_max_bpm
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

_ACTIVITY_COLUMNS = "id, user_id, start_time, duration_s, sport, power_avg, hr_avg, hr_max, tss"


def _fetch_activities(db: Any, *, recompute_all: bool) -> list[dict[str, Any]]:
    query = db.table("activities").select(_ACTIVITY_COLUMNS)
    if not recompute_all:
        query = query.is_("tss", "null")
    return cast("list[dict[str, Any]]", query.execute().data or [])


def _fetch_profile(db: Any, user_id: str) -> dict[str, Any]:
    resp = (
        db.table("athlete_profiles")
        .select("ftp_watts, fc_max_bpm")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return cast("dict[str, Any]", resp.data or {})


def backfill_tss(*, recompute_all: bool = False, recompute_state: bool = True) -> dict[str, int]:
    """Recompute TSS for activities, then daily_banister_state per touched user.

    Returns: {"updated": int, "skipped": int, "errors": int, "users_recomputed": int}
    """
    db = get_admin_client()
    activities = _fetch_activities(db, recompute_all=recompute_all)

    by_user: dict[str, list[dict[str, Any]]] = {}
    for a in activities:
        by_user.setdefault(a["user_id"], []).append(a)

    today = date.today()
    updated = 0
    skipped = 0
    errors = 0
    touched_users: set[str] = set()
    for user_id, user_activities in by_user.items():
        profile = _fetch_profile(db, user_id)
        # fc_max fallback (issue #120): profile value, else the user's observed
        # 90-day hr_max from the rows fetched above.
        fc_max = resolve_fc_max_bpm(profile.get("fc_max_bpm"), user_activities, today=today)
        for a in user_activities:
            try:
                tss = compute_tss(
                    duration_s=a.get("duration_s") or 0,
                    sport=a.get("sport") or "",
                    power_avg=a.get("power_avg"),
                    hr_avg=a.get("hr_avg"),
                    ftp_watts=profile.get("ftp_watts"),
                    fc_max_bpm=fc_max,
                )
                if tss is None or tss == a.get("tss"):
                    skipped += 1
                    continue
                db.table("activities").update({"tss": tss}).eq("id", a["id"]).execute()
                updated += 1
                touched_users.add(user_id)
            except Exception:
                log.exception("Failed to backfill TSS for activity %s", a.get("id"))
                errors += 1

    users_recomputed = 0
    if recompute_state:
        for user_id in sorted(touched_users):
            try:
                recompute_daily_state(user_id)
                users_recomputed += 1
            except Exception:
                log.exception("Failed to recompute daily state for user %s", user_id)
                errors += 1

    return {
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "users_recomputed": users_recomputed,
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recompute-all",
        action="store_true",
        help="recompute every activity, not only those with tss IS NULL",
    )
    parser.add_argument(
        "--skip-state",
        action="store_true",
        help="do not recompute daily_banister_state afterwards",
    )
    args = parser.parse_args()
    result = backfill_tss(recompute_all=args.recompute_all, recompute_state=not args.skip_state)
    print(json.dumps(result, indent=2))
