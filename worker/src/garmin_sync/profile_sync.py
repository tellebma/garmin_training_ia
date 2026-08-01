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


def _user_field(user_profile: Any, key: str) -> Any:
    """Read a user-settings field, whichever level Garmin nests it at.

    /userprofile-service/userprofile/user-settings nests everything under "userData"
    — garminconnect itself does `settings["userData"].get("measurementSystem")`. The
    previous version read at the top level only, so fc_max_bpm and ftp_watts were
    silently always None. Both levels are accepted so a payload change on either side
    cannot bring the bug back.
    """
    if not isinstance(user_profile, dict):
        return None
    nested = user_profile.get("userData")
    if isinstance(nested, dict) and nested.get(key) is not None:
        return nested.get(key)
    return user_profile.get(key)


_VO2MAX_KEYS = ("vo2MaxPreciseValue", "vo2MaxValue", "vo2MaxValueRunning")


def _vo2max_in(source: Any) -> float | None:
    """First usable VO2max value in a single object, `vo2MaxPreciseValue` preferred."""
    if not isinstance(source, dict):
        return None
    for key in _VO2MAX_KEYS:
        value = _as_float(source.get(key))
        if value:
            return value
    return None


def _vo2max_running(max_metrics: Any) -> float | None:
    """Extract running VO2max from the maxmet payload.

    /metrics-service/metrics/maxmet/daily/{start}/{end} is a date-RANGE endpoint: it
    answers a list of daily entries, each nesting the running values under "generic"
    (and cycling ones under "cycling"). The previous version called
    `.get("vo2MaxValueRunning")` on the payload as if it were a flat dict, which never
    matched.
    """
    entries: list[Any]
    if isinstance(max_metrics, list):
        entries = max_metrics
    elif isinstance(max_metrics, dict):
        entries = [max_metrics]
    else:
        return None

    for entry in reversed(entries):  # most recent day last in Garmin's ordering
        if not isinstance(entry, dict):
            continue
        value = _vo2max_in(entry.get("generic")) or _vo2max_in(entry)
        if value:
            return value
    return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _shape_of(payload: Any) -> str:
    """Describe a payload by its KEYS only — never its values.

    These payloads carry personal data (birth date, weight, sleep). Logging keys is
    enough to diagnose a shape change and keeps the logs free of personal values.
    """
    if isinstance(payload, dict):
        return f"dict({sorted(payload)})"
    if isinstance(payload, list):
        first = payload[0] if payload else None
        inner = f"dict({sorted(first)})" if isinstance(first, dict) else type(first).__name__
        return f"list[{len(payload)}] of {inner}"
    return type(payload).__name__


def _log_payload_shape(user_id: str, user_profile: Any, max_metrics: Any) -> None:
    """Record the real payload shapes so a mismatch is diagnosable from the logs.

    The fc_max/VMA bug went unnoticed for months because nothing ever showed what
    Garmin actually returned, and the unit tests mocked the shape the code assumed.
    """
    log.info(
        "profile-sync payload shapes user=%s user_profile=%s max_metrics=%s",
        user_id,
        _shape_of(user_profile),
        _shape_of(max_metrics),
    )


def _transform_profile(user_profile: Any, max_metrics: Any) -> dict[str, Any]:
    """Return only non-null perf fields. Keys with None values are EXCLUDED.

    Tolerant to unexpected payload shapes on purpose: this runs in the daily cron, and
    a Garmin response change must degrade to "no value written" rather than raise —
    `_transform_profile` is called outside the try/except guarding the API calls.
    """
    row: dict[str, Any] = {}
    ftp = _safe_int(_user_field(user_profile, "functionalThresholdPower"))
    if ftp is not None:
        row["ftp_watts"] = ftp
    vma = _vma_from_vo2max(_vo2max_running(max_metrics))
    if vma is not None:
        row["vma_kmh"] = vma
    fcmax = _safe_int(_user_field(user_profile, "userMaxHr"))
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

    _log_payload_shape(user_id, user_profile, max_metrics)

    row = _transform_profile(user_profile, max_metrics)
    if not row:
        # Attendu quand Garmin n'a rien : pas de capteur de puissance → pas de FTP.
        # Mais c'est aussi la signature d'un changement de forme de payload, et ce cas
        # est resté invisible des mois. On le rend explicite dans les logs.
        log.info("profile-sync: no perf field resolved for user=%s (see shape log)", user_id)
    if "fc_max_bpm" not in row:
        # fc_max_bpm est le pivot du calcul hrTSS (issue #120) : sans lui, le tier 2
        # est mort et le coach retombe sur le max de FC observé sur 90 j. Un WARNING
        # nommé rend le cas visible en prod au lieu d'un NULL silencieux.
        log.warning(
            "profile-sync: fc_max_bpm unresolved for user=%s — userMaxHr absent from "
            "Garmin payload (see shape log); hrTSS will rely on the observed-HR fallback",
            user_id,
        )

    db.table("athlete_profiles").update(
        {**row, "garmin_synced_at": datetime.now(UTC).isoformat()}
    ).eq("user_id", user_id).execute()
    return {"status": "ok", "fetched": row}
