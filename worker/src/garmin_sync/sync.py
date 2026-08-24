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
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from garmin_sync.coach.race_tagging import tag_races_for_user
from garmin_sync.config import get_settings
from garmin_sync.supabase_client import get_admin_client
from garmin_sync.transformers.activities import transform_activity, transform_activity_samples
from garmin_sync.transformers.body import transform_body
from garmin_sync.transformers.daily import transform_daily
from garmin_sync.transformers.hrv import transform_hrv
from garmin_sync.transformers.route import build_route_polyline
from garmin_sync.transformers.segments import (
    extract_child_activity_ids,
    transform_activity_segment,
)
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

# Une activité GPS fait ~2000 samples ; un upsert unique dépasse le Mo de payload.
_SAMPLE_UPSERT_CHUNK = 500

# Sports d'une activité multisport : `brick` après normalisation, plus les valeurs
# brutes déjà en base avant que `multi_sport` ne soit reconnu.
_MULTISPORT_SPORTS = ("brick", "multi_sport", "multisport", "transition")

# Décompositions multisport traitées par run : chacune coûte 1 + N appels Garmin.
_SEGMENTS_BACKFILL_BATCH = 3


SYNC_MODE_FULL = "full"
SYNC_MODE_SLEEP_ONLY = "sleep_only"
SYNC_MODE_ACTIVITIES_ONLY = "activities_only"
SyncMode = str  # one of the above constants


_MODE_FLAGS: dict[str, tuple[bool, bool, bool, bool]] = {
    # (do_activities, do_sleep, do_hrv, do_body)
    SYNC_MODE_FULL: (True, True, True, True),
    SYNC_MODE_SLEEP_ONLY: (False, True, True, False),
    SYNC_MODE_ACTIVITIES_ONLY: (True, False, False, False),
}


def _load_athlete_profile(db: Any, user_id: str) -> dict[str, Any]:
    """Fetch athlete profile for TSS computation. Never raises."""
    try:
        profile_resp = (
            db.table("athlete_profiles")
            .select("ftp_watts, fc_max_bpm")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return cast("dict[str, Any]", profile_resp.data or {})
    except Exception:
        log.warning("Could not fetch athlete profile for TSS for user=%s", user_id)
        return {}


def _sync_activities(
    db: Any, user_id: str, client: Garmin, start: date, end: date, profile: dict[str, Any]
) -> None:
    """One-shot activities pull. Raises on _AbortSyncErrors so caller can back off."""
    ftp = profile.get("ftp_watts")
    fcmax = profile.get("fc_max_bpm")
    try:
        activities = client.get_activities_by_date(start.isoformat(), end.isoformat())
        rows = [
            transform_activity(user_id=user_id, raw=a, ftp_watts=ftp, fc_max_bpm=fcmax)
            for a in activities
        ]
        if rows:
            db.table("activities").upsert(rows, on_conflict="user_id,garmin_activity_id").execute()
            _sync_missing_activity_samples(db, user_id, client, rows)
        _sync_gps_backfill(db, user_id, client, get_settings().gps_backfill_batch)
        _sync_activity_segments(db, user_id, client, _SEGMENTS_BACKFILL_BATCH)
        # E23.1 — rattache l'activité du jour J à sa course. Borné à la fenêtre
        # synchronisée ; `tag_races_for_user` avale ses propres erreurs.
        tag_races_for_user(db, user_id, start_date=start.isoformat(), end_date=end.isoformat())
    except _AbortSyncErrors:
        log.warning("activities sync aborted (rate-limit/auth) for user=%s", user_id)
        raise
    except Exception:
        log.exception("activities sync failed for user=%s", user_id)


def _sync_missing_activity_samples(
    db: Any,
    user_id: str,
    client: Garmin,
    activity_rows: list[dict[str, Any]],
) -> None:
    """Fetch chart samples only for activities that do not have samples yet."""
    activity_ids = [
        int(row["garmin_activity_id"])
        for row in activity_rows
        if row.get("garmin_activity_id") is not None
    ]
    if not activity_ids:
        return

    existing = _sampled_activity_ids(db, user_id, activity_ids)
    for activity_id in activity_ids:
        if activity_id in existing:
            continue
        try:
            _persist_samples_and_route(db, user_id, activity_id, client)
        except _AbortSyncErrors:
            raise
        except Exception:
            log.exception("activity samples sync failed user=%s activity=%s", user_id, activity_id)


def _persist_samples_and_route(db: Any, user_id: str, activity_id: int, client: Garmin) -> None:
    """Fetch activity details, upsert samples, and write the downsampled route polyline.

    ALWAYS records that GPS was checked: activities with no usable GPS get
    ``route_polyline = []`` (empty-array sentinel) so they become non-NULL and
    are excluded from ``_activities_missing_gps`` on subsequent runs.  A failed
    or malformed fetch (non-dict) remains NULL and will be retried later.
    """
    raw_details = client.get_activity_details(str(activity_id))
    if not isinstance(raw_details, dict):
        return
    samples = transform_activity_samples(
        user_id=user_id,
        garmin_activity_id=activity_id,
        raw_details=raw_details,
    )
    for start_idx in range(0, len(samples), _SAMPLE_UPSERT_CHUNK):
        db.table("activity_samples").upsert(
            samples[start_idx : start_idx + _SAMPLE_UPSERT_CHUNK],
            on_conflict="user_id,garmin_activity_id,sample_index",
        ).execute()
    polyline = build_route_polyline(samples) if samples else None
    # Write the polyline (real route) or [] sentinel (no usable GPS) so the
    # activity is marked as "GPS-checked" and won't be re-selected by backfill.
    db.table("activities").update({"route_polyline": polyline if polyline is not None else []}).eq(
        "user_id", user_id
    ).eq("garmin_activity_id", activity_id).execute()


def _sampled_activity_ids(db: Any, user_id: str, activity_ids: list[int]) -> set[int]:
    """Activities whose GPS details were already fetched (route_polyline non-NULL).

    Reads `activities` (1 ligne par activité, bornée par la fenêtre de sync) et
    PAS `activity_samples` : cette table fait ~2000 lignes par activité GPS et le
    cap serveur silencieux de PostgREST (~1000 lignes) tronquait la réponse — une
    activité déjà samplée disparaissait du set et était re-fetchée chez Garmin
    (risque de rate-limit/ban) puis ré-upsertée à chaque cron. La sentinelle
    route_polyline (posée par `_persist_samples_and_route`, y compris `[]` pour
    les activités sans GPS) couvre aussi les activités indoor, qui étaient
    re-fetchées à chaque run faute de samples.
    """
    try:
        resp = (
            db.table("activities")
            .select("garmin_activity_id")
            .eq("user_id", user_id)
            .in_("garmin_activity_id", activity_ids)
            .not_.is_("route_polyline", "null")
            .execute()
        )
    except Exception:
        log.exception("sampled activities lookup failed user=%s", user_id)
        return set()
    rows = resp.data if resp else None
    if not isinstance(rows, list):
        return set()
    return {
        int(row["garmin_activity_id"])
        for row in rows
        if isinstance(row, dict) and row.get("garmin_activity_id") is not None
    }


def _sync_gps_backfill(db: Any, user_id: str, client: Garmin, limit: int) -> None:
    """Backfill GPS for already-synced activities lacking a route polyline (throttled)."""
    if limit <= 0:
        return
    for activity_id in _activities_missing_gps(db, user_id, limit):
        try:
            _persist_samples_and_route(db, user_id, activity_id, client)
        except _AbortSyncErrors:
            raise
        except Exception:
            log.exception("gps backfill failed user=%s activity=%s", user_id, activity_id)


def _activities_missing_gps(db: Any, user_id: str, limit: int) -> list[int]:
    try:
        resp = (
            db.table("activities")
            .select("garmin_activity_id")
            .eq("user_id", user_id)
            .is_("route_polyline", "null")
            .order("start_time", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception:
        log.exception("gps backfill lookup failed user=%s", user_id)
        return []
    rows = resp.data if resp else None
    if not isinstance(rows, list):
        return []
    return [
        int(row["garmin_activity_id"])
        for row in rows
        if isinstance(row, dict) and row.get("garmin_activity_id") is not None
    ]


def _sync_activity_segments(db: Any, user_id: str, client: Garmin, limit: int) -> None:
    """Décompose les activités multisport en segments par discipline (throttlé).

    Sert à la fois les nouvelles activités et l'historique : la sélection porte sur
    `segments_checked_at is null`, qui est renseigné même quand Garmin ne publie
    aucun enfant — sinon la même activité serait ré-interrogée à chaque cron.
    """
    if limit <= 0:
        return
    for activity_id in _multisport_activities_without_segments(db, user_id, limit):
        try:
            _persist_activity_segments(db, user_id, activity_id, client)
        except _AbortSyncErrors:
            raise
        except Exception:
            log.exception("segments sync failed user=%s activity=%s", user_id, activity_id)


def _persist_activity_segments(db: Any, user_id: str, activity_id: int, client: Garmin) -> None:
    """Récupère les activités enfants d'un multisport et écrit ses segments."""
    parent = client.get_activity(str(activity_id))
    child_ids = extract_child_activity_ids(parent if isinstance(parent, dict) else {})
    rows = [
        transform_activity_segment(
            user_id=user_id,
            parent_activity_id=activity_id,
            segment_index=index,
            raw=child,
        )
        for index, child in enumerate(_fetch_children(client, child_ids))
    ]
    if rows:
        db.table("activity_segments").upsert(
            rows, on_conflict="user_id,garmin_activity_id,segment_index"
        ).execute()
    # Marqueur écrit dans tous les cas, y compris sans enfant exploitable.
    db.table("activities").update({"segments_checked_at": datetime.now(UTC).isoformat()}).eq(
        "user_id", user_id
    ).eq("garmin_activity_id", activity_id).execute()


def _fetch_children(client: Garmin, child_ids: list[int]) -> list[dict[str, Any]]:
    """Résumé de chaque activité enfant. Un enfant illisible est ignoré, pas fatal."""
    children: list[dict[str, Any]] = []
    for child_id in child_ids:
        try:
            child = client.get_activity(str(child_id))
        except _AbortSyncErrors:
            raise
        except Exception:
            log.exception("multisport child fetch failed activity=%s", child_id)
            continue
        if isinstance(child, dict):
            children.append(child)
    return children


def _multisport_activities_without_segments(db: Any, user_id: str, limit: int) -> list[int]:
    try:
        resp = (
            db.table("activities")
            .select("garmin_activity_id")
            .eq("user_id", user_id)
            .in_("sport", list(_MULTISPORT_SPORTS))
            .is_("segments_checked_at", "null")
            .order("start_time", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception:
        log.exception("multisport segments lookup failed user=%s", user_id)
        return []
    rows = resp.data if resp else None
    if not isinstance(rows, list):
        return []
    return [
        int(row["garmin_activity_id"])
        for row in rows
        if isinstance(row, dict) and row.get("garmin_activity_id") is not None
    ]


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
    profile = _load_athlete_profile(db, user_id)

    do_activities, do_sleep, do_hrv, do_body = _MODE_FLAGS.get(mode, _MODE_FLAGS[SYNC_MODE_FULL])

    if do_activities:
        _sync_activities(db, user_id, client, start, end, profile)

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
