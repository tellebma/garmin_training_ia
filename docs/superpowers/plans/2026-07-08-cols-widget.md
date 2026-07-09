# Widget « Mes cols » Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Mes cols" widget to `/stats` listing the mountain passes (cols) within
50km of the user's home, with a per-col count of how many activities crossed it.

**Architecture:** A daily worker pipeline (3 pure Python functions wired into the
existing post-sync cron hook) computes the user's home location from GPS activity
history, refreshes a shared `cols` reference table from OpenStreetMap's Overpass API,
and matches new activities against nearby cols by GPS proximity, persisting results to
a new `col_crossings` table. The Next.js stats page reads these tables directly and
renders a table, in its own `<Suspense>` boundary so it never blocks the rest of the
page.

**Tech Stack:** Python 3.12 / FastAPI worker (supabase-py, httpx), Next.js 15 App
Router / TypeScript (Supabase JS, Vitest), Supabase Postgres (new migration).

## Global Constraints

- Crossing detection radius: activity GPS track passes within **150 m** of a col's
  summit point.
- Cols search radius: **50 km** around the computed home location.
- Overpass refresh trigger: cache absent, OR older than **30 days**, OR home moved more
  than **5 km** since the last successful fetch.
- Home location = **median** (not mean) of the first GPS point (`route_polyline[0]`) of
  every GPS activity, recomputed on every cron run.
- Reuse the **existing** `athlete_profiles.lat` / `athlete_profiles.lon` columns for the
  computed home location — do not add new columns for this.
- At most **1 crossing counted per activity per col** (no multi-pass detection within a
  single activity).
- All activity types with GPS data count (no sport filter).
- The stats widget lists **all** cols in radius, including those crossed 0 times.
- The cols widget's data fetch is **isolated from** the main `Promise.all` in
  `CockpitBody` (`app/(app)/stats/page.tsx`) — own async component, own `<Suspense>` +
  skeleton, mounted as a sibling so it fetches in parallel and never delays the rest of
  the page.
- New worker functions let exceptions propagate naturally (no internal try/except) —
  `_run_post_sync_recomputes` in `cron.py` wraps each call in `try/except` +
  `log.exception` + `capture()`, matching the existing pattern for
  `recompute_daily_state` / `recompute_recovery_baselines`. Do not duplicate error
  handling inside the new modules.
- mypy strict mode is on for the worker — every new function needs full type
  annotations.
- Work happens in this git worktree (`.claude/worktrees/cols-widget`, branch
  `worktree-cols-widget`) — do not touch the main checkout. Rename the branch to
  `feat/cols-widget` before opening the PR (see final task).
- After all tasks pass and before opening the PR, run a `/vqo` (Vibecoding Quality
  Orchestrator) pass over the diff and fix everything raised until every category
  scores **9.5+** (owner instruction, 2026-07-08) — see Task 10.

---

### Task 1: Migration — `cols`, `col_crossings`, `athlete_profiles` columns

**Files:**
- Create: `supabase/migrations/20260708000000_cols_and_crossings.sql`

**Interfaces:**
- Produces: tables `public.cols` (`id`, `osm_id`, `name`, `latitude`, `longitude`,
  `elevation_m`, `fetched_at`) and `public.col_crossings` (`user_id`, `col_id`,
  `garmin_activity_id`, `crossed_at`, `min_distance_m`); new columns on
  `athlete_profiles`: `home_computed_at`, `cols_cache_updated_at`,
  `cols_cache_home_lat`, `cols_cache_home_lon`, `col_matching_cursor`.

- [ ] **Step 1: Write the migration**

```sql
-- Référentiel global des cols (partagé entre users, alimenté depuis OSM Overpass).
create table public.cols (
  id uuid primary key default gen_random_uuid(),
  osm_id bigint not null unique,
  name text not null,
  latitude numeric(9, 6) not null
    check (latitude between -90 and 90),
  longitude numeric(9, 6) not null
    check (longitude between -180 and 180),
  elevation_m integer,
  fetched_at timestamptz not null default now()
);

alter table public.cols enable row level security;

create policy "authenticated users read cols"
  on public.cols for select
  to authenticated
  using (true);

comment on table public.cols is
  'Référentiel global des cols (mountain_pass OSM), alimenté par le worker via Overpass API. Écriture service-role uniquement.';

-- Franchissements détectés par activité (au plus 1 par activité + col).
create table public.col_crossings (
  user_id uuid not null references auth.users(id) on delete cascade,
  col_id uuid not null references public.cols(id) on delete cascade,
  garmin_activity_id bigint not null,
  crossed_at timestamptz not null,
  min_distance_m numeric(6, 1) not null,
  primary key (user_id, col_id, garmin_activity_id)
);

create index col_crossings_user_col_idx
  on public.col_crossings (user_id, col_id);

alter table public.col_crossings enable row level security;

create policy "users read own col crossings"
  on public.col_crossings for select
  using (auth.uid() = user_id);

comment on table public.col_crossings is
  'Franchissements de cols détectés par proximité GPS (<=150m), calculés par le worker. Au plus 1 ligne par (user, col, activité).';

-- Domicile calculé + état du pipeline cols, sur athlete_profiles.
-- Note: `lat`/`lon` existent déjà (schéma E1) et n'étaient utilisés nulle part —
-- réutilisés ici pour le domicile calculé plutôt que d'ajouter des colonnes redondantes.
alter table public.athlete_profiles
  add column home_computed_at timestamptz,
  add column cols_cache_updated_at timestamptz,
  add column cols_cache_home_lat numeric(9, 6),
  add column cols_cache_home_lon numeric(9, 6),
  add column col_matching_cursor timestamptz;
```

- [ ] **Step 2: Apply the migration to the dev Supabase project**

Run via the Supabase MCP tool (`mcp__supabase__apply_migration`, project
`peiyrqplymdlmlpsbqzu`) with `name: "cols_and_crossings"` and the SQL above — ask the
user for explicit confirmation first since this touches the shared dev database. This
lets the worker/frontend tasks below run against real tables during manual QA; CI
auto-applies the same file to prod on merge (E17).

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260708000000_cols_and_crossings.sql
git commit -m "feat(db): cols + col_crossings tables for the cols widget"
```

---

### Task 2: Worker — `haversine_m` geo helper

**Files:**
- Create: `worker/src/garmin_sync/coach/geo.py`
- Test: `worker/tests/coach/test_geo.py`

**Interfaces:**
- Produces: `haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float`
  — great-circle distance in meters. Consumed by Tasks 4 and 5.

- [ ] **Step 1: Write the failing tests**

```python
# worker/tests/coach/test_geo.py
from __future__ import annotations

from garmin_sync.coach.geo import haversine_m


def test_haversine_zero_distance_for_identical_points() -> None:
    assert haversine_m(45.0, 6.0, 45.0, 6.0) == 0.0


def test_haversine_known_distance_paris_lyon() -> None:
    # Paris (48.8566, 2.3522) -> Lyon (45.7640, 4.8357) is ~391 km great-circle.
    distance = haversine_m(48.8566, 2.3522, 45.7640, 4.8357)
    assert 385_000 < distance < 400_000


def test_haversine_small_distance_near_150m_threshold() -> None:
    # ~0.00135 deg of latitude at the equator-ish scale is close to 150m.
    distance = haversine_m(45.0, 6.0, 45.00135, 6.0)
    assert 140 < distance < 160
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/coach/test_geo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'garmin_sync.coach.geo'`

- [ ] **Step 3: Write the implementation**

```python
# worker/src/garmin_sync/coach/geo.py
"""Shared geographic distance helper for the cols pipeline."""

from __future__ import annotations

import math

_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two lat/lon points (degrees)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/coach/test_geo.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add worker/src/garmin_sync/coach/geo.py worker/tests/coach/test_geo.py
git commit -m "feat(worker): haversine distance helper for cols matching"
```

---

### Task 3: Worker — `compute_home_location`

**Files:**
- Create: `worker/src/garmin_sync/coach/home_location.py`
- Test: `worker/tests/coach/test_home_location.py`

**Interfaces:**
- Consumes: `garmin_sync.supabase_client.get_admin_client()`.
- Produces: `compute_home_location(user_id: str) -> tuple[float, float] | None` —
  returns `(lat, lon)` on success, `None` if the user has no GPS activity (columns left
  untouched). Consumed by Task 6 (cron wiring).

- [ ] **Step 1: Write the failing tests**

```python
# worker/tests/coach/test_home_location.py
from __future__ import annotations

from typing import Any

import garmin_sync.coach.home_location as mod


class _FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.updated: dict[str, Any] | None = None

    @property
    def not_(self) -> "_FakeQuery":
        return self

    def select(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def eq(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def is_(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def update(self, values: dict[str, Any]) -> "_FakeQuery":
        self.updated = values
        return self

    def execute(self) -> Any:
        class _R:
            data = self._rows

        return _R()


class _FakeDb:
    def __init__(self, activities_rows: list[dict[str, Any]]) -> None:
        self.activities_query = _FakeQuery(activities_rows)
        self.profile_query = _FakeQuery([])

    def table(self, name: str) -> _FakeQuery:
        if name == "activities":
            return self.activities_query
        if name == "athlete_profiles":
            return self.profile_query
        raise AssertionError(f"unexpected table {name}")


def test_compute_home_location_uses_median_of_start_points(monkeypatch: Any) -> None:
    rows = [
        {"route_polyline": [[6.0, 45.0], [6.1, 45.1]]},
        {"route_polyline": [[6.2, 45.2], [6.3, 45.3]]},
        {"route_polyline": [[6.4, 45.4]]},
    ]
    db = _FakeDb(rows)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    result = mod.compute_home_location("user-1")

    assert result == (45.2, 6.2)
    assert db.profile_query.updated is not None
    assert db.profile_query.updated["lat"] == 45.2
    assert db.profile_query.updated["lon"] == 6.2
    assert db.profile_query.updated["home_computed_at"] is not None


def test_compute_home_location_ignores_malformed_polylines(monkeypatch: Any) -> None:
    rows = [
        {"route_polyline": [[6.0, 45.0]]},
        {"route_polyline": []},
        {"route_polyline": [[6.2]]},
        {"route_polyline": None},
    ]
    db = _FakeDb(rows)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    result = mod.compute_home_location("user-1")

    assert result == (45.0, 6.0)


def test_compute_home_location_returns_none_without_gps_activities(monkeypatch: Any) -> None:
    db = _FakeDb([])
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    result = mod.compute_home_location("user-1")

    assert result is None
    assert db.profile_query.updated is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/coach/test_home_location.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'garmin_sync.coach.home_location'`

- [ ] **Step 3: Write the implementation**

```python
# worker/src/garmin_sync/coach/home_location.py
"""Compute the user's home location from the median of GPS activity start points."""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from typing import Any, cast

from garmin_sync.supabase_client import get_admin_client


def compute_home_location(user_id: str) -> tuple[float, float] | None:
    """Recompute and persist the user's home (lat, lon) from GPS activity history.

    Uses the first point of each activity's `route_polyline` (already downsampled at
    sync time). Writes `lat`, `lon`, `home_computed_at` on `athlete_profiles`. Returns
    the computed `(lat, lon)`, or `None` if the user has no GPS activity yet — in that
    case the profile is left untouched.
    """
    db = get_admin_client()
    rows = cast(
        "list[dict[str, Any]]",
        db.table("activities")
        .select("route_polyline")
        .eq("user_id", user_id)
        .not_.is_("route_polyline", "null")
        .execute()
        .data
        or [],
    )

    lats: list[float] = []
    lons: list[float] = []
    for row in rows:
        polyline = row.get("route_polyline")
        if not isinstance(polyline, list) or not polyline:
            continue
        first = polyline[0]
        if not isinstance(first, list) or len(first) < 2:
            continue
        lons.append(float(first[0]))
        lats.append(float(first[1]))

    if not lats:
        return None

    home_lat = statistics.median(lats)
    home_lon = statistics.median(lons)

    db.table("athlete_profiles").update(
        {
            "lat": home_lat,
            "lon": home_lon,
            "home_computed_at": datetime.now(UTC).isoformat(),
        }
    ).eq("user_id", user_id).execute()

    return home_lat, home_lon
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/coach/test_home_location.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add worker/src/garmin_sync/coach/home_location.py worker/tests/coach/test_home_location.py
git commit -m "feat(worker): compute home location from GPS activity median"
```

---

### Task 4: Worker — `refresh_nearby_cols` (Overpass client)

**Files:**
- Create: `worker/src/garmin_sync/coach/overpass.py`
- Test: `worker/tests/coach/test_overpass.py`

**Interfaces:**
- Consumes: `garmin_sync.coach.geo.haversine_m`,
  `garmin_sync.supabase_client.get_admin_client()`.
- Produces: `refresh_nearby_cols(user_id: str, home_lat: float, home_lon: float) ->
  None`. Consumed by Task 6.

- [ ] **Step 1: Write the failing tests**

```python
# worker/tests/coach/test_overpass.py
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import garmin_sync.coach.overpass as mod


class _FakeQuery:
    def __init__(self, rows: Any) -> None:
        self._rows = rows
        self.upserted: list[dict[str, Any]] | None = None
        self.updated: dict[str, Any] | None = None

    def select(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def eq(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def maybe_single(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def upsert(self, rows: list[dict[str, Any]], **_k: Any) -> "_FakeQuery":
        self.upserted = rows
        return self

    def update(self, values: dict[str, Any]) -> "_FakeQuery":
        self.updated = values
        return self

    def execute(self) -> Any:
        class _R:
            data = self._rows

        return _R()


class _FakeDb:
    def __init__(self, profile_row: dict[str, Any] | None) -> None:
        self.profile_query = _FakeQuery(profile_row)
        self.cols_query = _FakeQuery(None)

    def table(self, name: str) -> _FakeQuery:
        if name == "athlete_profiles":
            return self.profile_query
        if name == "cols":
            return self.cols_query
        raise AssertionError(f"unexpected table {name}")


_OVERPASS_RESPONSE = {
    "elements": [
        {
            "type": "node",
            "id": 123,
            "lat": 45.05,
            "lon": 6.05,
            "tags": {"mountain_pass": "yes", "name": "Col du Truc", "ele": "1850"},
        },
        {
            "type": "node",
            "id": 456,
            "lat": 45.06,
            "lon": 6.06,
            "tags": {"mountain_pass": "yes"},
        },
    ]
}


def test_refresh_skips_when_cache_is_fresh_and_home_unchanged(monkeypatch: Any) -> None:
    db = _FakeDb(
        {
            "cols_cache_updated_at": "2026-07-01T00:00:00+00:00",
            "cols_cache_home_lat": 45.0,
            "cols_cache_home_lon": 6.0,
        }
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    monkeypatch.setattr(mod, "httpx", httpx_mock)
    # "now" close enough to 2026-07-01 that 30 days haven't passed.
    monkeypatch.setattr(mod, "_now", lambda: mod.datetime(2026, 7, 8, tzinfo=mod.UTC))

    mod.refresh_nearby_cols("user-1", 45.0001, 6.0001)

    httpx_mock.get.assert_not_called()
    assert db.cols_query.upserted is None


def test_refresh_fetches_and_upserts_when_cache_is_stale(monkeypatch: Any) -> None:
    db = _FakeDb(
        {
            "cols_cache_updated_at": "2026-01-01T00:00:00+00:00",
            "cols_cache_home_lat": 45.0,
            "cols_cache_home_lon": 6.0,
        }
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.json.return_value = _OVERPASS_RESPONSE
    monkeypatch.setattr(mod, "httpx", httpx_mock)
    monkeypatch.setattr(mod, "_now", lambda: mod.datetime(2026, 7, 8, tzinfo=mod.UTC))

    mod.refresh_nearby_cols("user-1", 45.0, 6.0)

    httpx_mock.get.assert_called_once()
    assert db.cols_query.upserted is not None
    assert len(db.cols_query.upserted) == 2
    named = next(r for r in db.cols_query.upserted if r["osm_id"] == 123)
    assert named["name"] == "Col du Truc"
    assert named["elevation_m"] == 1850
    unnamed = next(r for r in db.cols_query.upserted if r["osm_id"] == 456)
    assert "Col (OSM #456)" in unnamed["name"]
    assert db.profile_query.updated is not None
    assert db.profile_query.updated["cols_cache_home_lat"] == 45.0


def test_refresh_fetches_when_home_moved_more_than_5km(monkeypatch: Any) -> None:
    db = _FakeDb(
        {
            "cols_cache_updated_at": "2026-07-07T00:00:00+00:00",
            "cols_cache_home_lat": 45.0,
            "cols_cache_home_lon": 6.0,
        }
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.json.return_value = {"elements": []}
    monkeypatch.setattr(mod, "httpx", httpx_mock)
    monkeypatch.setattr(mod, "_now", lambda: mod.datetime(2026, 7, 8, tzinfo=mod.UTC))

    # ~1 degree of latitude is ~111km, well over the 5km threshold.
    mod.refresh_nearby_cols("user-1", 45.1, 6.0)

    httpx_mock.get.assert_called_once()


def test_refresh_always_fetches_when_never_cached(monkeypatch: Any) -> None:
    db = _FakeDb({"cols_cache_updated_at": None, "cols_cache_home_lat": None, "cols_cache_home_lon": None})
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.json.return_value = {"elements": []}
    monkeypatch.setattr(mod, "httpx", httpx_mock)

    mod.refresh_nearby_cols("user-1", 45.0, 6.0)

    httpx_mock.get.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/coach/test_overpass.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'garmin_sync.coach.overpass'`

- [ ] **Step 3: Write the implementation**

```python
# worker/src/garmin_sync/coach/overpass.py
"""Overpass API (OpenStreetMap) client — refresh the shared `cols` reference table."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx

from garmin_sync.coach.geo import haversine_m
from garmin_sync.supabase_client import get_admin_client

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_RADIUS_M = 50_000
_TIMEOUT_S = 30.0
_CACHE_MAX_AGE_DAYS = 30
_CACHE_MOVE_THRESHOLD_M = 5_000


def _now() -> datetime:
    return datetime.now(UTC)


def _build_query(home_lat: float, home_lon: float) -> str:
    return (
        "[out:json][timeout:25];"
        f"node[mountain_pass=yes](around:{_RADIUS_M},{home_lat},{home_lon});"
        "out;"
    )


def _parse_elevation(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        return round(float(raw))
    except (TypeError, ValueError):
        return None


def _should_refresh(profile: dict[str, Any], home_lat: float, home_lon: float) -> bool:
    updated_at = profile.get("cols_cache_updated_at")
    if not updated_at:
        return True
    fetched = datetime.fromisoformat(str(updated_at))
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    if _now() - fetched > timedelta(days=_CACHE_MAX_AGE_DAYS):
        return True
    cache_lat = profile.get("cols_cache_home_lat")
    cache_lon = profile.get("cols_cache_home_lon")
    if cache_lat is None or cache_lon is None:
        return True
    moved_m = haversine_m(float(cache_lat), float(cache_lon), home_lat, home_lon)
    return moved_m > _CACHE_MOVE_THRESHOLD_M


def refresh_nearby_cols(user_id: str, home_lat: float, home_lon: float) -> None:
    """Refresh the shared `cols` cache from Overpass if stale or the user moved."""
    db = get_admin_client()
    profile = cast(
        "dict[str, Any] | None",
        db.table("athlete_profiles")
        .select("cols_cache_updated_at, cols_cache_home_lat, cols_cache_home_lon")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
        .data,
    )
    if profile is not None and not _should_refresh(profile, home_lat, home_lon):
        return

    response = httpx.get(
        _OVERPASS_URL,
        params={"data": _build_query(home_lat, home_lon)},
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    elements = response.json().get("elements", [])

    rows = [
        {
            "osm_id": element["id"],
            "name": element.get("tags", {}).get("name") or f"Col (OSM #{element['id']})",
            "latitude": element["lat"],
            "longitude": element["lon"],
            "elevation_m": _parse_elevation(element.get("tags", {}).get("ele")),
            "fetched_at": _now().isoformat(),
        }
        for element in elements
        if element.get("type") == "node" and "lat" in element and "lon" in element
    ]
    if rows:
        db.table("cols").upsert(rows, on_conflict="osm_id").execute()

    db.table("athlete_profiles").update(
        {
            "cols_cache_updated_at": _now().isoformat(),
            "cols_cache_home_lat": home_lat,
            "cols_cache_home_lon": home_lon,
        }
    ).eq("user_id", user_id).execute()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/coach/test_overpass.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add worker/src/garmin_sync/coach/overpass.py worker/tests/coach/test_overpass.py
git commit -m "feat(worker): refresh nearby cols from OSM Overpass API"
```

---

### Task 5: Worker — `recompute_col_crossings` (matching)

**Files:**
- Create: `worker/src/garmin_sync/coach/col_matching.py`
- Test: `worker/tests/coach/test_col_matching.py`

**Interfaces:**
- Consumes: `garmin_sync.coach.geo.haversine_m`,
  `garmin_sync.supabase_client.get_admin_client()`.
- Produces: `recompute_col_crossings(user_id: str, home_lat: float, home_lon: float) ->
  None`. Consumed by Task 6.

- [ ] **Step 1: Write the failing tests**

```python
# worker/tests/coach/test_col_matching.py
from __future__ import annotations

from typing import Any

import garmin_sync.coach.col_matching as mod

NEARBY_COL = {"id": "col-1", "latitude": 45.05, "longitude": 6.05}
FAR_COL = {"id": "col-2", "latitude": 50.0, "longitude": 2.0}


class _FakeQuery:
    def __init__(self, rows: Any) -> None:
        self._rows = rows
        self.upserted: list[dict[str, Any]] | None = None
        self.updated: dict[str, Any] | None = None

    @property
    def not_(self) -> "_FakeQuery":
        return self

    def select(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def eq(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def is_(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def gt(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def order(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def maybe_single(self, *_a: Any, **_k: Any) -> "_FakeQuery":
        return self

    def upsert(self, rows: list[dict[str, Any]], **_k: Any) -> "_FakeQuery":
        self.upserted = rows
        return self

    def update(self, values: dict[str, Any]) -> "_FakeQuery":
        self.updated = values
        return self

    def execute(self) -> Any:
        class _R:
            data = self._rows

        return _R()


class _FakeSamplesQuery(_FakeQuery):
    """Routes `.eq("garmin_activity_id", X)` to per-activity canned samples."""

    def __init__(self, samples_by_activity: dict[int, list[dict[str, Any]]]) -> None:
        super().__init__([])
        self._samples_by_activity = samples_by_activity
        self._activity_id: int | None = None

    def eq(self, key: str, value: Any) -> "_FakeSamplesQuery":
        if key == "garmin_activity_id":
            self._activity_id = value
        return self

    def execute(self) -> Any:
        class _R:
            data = self._samples_by_activity.get(self._activity_id, [])

        return _R()


class _FakeDb:
    def __init__(
        self,
        *,
        cols_rows: list[dict[str, Any]],
        profile_row: dict[str, Any] | None,
        activities_rows: list[dict[str, Any]],
        samples_by_activity: dict[int, list[dict[str, Any]]],
    ) -> None:
        self.cols_query = _FakeQuery(cols_rows)
        self.profile_query = _FakeQuery(profile_row)
        self.activities_query = _FakeQuery(activities_rows)
        self.samples_query = _FakeSamplesQuery(samples_by_activity)
        self.crossings_query = _FakeQuery(None)

    def table(self, name: str) -> _FakeQuery:
        return {
            "cols": self.cols_query,
            "athlete_profiles": self.profile_query,
            "activities": self.activities_query,
            "activity_samples": self.samples_query,
            "col_crossings": self.crossings_query,
        }[name]


def test_records_crossing_within_threshold(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        samples_by_activity={1: [{"latitude": 45.0501, "longitude": 6.0501}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    mod.recompute_col_crossings("user-1", 45.0, 6.0)

    assert db.crossings_query.upserted is not None
    assert len(db.crossings_query.upserted) == 1
    row = db.crossings_query.upserted[0]
    assert row["col_id"] == "col-1"
    assert row["garmin_activity_id"] == 1
    assert row["min_distance_m"] < 150
    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-01T08:00:00Z"}


def test_no_crossing_when_track_stays_beyond_threshold(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        # ~1.1km away from the col, well beyond 150m.
        samples_by_activity={1: [{"latitude": 45.06, "longitude": 6.05}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    mod.recompute_col_crossings("user-1", 45.0, 6.0)

    assert db.crossings_query.upserted is None
    # Cursor still advances — the activity was processed.
    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-01T08:00:00Z"}


def test_skips_entirely_when_no_cols_nearby(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[FAR_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        samples_by_activity={1: [{"latitude": 45.0, "longitude": 6.0}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    mod.recompute_col_crossings("user-1", 45.0, 6.0)

    assert db.crossings_query.upserted is None
    assert db.profile_query.updated is None


def test_no_new_activities_leaves_cursor_untouched(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": "2026-07-01T08:00:00Z"},
        activities_rows=[],
        samples_by_activity={},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    mod.recompute_col_crossings("user-1", 45.0, 6.0)

    assert db.crossings_query.upserted is None
    assert db.profile_query.updated is None


def test_processes_two_activities_and_advances_cursor_to_latest(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[
            {"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"},
            {"garmin_activity_id": 2, "start_time": "2026-07-03T08:00:00Z"},
        ],
        samples_by_activity={
            1: [{"latitude": 45.0501, "longitude": 6.0501}],
            2: [{"latitude": 45.06, "longitude": 6.05}],  # beyond threshold
        },
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    mod.recompute_col_crossings("user-1", 45.0, 6.0)

    assert db.crossings_query.upserted is not None
    assert len(db.crossings_query.upserted) == 1
    assert db.crossings_query.upserted[0]["garmin_activity_id"] == 1
    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-03T08:00:00Z"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/coach/test_col_matching.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'garmin_sync.coach.col_matching'`

- [ ] **Step 3: Write the implementation**

```python
# worker/src/garmin_sync/coach/col_matching.py
"""Match GPS activities against nearby cols by proximity to the summit point."""

from __future__ import annotations

from typing import Any, cast

from garmin_sync.coach.geo import haversine_m
from garmin_sync.supabase_client import get_admin_client

_NEARBY_RADIUS_M = 50_000
_CROSSING_THRESHOLD_M = 150.0


def recompute_col_crossings(user_id: str, home_lat: float, home_lon: float) -> None:
    """Detect col crossings on GPS activities synced since the last run.

    Processes activities with `start_time` after `col_matching_cursor` (or the full
    history on first run), matches each against cols within 50km of home using
    full-resolution `activity_samples`, and upserts one `col_crossings` row per
    (col, activity) pair within 150m. Advances the cursor to the latest processed
    activity's `start_time`.
    """
    db = get_admin_client()

    all_cols = cast(
        "list[dict[str, Any]]",
        db.table("cols").select("id, latitude, longitude").execute().data or [],
    )
    nearby_cols = [
        col
        for col in all_cols
        if haversine_m(home_lat, home_lon, float(col["latitude"]), float(col["longitude"]))
        <= _NEARBY_RADIUS_M
    ]
    if not nearby_cols:
        return

    profile = cast(
        "dict[str, Any] | None",
        db.table("athlete_profiles")
        .select("col_matching_cursor")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
        .data,
    )
    cursor = profile.get("col_matching_cursor") if profile else None

    query = (
        db.table("activities")
        .select("garmin_activity_id, start_time")
        .eq("user_id", user_id)
        .not_.is_("route_polyline", "null")
    )
    if cursor:
        query = query.gt("start_time", cursor)
    activities = cast("list[dict[str, Any]]", query.order("start_time").execute().data or [])
    if not activities:
        return

    max_start_time: str | None = cursor
    for activity in activities:
        activity_id = activity["garmin_activity_id"]
        start_time = activity["start_time"]
        samples = cast(
            "list[dict[str, Any]]",
            db.table("activity_samples")
            .select("latitude, longitude")
            .eq("user_id", user_id)
            .eq("garmin_activity_id", activity_id)
            .not_.is_("latitude", "null")
            .execute()
            .data
            or [],
        )
        crossing_rows = _match_activity(
            user_id=user_id,
            activity_id=activity_id,
            start_time=start_time,
            samples=samples,
            cols=nearby_cols,
        )
        if crossing_rows:
            db.table("col_crossings").upsert(
                crossing_rows, on_conflict="user_id,col_id,garmin_activity_id"
            ).execute()
        if max_start_time is None or start_time > max_start_time:
            max_start_time = start_time

    if max_start_time is not None and max_start_time != cursor:
        db.table("athlete_profiles").update({"col_matching_cursor": max_start_time}).eq(
            "user_id", user_id
        ).execute()


def _match_activity(
    *,
    user_id: str,
    activity_id: int,
    start_time: str,
    samples: list[dict[str, Any]],
    cols: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/coach/test_col_matching.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add worker/src/garmin_sync/coach/col_matching.py worker/tests/coach/test_col_matching.py
git commit -m "feat(worker): match GPS activities against nearby cols"
```

---

### Task 6: Worker — wire the pipeline into the daily cron

**Files:**
- Modify: `worker/src/garmin_sync/cron.py:33-45` (`_run_post_sync_recomputes`)
- Test: `worker/tests/test_cron_post_sync_recomputes.py` (new)

**Interfaces:**
- Consumes: `compute_home_location`, `refresh_nearby_cols`,
  `recompute_col_crossings` (Tasks 3-5).

- [ ] **Step 1: Write the failing test**

```python
# worker/tests/test_cron_post_sync_recomputes.py
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from garmin_sync import cron


def test_post_sync_recomputes_calls_cols_pipeline_when_home_found(monkeypatch: Any) -> None:
    monkeypatch.setattr(cron, "recompute_daily_state", MagicMock())
    recovery_mock = MagicMock()
    monkeypatch.setattr(
        "garmin_sync.coach.recovery_baselines.recompute_recovery_baselines", recovery_mock
    )
    home_mock = MagicMock(return_value=(45.0, 6.0))
    monkeypatch.setattr("garmin_sync.coach.home_location.compute_home_location", home_mock)
    overpass_mock = MagicMock()
    monkeypatch.setattr("garmin_sync.coach.overpass.refresh_nearby_cols", overpass_mock)
    matching_mock = MagicMock()
    monkeypatch.setattr("garmin_sync.coach.col_matching.recompute_col_crossings", matching_mock)

    cron._run_post_sync_recomputes("user-1")

    home_mock.assert_called_once_with("user-1")
    overpass_mock.assert_called_once_with("user-1", 45.0, 6.0)
    matching_mock.assert_called_once_with("user-1", 45.0, 6.0)


def test_post_sync_recomputes_skips_cols_pipeline_without_home(monkeypatch: Any) -> None:
    monkeypatch.setattr(cron, "recompute_daily_state", MagicMock())
    monkeypatch.setattr(
        "garmin_sync.coach.recovery_baselines.recompute_recovery_baselines", MagicMock()
    )
    monkeypatch.setattr(
        "garmin_sync.coach.home_location.compute_home_location", MagicMock(return_value=None)
    )
    overpass_mock = MagicMock()
    monkeypatch.setattr("garmin_sync.coach.overpass.refresh_nearby_cols", overpass_mock)
    matching_mock = MagicMock()
    monkeypatch.setattr("garmin_sync.coach.col_matching.recompute_col_crossings", matching_mock)

    cron._run_post_sync_recomputes("user-1")

    overpass_mock.assert_not_called()
    matching_mock.assert_not_called()


def test_post_sync_recomputes_swallows_cols_pipeline_errors(monkeypatch: Any) -> None:
    monkeypatch.setattr(cron, "recompute_daily_state", MagicMock())
    monkeypatch.setattr(
        "garmin_sync.coach.recovery_baselines.recompute_recovery_baselines", MagicMock()
    )
    monkeypatch.setattr(
        "garmin_sync.coach.home_location.compute_home_location",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    # Must not raise.
    cron._run_post_sync_recomputes("user-1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker && uv run pytest tests/test_cron_post_sync_recomputes.py -v`
Expected: FAIL — `overpass_mock`/`matching_mock` assertions fail (functions not called,
module doesn't import/call them yet).

- [ ] **Step 3: Wire the pipeline in `_run_post_sync_recomputes`**

In `worker/src/garmin_sync/cron.py`, replace the function body (lines 33-45):

```python
def _run_post_sync_recomputes(user_id: str) -> None:
    try:
        recompute_daily_state(user_id, days_back=180)
    except Exception as exc:
        log.exception("recompute_daily_state failed for user=%s", user_id)
        capture(exc, where="recompute_daily_state", user_id=user_id)
    try:
        from garmin_sync.coach.recovery_baselines import recompute_recovery_baselines

        recompute_recovery_baselines(user_id)
    except Exception as exc:
        log.exception("recompute_recovery_baselines failed for user=%s", user_id)
        capture(exc, where="recompute_recovery_baselines", user_id=user_id)

    home: tuple[float, float] | None = None
    try:
        from garmin_sync.coach.home_location import compute_home_location

        home = compute_home_location(user_id)
    except Exception as exc:
        log.exception("compute_home_location failed for user=%s", user_id)
        capture(exc, where="compute_home_location", user_id=user_id)

    if home is not None:
        home_lat, home_lon = home
        try:
            from garmin_sync.coach.overpass import refresh_nearby_cols

            refresh_nearby_cols(user_id, home_lat, home_lon)
        except Exception as exc:
            log.exception("refresh_nearby_cols failed for user=%s", user_id)
            capture(exc, where="refresh_nearby_cols", user_id=user_id)
        try:
            from garmin_sync.coach.col_matching import recompute_col_crossings

            recompute_col_crossings(user_id, home_lat, home_lon)
        except Exception as exc:
            log.exception("recompute_col_crossings failed for user=%s", user_id)
            capture(exc, where="recompute_col_crossings", user_id=user_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/test_cron_post_sync_recomputes.py -v`
Expected: `3 passed`

- [ ] **Step 5: Run the full worker test suite**

Run: `cd worker && uv run pytest -q`
Expected: all tests pass (450 previously + 3 + 12 new from Tasks 2-5 = 465, exact count
may vary slightly).

- [ ] **Step 6: Lint and type-check**

Run: `cd worker && uv run ruff check . && uv run mypy src/`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add worker/src/garmin_sync/cron.py worker/tests/test_cron_post_sync_recomputes.py
git commit -m "feat(worker): wire cols pipeline into the daily post-sync cron"
```

---

### Task 7: Frontend — `lib/dashboard/cols.ts` (types + aggregation)

**Files:**
- Create: `lib/dashboard/cols.ts`
- Test: `tests/unit/dashboard/cols.test.ts`

**Interfaces:**
- Produces: `ColDto`, `ColCrossingRowDto`, `ColSummary` types; `haversineKm(lat1, lon1,
  lat2, lon2): number`; `computeColsSummary({ homeLat, homeLon, cols, crossings,
  radiusKm? }): ColSummary[]`. Consumed by Task 8/9.

- [ ] **Step 1: Write the failing tests**

```typescript
// tests/unit/dashboard/cols.test.ts
import { describe, expect, it } from 'vitest'
import { computeColsSummary, haversineKm } from '@/lib/dashboard/cols'
import type { ColCrossingRowDto, ColDto } from '@/lib/dashboard/cols'

const HOME_LAT = 45.0
const HOME_LON = 6.0

function mkCol(overrides: Partial<ColDto>): ColDto {
  return {
    id: 'col-1',
    name: 'Col du Truc',
    latitude: 45.05,
    longitude: 6.05,
    elevation_m: 1850,
    ...overrides,
  }
}

describe('haversineKm', () => {
  it('returns 0 for identical points', () => {
    expect(haversineKm(45.0, 6.0, 45.0, 6.0)).toBe(0)
  })

  it('computes the known Paris-Lyon distance (~391km)', () => {
    const km = haversineKm(48.8566, 2.3522, 45.764, 4.8357)
    expect(km).toBeGreaterThan(385)
    expect(km).toBeLessThan(400)
  })
})

describe('computeColsSummary', () => {
  it('filters out cols beyond the radius', () => {
    const cols: ColDto[] = [
      mkCol({ id: 'near', latitude: 45.05, longitude: 6.05 }),
      mkCol({ id: 'far', latitude: 50.0, longitude: 2.0 }),
    ]
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols, crossings: [] })
    expect(out.map((c) => c.id)).toEqual(['near'])
  })

  it('counts crossings per col and keeps 0-count cols', () => {
    const cols: ColDto[] = [
      mkCol({ id: 'col-a', latitude: 45.01, longitude: 6.01 }),
      mkCol({ id: 'col-b', latitude: 45.02, longitude: 6.02 }),
    ]
    const crossings: ColCrossingRowDto[] = [
      { col_id: 'col-a', crossed_at: '2026-06-01T08:00:00Z' },
      { col_id: 'col-a', crossed_at: '2026-06-15T08:00:00Z' },
    ]
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols, crossings })
    const colA = out.find((c) => c.id === 'col-a')
    const colB = out.find((c) => c.id === 'col-b')
    expect(colA?.crossingsCount).toBe(2)
    expect(colA?.lastCrossedAt).toBe('2026-06-15T08:00:00Z')
    expect(colB?.crossingsCount).toBe(0)
    expect(colB?.lastCrossedAt).toBeNull()
  })

  it('sorts by crossings count desc, then distance asc', () => {
    const cols: ColDto[] = [
      mkCol({ id: 'far-climbed', latitude: 45.04, longitude: 6.04 }),
      mkCol({ id: 'near-unclimbed', latitude: 45.01, longitude: 6.01 }),
      mkCol({ id: 'far-unclimbed', latitude: 45.03, longitude: 6.03 }),
    ]
    const crossings: ColCrossingRowDto[] = [
      { col_id: 'far-climbed', crossed_at: '2026-06-01T08:00:00Z' },
    ]
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols, crossings })
    expect(out.map((c) => c.id)).toEqual(['far-climbed', 'near-unclimbed', 'far-unclimbed'])
  })

  it('returns an empty array when there are no cols in range', () => {
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols: [], crossings: [] })
    expect(out).toEqual([])
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm vitest run tests/unit/dashboard/cols.test.ts`
Expected: FAIL — cannot find module `@/lib/dashboard/cols`.

- [ ] **Step 3: Write the implementation**

```typescript
// lib/dashboard/cols.ts
const DEFAULT_RADIUS_KM = 50
const EARTH_RADIUS_KM = 6371

export interface ColDto {
  id: string
  name: string
  latitude: number
  longitude: number
  elevation_m: number | null
}

export interface ColCrossingRowDto {
  col_id: string
  crossed_at: string
}

export interface ColSummary {
  id: string
  name: string
  elevationM: number | null
  distanceKm: number
  crossingsCount: number
  lastCrossedAt: string | null
}

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a))
}

export function computeColsSummary({
  homeLat,
  homeLon,
  cols,
  crossings,
  radiusKm = DEFAULT_RADIUS_KM,
}: {
  homeLat: number
  homeLon: number
  cols: ColDto[]
  crossings: ColCrossingRowDto[]
  radiusKm?: number
}): ColSummary[] {
  const crossingsByCol = new Map<string, { count: number; lastCrossedAt: string }>()
  for (const crossing of crossings) {
    const existing = crossingsByCol.get(crossing.col_id)
    if (!existing) {
      crossingsByCol.set(crossing.col_id, { count: 1, lastCrossedAt: crossing.crossed_at })
      continue
    }
    existing.count += 1
    if (crossing.crossed_at > existing.lastCrossedAt) {
      existing.lastCrossedAt = crossing.crossed_at
    }
  }

  const summaries: ColSummary[] = cols
    .map((col): ColSummary & { _distanceKm: number } => {
      const distanceKm = haversineKm(homeLat, homeLon, col.latitude, col.longitude)
      const crossing = crossingsByCol.get(col.id)
      return {
        id: col.id,
        name: col.name,
        elevationM: col.elevation_m,
        distanceKm: Math.round(distanceKm * 10) / 10,
        crossingsCount: crossing?.count ?? 0,
        lastCrossedAt: crossing?.lastCrossedAt ?? null,
        _distanceKm: distanceKm,
      }
    })
    .filter((summary) => summary._distanceKm <= radiusKm)

  return summaries
    .sort((a, b) => b.crossingsCount - a.crossingsCount || a.distanceKm - b.distanceKm)
    .map(({ _distanceKm, ...summary }) => summary)
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm vitest run tests/unit/dashboard/cols.test.ts`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add lib/dashboard/cols.ts tests/unit/dashboard/cols.test.ts
git commit -m "feat(dashboard): cols summary aggregation (distance + crossings count)"
```

---

### Task 8: Frontend — `ColsWidgetSkeleton` + `ColsWidget` presentational component

**Files:**
- Create: `app/(app)/_components/skeletons/cols-widget-skeleton.tsx`
- Create: `app/(app)/_components/cols-widget.tsx`
- Test: `tests/unit/components/cols-widget-skeleton.test.tsx`
- Test: `tests/unit/components/cols-widget.test.tsx`

**Interfaces:**
- Consumes: `ColSummary` (Task 7), `ChartCard`, `EmptyState` (existing).
- Produces: `ColsWidgetSkeleton` (no props), `ColsWidget({ summaries: ColSummary[] })`.
  Consumed by Task 9.

- [ ] **Step 1: Write the failing tests**

```typescript
// tests/unit/components/cols-widget-skeleton.test.tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ColsWidgetSkeleton } from '@/app/(app)/_components/skeletons/cols-widget-skeleton'

afterEach(() => {
  cleanup()
})

describe('ColsWidgetSkeleton', () => {
  it('renders an accessible loading region for the cols widget', () => {
    render(<ColsWidgetSkeleton />)
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toContain('cols')
  })
})
```

```typescript
// tests/unit/components/cols-widget.test.tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ColsWidget } from '@/app/(app)/_components/cols-widget'
import type { ColSummary } from '@/lib/dashboard/cols'

afterEach(() => {
  cleanup()
})

function mkSummary(overrides: Partial<ColSummary>): ColSummary {
  return {
    id: 'col-1',
    name: 'Col du Truc',
    elevationM: 1850,
    distanceKm: 12,
    crossingsCount: 4,
    lastCrossedAt: '2026-06-15T08:00:00Z',
    ...overrides,
  }
}

describe('ColsWidget', () => {
  it('renders one row per col with name, altitude, distance and count', () => {
    render(<ColsWidget summaries={[mkSummary({})]} />)
    expect(screen.getByText('Col du Truc')).not.toBeNull()
    expect(screen.getByText(/1850/)).not.toBeNull()
    expect(screen.getByText(/12/)).not.toBeNull()
    expect(screen.getByText(/4 fois/)).not.toBeNull()
  })

  it('shows singular wording for exactly one crossing', () => {
    render(<ColsWidget summaries={[mkSummary({ crossingsCount: 1 })]} />)
    expect(screen.getByText(/1 fois/)).not.toBeNull()
  })

  it('shows an empty state when there are no cols in range', () => {
    render(<ColsWidget summaries={[]} />)
    expect(screen.getByText(/Aucun col recensé/)).not.toBeNull()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm vitest run tests/unit/components/cols-widget-skeleton.test.tsx tests/unit/components/cols-widget.test.tsx`
Expected: FAIL — modules don't exist yet.

- [ ] **Step 3: Write the skeleton**

```typescript
// app/(app)/_components/skeletons/cols-widget-skeleton.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from './loading-region'

const ROW_KEYS = ['row-1', 'row-2', 'row-3', 'row-4']

export function ColsWidgetSkeleton() {
  return (
    <LoadingRegion label="Chargement des cols">
      <section className="space-y-3 rounded-lg border p-4">
        <Skeleton className="h-4 w-32" />
        <div className="divide-y">
          {ROW_KEYS.map((key) => (
            <div key={key} className="flex items-center justify-between py-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
      </section>
    </LoadingRegion>
  )
}
```

- [ ] **Step 4: Write the presentational component**

```typescript
// app/(app)/_components/cols-widget.tsx
import { Mountain } from 'lucide-react'
import type { ColSummary } from '@/lib/dashboard/cols'
import { ChartCard } from './chart-card'
import { EmptyState } from './empty-state'

function crossingsLabel(count: number): string {
  return count === 1 ? '1 fois' : `${String(count)} fois`
}

export function ColsWidget({ summaries }: Readonly<{ summaries: ColSummary[] }>) {
  if (summaries.length === 0) {
    return (
      <ChartCard title="Mes cols" description="Cols dans un rayon de 50 km autour de chez toi">
        <EmptyState
          icon={Mountain}
          title="Aucun col recensé"
          description="Aucun col recensé dans un rayon de 50 km autour de chez toi."
        />
      </ChartCard>
    )
  }

  return (
    <ChartCard title="Mes cols" description="Cols dans un rayon de 50 km autour de chez toi">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-muted-foreground border-b text-left text-xs uppercase">
            <th className="py-2 font-medium">Nom</th>
            <th className="py-2 font-medium">Altitude</th>
            <th className="py-2 font-medium">Distance</th>
            <th className="py-2 text-right font-medium">Grimpé</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {summaries.map((summary) => (
            <tr key={summary.id}>
              <td className="py-2 font-medium">{summary.name}</td>
              <td className="text-muted-foreground py-2">
                {summary.elevationM !== null ? `${String(summary.elevationM)} m` : '—'}
              </td>
              <td className="text-muted-foreground py-2">{summary.distanceKm} km</td>
              <td
                className={
                  summary.crossingsCount > 0
                    ? 'py-2 text-right font-medium'
                    : 'text-muted-foreground py-2 text-right'
                }
              >
                {crossingsLabel(summary.crossingsCount)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </ChartCard>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pnpm vitest run tests/unit/components/cols-widget-skeleton.test.tsx tests/unit/components/cols-widget.test.tsx`
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add app/\(app\)/_components/skeletons/cols-widget-skeleton.tsx \
        app/\(app\)/_components/cols-widget.tsx \
        tests/unit/components/cols-widget-skeleton.test.tsx \
        tests/unit/components/cols-widget.test.tsx
git commit -m "feat(dashboard): cols widget table + skeleton components"
```

---

### Task 9: Frontend — wire `ColsWidget` into `/stats`, isolated from the cockpit fetch

**Files:**
- Modify: `app/(app)/stats/page.tsx`

**Interfaces:**
- Consumes: `ColSummary`, `computeColsSummary` (Task 7), `ColsWidget` (Task 8),
  `ColsWidgetSkeleton` (Task 8).

- [ ] **Step 1: Add imports**

At the top of `app/(app)/stats/page.tsx`, alongside the existing imports:

```typescript
import { ColsWidget } from '../_components/cols-widget'
import { ColsWidgetSkeleton } from '../_components/skeletons/cols-widget-skeleton'
import { computeColsSummary, type ColCrossingRowDto, type ColDto } from '@/lib/dashboard/cols'
```

- [ ] **Step 2: Add the `ColsWidgetLoader` async component**

Below the `CockpitBody` function (before `export default async function StatsPage`), add
a self-contained async server component — mirrors the `BriefingLoader` pattern in
`app/(app)/today/page.tsx`, which already runs its own independent
`<Suspense>`-wrapped fetch outside the page's main data block:

```typescript
async function ColsWidgetLoader({ userId }: { readonly userId: string }) {
  const supabase = await createClient()
  const { data: profile } = await supabase
    .from('athlete_profiles')
    .select('lat, lon')
    .eq('user_id', userId)
    .maybeSingle()

  if (!profile?.lat || !profile.lon) {
    return (
      <ChartCard title="Mes cols" description="Cols dans un rayon de 50 km autour de chez toi">
        <EmptyState
          icon={ActivityIcon}
          title="Domicile pas encore situé"
          description="Pas encore assez de données GPS pour situer chez toi."
        />
      </ChartCard>
    )
  }

  const [colsRes, crossingsRes] = await Promise.all([
    supabase.from('cols').select('id, name, latitude, longitude, elevation_m'),
    supabase.from('col_crossings').select('col_id, crossed_at').eq('user_id', userId),
  ])

  const summaries = computeColsSummary({
    homeLat: Number(profile.lat),
    homeLon: Number(profile.lon),
    cols: (colsRes.data ?? []) as ColDto[],
    crossings: (crossingsRes.data ?? []) as ColCrossingRowDto[],
  })

  return <ColsWidget summaries={summaries} />
}
```

- [ ] **Step 3: Mount it as a sibling Suspense boundary in `StatsPage`**

In the `StatsPage` return statement, after the closing `</Suspense>` of the main
`CockpitBody` block and before the closing `</div>`:

```typescript
      <Suspense fallback={<CockpitSkeleton />}>
        <CockpitBody userId={userId} range={range} selectedSport={selectedSport} />
      </Suspense>

      <Suspense fallback={<ColsWidgetSkeleton />}>
        <ColsWidgetLoader userId={userId} />
      </Suspense>
    </div>
  )
}
```

This keeps `ColsWidgetLoader`'s fetch fully independent of `CockpitBody`'s
`Promise.all` — it mounts and starts fetching immediately, in parallel, and never
delays the rest of the page.

- [ ] **Step 4: Type-check and lint**

Run: `pnpm typecheck && pnpm lint`
Expected: no errors.

- [ ] **Step 5: Run the full frontend test suite**

Run: `pnpm test -- --run`
Expected: all tests pass (546 previously + 13 new from Tasks 7-8 = 559, exact count may
vary slightly).

- [ ] **Step 6: Commit**

```bash
git add app/\(app\)/stats/page.tsx
git commit -m "feat(dashboard): mount cols widget on /stats with an isolated Suspense boundary"
```

---

### Task 10: Manual QA, quality pass, and PR

**Files:** none (verification only).

- [ ] **Step 1: Rename the branch for the PR**

```bash
git branch -m worktree-cols-widget feat/cols-widget
```

- [ ] **Step 2: Full verification**

```bash
cd worker && uv run pytest -v && uv run ruff check . && uv run mypy src/
cd .. && pnpm lint && pnpm typecheck && pnpm test -- --run && pnpm build
```

Expected: everything green. If `pnpm build` fails on stale `.next/types`, run
`rm -rf .next` first (known pitfall, see `CLAUDE.md`).

- [ ] **Step 3: Manual smoke test**

Start the worker locally (`cd worker && uv run uvicorn garmin_sync.main:app --reload
--port 8080`) and the frontend (`pnpm dev`). Trigger a sync for a user with GPS
activities (or call `run_sync_for_user` directly in a Python shell against the dev
Supabase project — migration from Task 1 must already be applied there). Load `/stats`
and confirm:
- the cockpit section renders immediately, before the cols widget resolves (throttle
  the network in devtools if needed to see the skeleton clearly);
- the cols widget shows a skeleton, then either a populated table or the correct empty
  state depending on the test user's data.

- [ ] **Step 4: Run `/vqo` and reach 9.5+ in every category**

Per owner instruction (2026-07-08): invoke the `/vqo` skill against this branch's diff.
Fix every point it raises — correctness, security, tests, simplification, whatever the
categories are — and re-run until **every category scores 9.5 or above**. Do not open
the PR before this passes.

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin feat/cols-widget
gh pr create --title "feat: widget Mes cols — cols autour de chez moi + franchissements" --body "$(cat <<'EOF'
## Summary
- Domicile calculé automatiquement (médiane des départs GPS, réutilise athlete_profiles.lat/lon)
- Référentiel de cols alimenté depuis OpenStreetMap Overpass (rayon 50km)
- Détection de franchissement par proximité GPS (150m), calculée dans le cron worker quotidien
- Widget /stats avec chargement async isolé (Suspense + skeleton dédiés, ne bloque jamais le reste de la page)

## Test plan
- [x] worker: pytest + ruff + mypy
- [x] frontend: vitest + lint + typecheck + build
- [ ] Migration appliquée sur le projet Supabase dev et vérifiée en conditions réelles
- [ ] `/vqo` passé, 9.5+ dans toutes les catégories

Spec: docs/superpowers/specs/2026-07-08-cols-stats-widget-design.md
EOF
)"
```

Report the PR URL back to the user; do not merge without their go-ahead.
