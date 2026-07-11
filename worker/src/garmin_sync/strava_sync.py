"""Strava activity ingestion: initial backfill and webhook-triggered fetches.

Token refresh, app-wide rate limiting, and the Garmin-priority dedup rule are
all applied here, in front of every write to `activities`.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from garmin_sync import dedup, strava_client, strava_rate_limit, supabase_client
from garmin_sync.crypto import TokenCipher
from garmin_sync.transformers.strava_activities import transform_strava_activity

log = logging.getLogger(__name__)

_REFRESH_MARGIN_S = 60


def _load_credentials(db: Any, user_id: str) -> dict[str, Any] | None:
    return cast(
        "dict[str, Any] | None",
        db.table("athlete_strava_credentials")
        .select("oauth_tokens_encrypted")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
        .data,
    )


def get_valid_access_token(user_id: str) -> str | None:
    db = supabase_client.get_admin_client()
    row = _load_credentials(db, user_id)
    if not row:
        return None

    blob: dict[str, Any] = json.loads(
        TokenCipher().decrypt(row["oauth_tokens_encrypted"].encode("ascii"))
    )
    if blob["expires_at"] > time.time() + _REFRESH_MARGIN_S:
        return cast(str, blob["access_token"])

    try:
        strava_rate_limit.check_or_raise()
        refreshed = strava_client.refresh_access_token(blob["refresh_token"])
        strava_rate_limit.record_call()
    except strava_rate_limit.StravaRateLimitExceeded:
        log.warning("Strava rate limit hit during token refresh for user=%s", user_id)
        return None
    except Exception:
        log.warning("Strava token refresh failed for user=%s", user_id)
        db.table("athlete_strava_credentials").update(
            {"token_refresh_failed_at": datetime.now(UTC).isoformat()}
        ).eq("user_id", user_id).execute()
        return None

    new_blob = json.dumps(
        {
            "access_token": refreshed["access_token"],
            "refresh_token": refreshed["refresh_token"],
            "expires_at": refreshed["expires_at"],
        }
    )
    encrypted = TokenCipher().encrypt(new_blob)
    db.table("athlete_strava_credentials").update(
        {"oauth_tokens_encrypted": encrypted.decode("ascii"), "token_refresh_failed_at": None}
    ).eq("user_id", user_id).execute()
    return cast(str, refreshed["access_token"])


def _insert_if_not_duplicate(db: Any, user_id: str, raw: dict[str, Any]) -> bool:
    row = transform_strava_activity(user_id=user_id, raw=raw)
    if row["start_time"] is None:
        return False
    if dedup.is_likely_garmin_duplicate(
        db, user_id=user_id, start_time=row["start_time"], sport=row["sport"]
    ):
        return False
    db.table("activities").upsert([row], on_conflict="user_id,strava_activity_id").execute()
    return True


def run_strava_backfill(user_id: str, *, since_days: int = 90) -> dict[str, Any]:
    token = get_valid_access_token(user_id)
    if token is None:
        return {"status": "no_credentials"}

    db = supabase_client.get_admin_client()
    after_epoch = int((datetime.now(UTC) - timedelta(days=since_days)).timestamp())
    inserted = 0
    page = 1
    rate_limited = False
    while True:
        try:
            strava_rate_limit.check_or_raise()
        except Exception:
            log.warning("Strava rate limit hit mid-backfill for user=%s, stopping", user_id)
            rate_limited = True
            break
        activities = strava_client.list_activities(
            token, after_epoch=after_epoch, page=page, per_page=100
        )
        strava_rate_limit.record_call()
        if not activities:
            break
        for raw in activities:
            if _insert_if_not_duplicate(db, user_id, raw):
                inserted += 1
        page += 1

    update: dict[str, Any] = {"last_sync_at": datetime.now(UTC).isoformat()}
    if rate_limited:
        update["last_sync_status"] = "rate_limited"
    else:
        update["initial_sync_completed_at"] = datetime.now(UTC).isoformat()
        update["last_sync_status"] = "ok"
    db.table("athlete_strava_credentials").update(update).eq("user_id", user_id).execute()
    return {"status": "rate_limited" if rate_limited else "ok", "inserted": inserted}


def store_activity_from_webhook(user_id: str, activity_id: int) -> dict[str, Any]:
    token = get_valid_access_token(user_id)
    if token is None:
        return {"status": "no_credentials"}

    strava_rate_limit.check_or_raise()
    raw = strava_client.get_activity(token, activity_id)
    strava_rate_limit.record_call()

    db = supabase_client.get_admin_client()
    inserted = _insert_if_not_duplicate(db, user_id, raw)
    return {"status": "stored" if inserted else "skipped_duplicate"}


def delete_activity_from_webhook(user_id: str, activity_id: int) -> dict[str, Any]:
    db = supabase_client.get_admin_client()
    db.table("activities").delete().eq("user_id", user_id).eq("source", "strava").eq(
        "strava_activity_id", activity_id
    ).execute()
    return {"status": "deleted"}
