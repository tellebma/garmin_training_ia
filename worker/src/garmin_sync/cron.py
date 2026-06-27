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
from garmin_sync.sync import (
    SYNC_MODE_ACTIVITIES_ONLY,
    SYNC_MODE_FULL,
    SYNC_MODE_SLEEP_ONLY,
    GarminProfileIncompleteError,
    SyncMode,
    sync_user_for_date_range,
)

log = logging.getLogger(__name__)

INITIAL_BACKFILL_DAYS = 90


def run_sync_for_user(
    user_id: str, *, initial: bool = False, mode: SyncMode = SYNC_MODE_FULL
) -> dict[str, Any]:
    """Sync a single user. Used by /sync endpoint and by run_*_cron functions."""
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
        sync_user_for_date_range(user_id=user_id, client=client, start=start, end=today, mode=mode)
    except GarminConnectTooManyRequestsError:
        db.table("garmin_credentials").update(
            {
                "last_sync_at": datetime.now(UTC).isoformat(),
                "last_sync_status": "rate_limited",
                "last_sync_status_at": datetime.now(UTC).isoformat(),
                "last_sync_error_message": (
                    "Garmin a temporairement bloqué les requêtes (rate limit)."
                ),
            }
        ).eq("user_id", user_id).execute()
        log.warning("sync rate-limited for user=%s — aborted", user_id)
        return {"status": "rate_limited"}
    except GarminConnectAuthenticationError:
        db.table("garmin_credentials").update(
            {
                "token_refresh_failed_at": datetime.now(UTC).isoformat(),
                "last_sync_status": "auth_failed",
                "last_sync_status_at": datetime.now(UTC).isoformat(),
                "last_sync_error_message": "Ton token Garmin est expiré. Reconnecte-toi.",
            }
        ).eq("user_id", user_id).execute()
        log.warning("sync auth-failed for user=%s — token marked stale", user_id)
        return {"status": "auth_failed"}
    except GarminProfileIncompleteError as exc:
        db.table("garmin_credentials").update(
            {
                "last_sync_at": datetime.now(UTC).isoformat(),
                "last_sync_status": "garmin_no_display_name",
                "last_sync_status_at": datetime.now(UTC).isoformat(),
                "last_sync_error_message": str(exc),
            }
        ).eq("user_id", user_id).execute()
        log.warning("sync aborted user=%s — Garmin profile incomplete (no display_name)", user_id)
        # Activities + TSS were synced before the display_name failure — recompute
        # Banister state from whatever was persisted so /today + /stats still work.
        try:
            recompute_daily_state(user_id, days_back=180)
        except Exception:
            log.exception("recompute_daily_state failed for user=%s", user_id)
        return {"status": "garmin_no_display_name"}

    now_iso = datetime.now(UTC).isoformat()
    update_payload: dict[str, Any] = {
        "last_sync_at": now_iso,
        "last_sync_status": "ok",
        "last_sync_status_at": now_iso,
        "last_sync_error_message": None,
        "initial_sync_completed_at": now_iso
        if not creds.get("initial_sync_completed_at")
        else creds["initial_sync_completed_at"],
    }
    # Per-category timestamps for UI freshness display
    if mode in (SYNC_MODE_FULL, SYNC_MODE_SLEEP_ONLY):
        update_payload["last_sleep_sync_at"] = now_iso
    if mode in (SYNC_MODE_FULL, SYNC_MODE_ACTIVITIES_ONLY):
        update_payload["last_activities_sync_at"] = now_iso
    db.table("garmin_credentials").update(update_payload).eq("user_id", user_id).execute()

    # E7 — Materialize Banister state for fast frontend reads.
    # Wrapped in try/except : a failure here MUST NOT abort the sync.
    try:
        recompute_daily_state(user_id, days_back=180)
    except Exception:
        log.exception("recompute_daily_state failed for user=%s", user_id)
    try:
        from garmin_sync.coach.recovery_baselines import recompute_recovery_baselines

        recompute_recovery_baselines(user_id)
    except Exception:
        log.exception("recompute_recovery_baselines failed for user=%s", user_id)

    return {"status": "ok", "days_synced": (today - start).days + 1}


def _iter_active_users(db: Any) -> list[str]:
    users = (
        db.table("garmin_credentials")
        .select("user_id")
        .is_("token_refresh_failed_at", "null")
        .execute()
    )
    rows = cast("list[dict[str, Any]]", users.data)
    return [str(r["user_id"]) for r in rows]


def _run_cron(mode: SyncMode, label: str) -> dict[str, Any]:
    """Iterate all users with credentials and run a sync of the given mode."""
    db = get_admin_client()
    user_ids = _iter_active_users(db)
    results: dict[str, dict[str, Any]] = {}
    for uid in user_ids:
        try:
            results[uid] = run_sync_for_user(uid, initial=False, mode=mode)
        except Exception:
            log.exception("%s cron failed for user=%s", label, uid)
            results[uid] = {"status": "exception"}
    return {"mode": mode, "total_users": len(user_ids), "results": results}


def run_daily_cron() -> dict[str, Any]:
    """Daily FULL sync (kept for backwards compatibility with existing timer)."""
    return _run_cron(SYNC_MODE_FULL, label="full")


def run_sleep_cron() -> dict[str, Any]:
    """Morning cron: pull last night's sleep + HRV + daily metrics. ~08:00 UTC."""
    return _run_cron(SYNC_MODE_SLEEP_ONLY, label="sleep")


def run_activities_cron() -> dict[str, Any]:
    """Afternoon/evening cron: pull recent activities + daily metrics. ~13:00/18:00 UTC."""
    return _run_cron(SYNC_MODE_ACTIVITIES_ONLY, label="activities")


def run_profile_sync_cron() -> dict[str, Any]:
    """Weekly cron: refresh FTP / VMA / FCmax from Garmin user profile."""
    from garmin_sync.profile_sync import sync_garmin_profile

    db = get_admin_client()
    user_ids = _iter_active_users(db)
    results: dict[str, dict[str, Any]] = {}
    for uid in user_ids:
        try:
            result = sync_garmin_profile(uid)
            results[uid] = result
            if isinstance(result, dict) and result.get("status") == "ok":
                db.table("garmin_credentials").update(
                    {"last_profile_sync_at": datetime.now(UTC).isoformat()}
                ).eq("user_id", uid).execute()
        except Exception:
            log.exception("profile sync failed for user=%s", uid)
            results[uid] = {"status": "exception"}
    return {"mode": "profile", "total_users": len(user_ids), "results": results}


_MODES = {
    "full": run_daily_cron,
    "sleep": run_sleep_cron,
    "activities": run_activities_cron,
    "profile": run_profile_sync_cron,
}


if __name__ == "__main__":
    import json
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    runner = _MODES.get(mode)
    if not runner:
        print(f"unknown mode={mode!r}. valid: {sorted(_MODES)}", file=sys.stderr)
        sys.exit(2)
    out = runner()
    print(json.dumps(out, indent=2))
