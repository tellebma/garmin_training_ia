"""Cron entry point — run sync for all users with valid Garmin credentials."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from garmin_sync.coach.state import recompute_daily_state
from garmin_sync.crypto import TokenCipher
from garmin_sync.garmin_client import GarminAuthError, login_with_tokens
from garmin_sync.supabase_client import get_admin_client
from garmin_sync.sync import sync_user_for_date_range

log = logging.getLogger(__name__)

INITIAL_BACKFILL_DAYS = 90


def run_sync_for_user(user_id: str, *, initial: bool = False) -> dict[str, Any]:
    """Sync a single user. Used by /sync endpoint and by run_daily_cron."""
    db = get_admin_client()
    creds_resp = (
        db.table("garmin_credentials")
        .select("oauth_tokens_encrypted, initial_sync_completed_at")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    creds = cast("dict[str, Any] | None", creds_resp.data)
    if not creds or not creds.get("oauth_tokens_encrypted"):
        return {"status": "no_credentials"}

    cipher = TokenCipher()
    # oauth_tokens_encrypted is stored as text (ASCII base64 from Fernet);
    # re-encode to bytes for decryption.
    encrypted_str = creds["oauth_tokens_encrypted"]
    serialized = cipher.decrypt(encrypted_str.encode("ascii"))
    try:
        client = login_with_tokens(serialized)
    except GarminAuthError:
        db.table("garmin_credentials").update(
            {"token_refresh_failed_at": datetime.now(UTC).isoformat()}
        ).eq("user_id", user_id).execute()
        return {"status": "auth_failed"}

    today = date.today()
    if initial or not creds.get("initial_sync_completed_at"):
        start = today - timedelta(days=INITIAL_BACKFILL_DAYS)
    else:
        start = today - timedelta(days=2)

    try:
        sync_user_for_date_range(user_id=user_id, client=client, start=start, end=today)
    except GarminConnectTooManyRequestsError:
        db.table("garmin_credentials").update(
            {
                "last_sync_at": datetime.now(UTC).isoformat(),
                "last_sync_status": "rate_limited",
            }
        ).eq("user_id", user_id).execute()
        log.warning("sync rate-limited for user=%s — aborted", user_id)
        return {"status": "rate_limited"}
    except GarminConnectAuthenticationError:
        db.table("garmin_credentials").update(
            {
                "token_refresh_failed_at": datetime.now(UTC).isoformat(),
                "last_sync_status": "auth_failed",
            }
        ).eq("user_id", user_id).execute()
        log.warning("sync auth-failed for user=%s — token marked stale", user_id)
        return {"status": "auth_failed"}

    db.table("garmin_credentials").update(
        {
            "last_sync_at": datetime.now(UTC).isoformat(),
            "last_sync_status": "ok",
            "initial_sync_completed_at": datetime.now(UTC).isoformat()
            if not creds.get("initial_sync_completed_at")
            else creds["initial_sync_completed_at"],
        }
    ).eq("user_id", user_id).execute()

    # E7 — Materialize Banister state for fast frontend reads.
    # Wrapped in try/except : a failure here MUST NOT abort the sync.
    try:
        recompute_daily_state(user_id, days_back=180)
    except Exception:
        log.exception("recompute_daily_state failed for user=%s", user_id)

    return {"status": "ok", "days_synced": (today - start).days + 1}


def run_daily_cron() -> dict[str, Any]:
    """Iterate all users with credentials and sync each."""
    db = get_admin_client()
    users = (
        db.table("garmin_credentials")
        .select("user_id")
        .is_("token_refresh_failed_at", "null")
        .execute()
    )

    rows = cast("list[dict[str, Any]]", users.data)
    results: dict[str, dict[str, Any]] = {}
    for row in rows:
        uid = str(row["user_id"])
        try:
            results[uid] = run_sync_for_user(uid, initial=False)
        except Exception:
            log.exception("daily cron failed for user=%s", uid)
            results[uid] = {"status": "exception"}
    return {"total_users": len(rows), "results": results}


if __name__ == "__main__":
    import json

    out = run_daily_cron()
    print(json.dumps(out, indent=2))
