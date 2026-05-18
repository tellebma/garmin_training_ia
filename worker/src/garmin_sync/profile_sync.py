"""Garmin profile auto-fetch — pulls FTP/VO2max/FCmax from Garmin Connect and
upserts into athlete_profiles. Called from the wizard step Perf and from the
'↻ Sync Garmin' button on /profile.

Design notes
------------
- We NEVER touch dob/sex (saisis manuellement à l'étape Perso, overwrite serait
  surprenant UX).
- We exclude keys whose Garmin value is None — the resulting UPDATE only writes
  fields where Garmin has a fresh value, preserving any manual entry the user
  made before.
- No cooldown : tokens already valid, the endpoint never triggers the login
  cascade that PR #6 protects against.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any, cast

from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from garmin_sync.crypto import TokenCipher
from garmin_sync.garmin_client import GarminAuthError, login_with_tokens
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _vma_from_vo2max(vo2: float | None) -> float | None:
    """VO2max (ml/kg/min) → VMA (km/h) via VMA = VO2max / 3.5 (formule classique)."""
    if not vo2:
        return None
    return round(vo2 / 3.5, 2)


def _normalize_sex(raw: str | None) -> str | None:
    if not raw:
        return None
    upper = raw.upper()
    if upper == "MALE":
        return "M"
    if upper == "FEMALE":
        return "F"
    if upper == "OTHER":
        return "X"
    return None


def _transform_profile(user_profile: dict[str, Any], max_metrics: dict[str, Any]) -> dict[str, Any]:
    """Return only non-null perf fields. Keys with None values are EXCLUDED."""
    row: dict[str, Any] = {}
    ftp = _safe_int(user_profile.get("functionalThresholdPower"))
    if ftp is not None:
        row["ftp_watts"] = ftp
    vma = _vma_from_vo2max(max_metrics.get("vo2MaxValueRunning"))
    if vma is not None:
        row["vma_kmh"] = vma
    fcmax = _safe_int(user_profile.get("userMaxHr"))
    if fcmax is not None:
        row["fc_max_bpm"] = fcmax
    return row


def sync_garmin_profile(user_id: str) -> dict[str, Any]:
    """Auto-fetch FTP/VMA/FCmax from Garmin Connect, upsert into athlete_profiles.

    Returns one of:
        {"status": "ok", "fetched": {...}}
        {"status": "no_credentials"}
        {"status": "auth_failed"}        — tokens dead, user must reconnect Garmin
        {"status": "rate_limited"}       — Garmin 429
        {"status": "garmin_error", "type": "..."}
    """
    db = get_admin_client()
    creds_resp = (
        db.table("garmin_credentials")
        .select("oauth_tokens_encrypted")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    creds = cast("dict[str, Any] | None", creds_resp.data)
    if not creds or not creds.get("oauth_tokens_encrypted"):
        return {"status": "no_credentials"}

    cipher = TokenCipher()
    serialized = cipher.decrypt(creds["oauth_tokens_encrypted"].encode("ascii"))
    try:
        client = login_with_tokens(serialized)
    except (GarminAuthError, GarminConnectAuthenticationError):
        return {"status": "auth_failed"}

    try:
        user_profile = client.get_user_profile()
        max_metrics = client.get_max_metrics(date.today().isoformat())
    except GarminConnectTooManyRequestsError:
        log.warning("Garmin rate-limited /profile-sync for user=%s", user_id)
        return {"status": "rate_limited"}
    except Exception as e:
        log.exception("Garmin error during /profile-sync for user=%s", user_id)
        return {"status": "garmin_error", "type": type(e).__name__}

    row = _transform_profile(user_profile or {}, max_metrics or {})
    db.table("athlete_profiles").update(
        {**row, "garmin_synced_at": datetime.now(UTC).isoformat()}
    ).eq("user_id", user_id).execute()
    return {"status": "ok", "fetched": row}
