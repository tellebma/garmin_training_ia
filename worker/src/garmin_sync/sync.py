"""Per-user sync orchestration.

Calls each Garmin endpoint, transforms the payload, upserts into Supabase.

Resilience policy:
- Transient per-endpoint failures (500, timeout, parse errors) are swallowed so
  one bad endpoint does not abort the others.
- 429 (rate limit) and 401 (auth) are *global* signals from Garmin telling us
  to stop. Continuing the 90-day loop in that state would matraquer their API
  and likely get the worker's IP banned. So those abort the whole sync.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, cast

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from garmin_sync.supabase_client import get_admin_client
from garmin_sync.transformers.activities import transform_activity
from garmin_sync.transformers.body import transform_body
from garmin_sync.transformers.daily import transform_daily
from garmin_sync.transformers.hrv import transform_hrv
from garmin_sync.transformers.sleep import transform_sleep

log = logging.getLogger(__name__)


class GarminProfileIncompleteError(Exception):
    """Raised when the Garmin account is missing required profile data.

    The most common case is a brand-new Garmin account where the user hasn't
    set a display_name yet — every daily-summary endpoint requires it.
    """


# Errors that mean "stop the whole sync right now" — see module docstring.
_AbortSyncErrors = (
    GarminConnectTooManyRequestsError,
    GarminConnectAuthenticationError,
    GarminProfileIncompleteError,
)


def _is_display_name_error(exc: Exception) -> bool:
    """Detect the 'Display name is not set' error from python-garminconnect."""
    return "Display name is not set" in str(exc)


_USER_DATE_CONFLICT = "user_id,date"


SYNC_MODE_FULL = "full"
SYNC_MODE_SLEEP_ONLY = "sleep_only"
SYNC_MODE_ACTIVITIES_ONLY = "activities_only"
SyncMode = str  # one of the above constants


def sync_user_for_date_range(
    *,
    user_id: str,
    client: Garmin,
    start: date,
    end: date,
    mode: SyncMode = SYNC_MODE_FULL,
) -> None:
    """Sync the requested categories for a single user across [start, end].

    Modes:
        - "full"            (default) : activities + daily + sleep + hrv + body
        - "sleep_only"      : sleep + hrv + daily (HR baseline). For the morning cron.
        - "activities_only" : activities + daily. For the afternoon/evening cron.

    Raises ``GarminConnectTooManyRequestsError`` or
    ``GarminConnectAuthenticationError`` if Garmin signals a global stop —
    callers should treat that as fatal and back off.
    """
    db = get_admin_client()

    # Fetch athlete profile once for TSS computation
    profile_data: dict[str, Any] = {}
    try:
        profile_resp = (
            db.table("athlete_profiles")
            .select("ftp_watts, fc_max_bpm")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        profile_data = cast("dict[str, Any]", profile_resp.data or {})
    except Exception:
        log.warning("Could not fetch athlete profile for TSS for user=%s", user_id)

    ftp = profile_data.get("ftp_watts")
    fcmax = profile_data.get("fc_max_bpm")

    do_activities = mode in (SYNC_MODE_FULL, SYNC_MODE_ACTIVITIES_ONLY)
    do_sleep = mode in (SYNC_MODE_FULL, SYNC_MODE_SLEEP_ONLY)
    do_hrv = mode in (SYNC_MODE_FULL, SYNC_MODE_SLEEP_ONLY)
    do_body = mode == SYNC_MODE_FULL

    # Activities — one shot for the whole range
    if do_activities:
        try:
            activities = client.get_activities_by_date(start.isoformat(), end.isoformat())
            rows = [
                transform_activity(user_id=user_id, raw=a, ftp_watts=ftp, fc_max_bpm=fcmax)
                for a in activities
            ]
            if rows:
                db.table("activities").upsert(
                    rows, on_conflict="user_id,garmin_activity_id"
                ).execute()
        except _AbortSyncErrors:
            log.warning("activities sync aborted (rate-limit/auth) for user=%s", user_id)
            raise
        except Exception:
            log.exception("activities sync failed for user=%s", user_id)

    # Per-day metrics — daily always (HR baseline), then sleep / hrv / body as requested
    current = start
    while current <= end:
        iso = current.isoformat()
        _safe_upsert_daily(db, user_id, client, iso)
        if do_sleep:
            _safe_upsert_sleep(db, user_id, client, iso)
        if do_hrv:
            _safe_upsert_hrv(db, user_id, client, iso)
        if do_body:
            _safe_upsert_body(db, user_id, client, iso)
        current += timedelta(days=1)


def _safe_upsert_daily(db: Any, user_id: str, client: Garmin, iso_date: str) -> None:
    try:
        raw = client.get_stats(iso_date)
        if raw and raw.get("calendarDate"):
            db.table("daily_metrics").upsert(
                transform_daily(user_id=user_id, raw=raw), on_conflict=_USER_DATE_CONFLICT
            ).execute()
    except _AbortSyncErrors:
        raise
    except GarminConnectConnectionError as exc:
        if _is_display_name_error(exc):
            raise GarminProfileIncompleteError(str(exc)) from exc
        log.exception("daily sync failed user=%s date=%s", user_id, iso_date)
    except Exception:
        log.exception("daily sync failed user=%s date=%s", user_id, iso_date)


def _safe_upsert_sleep(db: Any, user_id: str, client: Garmin, iso_date: str) -> None:
    try:
        raw = client.get_sleep_data(iso_date)
        if raw and (raw.get("dailySleepDTO") or {}).get("calendarDate"):
            db.table("sleep").upsert(
                transform_sleep(user_id=user_id, raw=raw), on_conflict=_USER_DATE_CONFLICT
            ).execute()
    except _AbortSyncErrors:
        raise
    except Exception:
        log.exception("sleep sync failed user=%s date=%s", user_id, iso_date)


def _safe_upsert_hrv(db: Any, user_id: str, client: Garmin, iso_date: str) -> None:
    try:
        raw = client.get_hrv_data(iso_date)
        summary = (raw or {}).get("hrvSummary") or {}
        if summary.get("calendarDate"):
            db.table("hrv").upsert(
                transform_hrv(user_id=user_id, raw=raw), on_conflict=_USER_DATE_CONFLICT
            ).execute()
    except _AbortSyncErrors:
        raise
    except Exception:
        log.exception("hrv sync failed user=%s date=%s", user_id, iso_date)


def _safe_upsert_body(db: Any, user_id: str, client: Garmin, iso_date: str) -> None:
    try:
        # Garmin returns {"dateWeightList": [...], "totalAverage": {...}} — iterate the inner list.
        # Accept legacy list shape too (defensive, in case lib version changes).
        payload = client.get_body_composition(iso_date, iso_date)
        weigh_ins = (
            payload.get("dateWeightList", []) if isinstance(payload, dict) else (payload or [])
        )
        for raw in weigh_ins:
            if isinstance(raw, dict) and raw.get("calendarDate"):
                db.table("body_composition").upsert(
                    transform_body(user_id=user_id, raw=raw), on_conflict=_USER_DATE_CONFLICT
                ).execute()
    except _AbortSyncErrors:
        raise
    except Exception:
        log.exception("body sync failed user=%s date=%s", user_id, iso_date)
