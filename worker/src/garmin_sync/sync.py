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
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from garmin_sync.supabase_client import get_admin_client
from garmin_sync.transformers.activities import transform_activity
from garmin_sync.transformers.body import transform_body
from garmin_sync.transformers.daily import transform_daily
from garmin_sync.transformers.hrv import transform_hrv
from garmin_sync.transformers.sleep import transform_sleep

log = logging.getLogger(__name__)

# Errors that mean "stop the whole sync right now" — see module docstring.
_AbortSyncErrors = (GarminConnectTooManyRequestsError, GarminConnectAuthenticationError)

_USER_DATE_CONFLICT = "user_id,date"


def sync_user_for_date_range(
    *,
    user_id: str,
    client: Garmin,
    start: date,
    end: date,
) -> None:
    """Sync all categories for a single user across [start, end] (inclusive).

    Raises ``GarminConnectTooManyRequestsError`` or
    ``GarminConnectAuthenticationError`` if Garmin signals a global stop —
    callers should treat that as fatal and back off.
    """
    db = get_admin_client()

    # Activities — one shot for the whole range
    try:
        activities = client.get_activities_by_date(start.isoformat(), end.isoformat())
        rows = [transform_activity(user_id=user_id, raw=a) for a in activities]
        if rows:
            db.table("activities").upsert(rows, on_conflict="user_id,garmin_activity_id").execute()
    except _AbortSyncErrors:
        log.warning("activities sync aborted (rate-limit/auth) for user=%s", user_id)
        raise
    except Exception:
        log.exception("activities sync failed for user=%s", user_id)

    # Per-day metrics — daily, sleep, hrv, body
    current = start
    while current <= end:
        iso = current.isoformat()
        _safe_upsert_daily(db, user_id, client, iso)
        _safe_upsert_sleep(db, user_id, client, iso)
        _safe_upsert_hrv(db, user_id, client, iso)
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
        if raw and raw.get("calendarDate"):
            db.table("hrv").upsert(
                transform_hrv(user_id=user_id, raw=raw), on_conflict=_USER_DATE_CONFLICT
            ).execute()
    except _AbortSyncErrors:
        raise
    except Exception:
        log.exception("hrv sync failed user=%s date=%s", user_id, iso_date)


def _safe_upsert_body(db: Any, user_id: str, client: Garmin, iso_date: str) -> None:
    try:
        items = client.get_body_composition(iso_date, iso_date)
        for raw in items or []:
            if raw.get("calendarDate"):
                db.table("body_composition").upsert(
                    transform_body(user_id=user_id, raw=raw), on_conflict=_USER_DATE_CONFLICT
                ).execute()
    except _AbortSyncErrors:
        raise
    except Exception:
        log.exception("body sync failed user=%s date=%s", user_id, iso_date)
