"""Match GPS activities against cols by proximity to the summit point.

Coverage model: each activity's own bounding box drives both the Overpass fetch
(so the shared `cols` table gains the cols actually ridden past, wherever they
are) and the DB query used for matching. The home-centred 50km Overpass refresh
(`refresh_nearby_cols`) still exists separately to populate not-yet-climbed cols
for the stats widget — but matching itself no longer depends on home at all.
"""

from __future__ import annotations

import time
from typing import Any, cast

from garmin_sync.coach.geo import haversine_m
from garmin_sync.coach.overpass import fetch_cols_in_bbox
from garmin_sync.supabase_client import get_admin_client

DbRows = list[dict[str, Any]]
Bbox = tuple[float, float, float, float]  # (south, west, north, east)

_CROSSING_THRESHOLD_M = 150.0
_SAMPLE_PAGE_SIZE = 1000
_MAX_SAMPLE_PAGES = 20  # 20k samples ceiling — generous even for multi-hour rides
# Marge ajoutée au bbox d'activité pour la couverture Overpass (~5.5 km) : large
# exprès, pour que les sorties successives dans la même zone réutilisent la
# couverture déjà fetchée pendant un backfill au lieu de re-frapper Overpass.
_COVERAGE_PAD_DEG = 0.05
# Marge ajoutée au bbox d'activité pour charger les cols candidats depuis la DB
# (~550 m) : doit seulement dépasser le seuil de franchissement de 150 m.
_MATCH_PAD_DEG = 0.005
# Pause de politesse entre deux appels Overpass d'un même run (backfill).
# 1 s s'est avéré trop court en prod (429 dès la 2e zone) — Overpass n'accorde
# que quelques slots par IP et pénalise les rafales.
_OVERPASS_COOLDOWN_S = 5.0


def recompute_col_crossings(user_id: str) -> None:
    """Detect col crossings on GPS activities synced since the last run.

    Processes activities with `start_time` after `col_matching_cursor` (or the full
    history on first run). For each activity: computes the track's bounding box,
    ensures Overpass coverage for that box (so cols ridden far from home exist in
    the shared `cols` table), then matches the full-resolution `activity_samples`
    against the cols inside the box and upserts one `col_crossings` row per
    (col, activity) pair within 150m. Advances the cursor to the latest
    successfully processed activity's `start_time`; if an activity fails (e.g.
    Overpass down), the cursor stops just before it so the next run retries it,
    and the error propagates to the cron caller.
    """
    db = get_admin_client()

    cursor = _fetch_cursor(db, user_id)
    activities = _fetch_pending_activities(db, user_id, cursor)
    if not activities:
        return

    fetched_bboxes: list[Bbox] = []
    max_start_time: str | None = cursor
    failure: Exception | None = None
    for activity in activities:
        start_time = activity["start_time"]
        try:
            _process_activity(db, user_id=user_id, activity=activity, fetched_bboxes=fetched_bboxes)
        except Exception as exc:
            failure = exc
            break
        if max_start_time is None or start_time > max_start_time:
            max_start_time = start_time

    if max_start_time is not None and max_start_time != cursor:
        db.table("athlete_profiles").update({"col_matching_cursor": max_start_time}).eq(
            "user_id", user_id
        ).execute()

    if failure is not None:
        raise failure


def _fetch_cursor(db: Any, user_id: str) -> str | None:
    profile_response = (
        db.table("athlete_profiles")
        .select("col_matching_cursor")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    profile = cast("dict[str, Any] | None", profile_response.data if profile_response else None)
    return profile.get("col_matching_cursor") if profile else None


def _fetch_pending_activities(db: Any, user_id: str, cursor: str | None) -> DbRows:
    query = (
        db.table("activities")
        .select("garmin_activity_id, start_time")
        .eq("user_id", user_id)
        .not_.is_("route_polyline", "null")
    )
    if cursor:
        query = query.gt("start_time", cursor)
    return cast(DbRows, query.order("start_time").execute().data or [])


def _fetch_all_samples(db: Any, user_id: str, activity_id: int) -> DbRows:
    """Fetch every GPS sample for one activity, paginating past PostgREST's row cap.

    A single `.limit(N)` request is NOT sufficient here: Supabase's REST API enforces
    its own server-side max-rows setting (commonly 1000) that silently overrides a
    higher client-requested limit — confirmed in production (2026-07-09): a 1730-sample
    activity returned only 1000 rows for a `.limit(5000)` request, truncating the
    second half of the ride and causing a real, silent missed crossing. `.range()`
    paging in fixed-size pages, ordered by `sample_index`, is the only way to
    guarantee every sample is read regardless of that server cap.
    """
    samples: DbRows = []
    for page in range(_MAX_SAMPLE_PAGES):
        start = page * _SAMPLE_PAGE_SIZE
        chunk = cast(
            DbRows,
            db.table("activity_samples")
            .select("latitude, longitude")
            .eq("user_id", user_id)
            .eq("garmin_activity_id", activity_id)
            .not_.is_("latitude", "null")
            .order("sample_index")
            .range(start, start + _SAMPLE_PAGE_SIZE - 1)
            .execute()
            .data
            or [],
        )
        samples.extend(chunk)
        if len(chunk) < _SAMPLE_PAGE_SIZE:
            break
    return samples


def _samples_bbox(samples: DbRows) -> Bbox | None:
    lats = [float(sample["latitude"]) for sample in samples]
    lons = [float(sample["longitude"]) for sample in samples]
    if not lats:
        return None
    return (min(lats), min(lons), max(lats), max(lons))


def _pad_bbox(bbox: Bbox, pad_deg: float) -> Bbox:
    south, west, north, east = bbox
    return (south - pad_deg, west - pad_deg, north + pad_deg, east + pad_deg)


def _bbox_contains(outer: Bbox, inner: Bbox) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


def _ensure_overpass_coverage(bbox: Bbox, fetched_bboxes: list[Bbox]) -> None:
    """Fetch cols from Overpass for the activity's zone, once per zone per run."""
    if any(_bbox_contains(fetched, bbox) for fetched in fetched_bboxes):
        return
    if fetched_bboxes:
        time.sleep(_OVERPASS_COOLDOWN_S)
    padded = _pad_bbox(bbox, _COVERAGE_PAD_DEG)
    fetch_cols_in_bbox(*padded)
    fetched_bboxes.append(padded)


def _fetch_cols_in_bbox(db: Any, bbox: Bbox) -> DbRows:
    south, west, north, east = _pad_bbox(bbox, _MATCH_PAD_DEG)
    return cast(
        DbRows,
        db.table("cols")
        .select("id, latitude, longitude")
        .gte("latitude", south)
        .lte("latitude", north)
        .gte("longitude", west)
        .lte("longitude", east)
        .execute()
        .data
        or [],
    )


def _process_activity(
    db: Any, *, user_id: str, activity: dict[str, Any], fetched_bboxes: list[Bbox]
) -> None:
    # One `activity_samples` fetch per activity (N+1) is deliberate here, not an
    # oversight: batching all activities' samples into a single `.in_(...)` query
    # would multiply the row count returned per request, making it *more* likely to
    # hit PostgREST's server-side row cap and silently truncate — exactly the
    # correctness risk `_fetch_all_samples`'s pagination is designed to prevent.
    # This runs in the nightly background cron (not a user-facing request path), and
    # the cursor bounds it to a handful of new activities per user per day after the
    # first backfill run, so the extra round-trips are an acceptable trade for
    # guaranteed-complete, non-truncating reads.
    activity_id = activity["garmin_activity_id"]
    start_time = activity["start_time"]
    samples = _fetch_all_samples(db, user_id, activity_id)
    bbox = _samples_bbox(samples)
    if bbox is None:
        return
    _ensure_overpass_coverage(bbox, fetched_bboxes)
    cols = _fetch_cols_in_bbox(db, bbox)
    if not cols:
        return
    crossing_rows = _match_activity(
        user_id=user_id,
        activity_id=activity_id,
        start_time=start_time,
        samples=samples,
        cols=cols,
    )
    if crossing_rows:
        db.table("col_crossings").upsert(
            crossing_rows, on_conflict="user_id,col_id,garmin_activity_id"
        ).execute()


def _match_activity(
    *,
    user_id: str,
    activity_id: int,
    start_time: str,
    samples: DbRows,
    cols: DbRows,
) -> DbRows:
    rows: DbRows = []
    for col in cols:
        distances = (
            haversine_m(
                float(sample["latitude"]),
                float(sample["longitude"]),
                float(col["latitude"]),
                float(col["longitude"]),
            )
            for sample in samples
        )
        min_distance = min(distances, default=None)
        if min_distance is not None and min_distance <= _CROSSING_THRESHOLD_M:
            rows.append(
                {
                    "user_id": user_id,
                    "col_id": col["id"],
                    "garmin_activity_id": activity_id,
                    "crossed_at": start_time,
                    "min_distance_m": round(min_distance, 1),
                }
            )
    return rows
