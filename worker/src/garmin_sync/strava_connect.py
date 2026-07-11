"""Strava OAuth connect/disconnect flow. Mirrors connect.py's structure."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from garmin_sync import strava_client, supabase_client
from garmin_sync.crypto import TokenCipher

log = logging.getLogger(__name__)


def _new_error_id() -> str:
    return uuid.uuid4().hex[:8]


def _trigger_initial_backfill(user_id: str) -> None:
    """Fire the initial 90-day Strava backfill in a daemon thread.

    Mirrors connect.py::_trigger_initial_sync — the HTTP response to the
    caller must not wait on this. A failure here must never surface; the
    webhook and any future manual re-run pick up subsequent activities.
    """

    def _run() -> None:
        try:
            from garmin_sync.strava_sync import run_strava_backfill

            run_strava_backfill(user_id)
        except Exception:
            log.exception("post-connect Strava backfill failed for user=%s", user_id)

    threading.Thread(target=_run, name=f"strava-backfill-{user_id}", daemon=True).start()


def start_connect_flow(*, user_id: str, code: str) -> dict[str, Any]:
    try:
        tokens = strava_client.exchange_code(code)
    except strava_client.StravaAuthError:
        return {"status": "strava_auth_error"}
    except strava_client.StravaRateLimitError:
        return {"status": "rate_limited"}
    except Exception as e:
        error_id = _new_error_id()
        log.exception("[%s] Unexpected error exchanging Strava code for user=%s", error_id, user_id)
        return {"status": "unexpected_error", "error_id": error_id, "type": type(e).__name__}

    athlete_id = tokens["athlete"]["id"]
    token_blob = json.dumps(
        {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_at": tokens["expires_at"],
        }
    )
    encrypted = TokenCipher().encrypt(token_blob)

    db = supabase_client.get_admin_client()
    db.table("athlete_strava_credentials").upsert(
        {
            "user_id": user_id,
            "strava_athlete_id": athlete_id,
            "oauth_tokens_encrypted": encrypted.decode("ascii"),
            "token_refresh_failed_at": None,
            "last_sync_status": None,
            "updated_at": datetime.now(UTC).isoformat(),
        },
        on_conflict="user_id",
    ).execute()

    _trigger_initial_backfill(user_id)
    return {"status": "connected"}


def disconnect(*, user_id: str) -> dict[str, Any]:
    db: Any = supabase_client.get_admin_client()
    resp = (
        db.table("athlete_strava_credentials")
        .select("oauth_tokens_encrypted")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    row = cast("dict[str, Any] | None", resp.data if resp else None)
    if not row:
        return {"status": "not_connected"}

    try:
        blob = json.loads(TokenCipher().decrypt(row["oauth_tokens_encrypted"].encode("ascii")))
        strava_client.deauthorize(blob["access_token"])
    except Exception:
        log.warning("Strava deauthorize call failed for user=%s (continuing)", user_id)

    db.table("athlete_strava_credentials").delete().eq("user_id", user_id).execute()
    return {"status": "disconnected"}
