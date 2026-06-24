# Cartographie GPS — Livrable A (pipeline data) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extraire les coordonnées GPS des activités Garmin, les stocker, et afficher la trace de chaque activité sur une carte interactive (page détail).

**Architecture:** Le worker récupère déjà `get_activity_details` ; on extrait les clés `directLatitude`/`directLongitude` (aucun appel API en plus pour les nouvelles activités), on stocke les points pleine résolution dans `activity_samples` et une polyligne downsamplée (~64 pts) dans `activities.route_polyline`. Une passe de backfill throttlée remplit l'historique existant. Le frontend rend la trace avec MapLibre GL JS (fond CARTO dark, sans clé API).

**Tech Stack:** Python 3.12 (FastAPI worker, pytest), Supabase Postgres, Next.js 15 / TypeScript, `recharts` (existant), `maplibre-gl` (nouveau), Vitest.

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-06-24-gps-routes-maps-design.md`.
- Migration Supabase **additive uniquement** (colonnes nullable) — aucun breaking change.
- Extraction Garmin **défensive** : clés multiples tolérées, valeurs nulles tolérées (indoor / trous GPS).
- Sémantique d'abort worker inchangée : `GarminConnectTooManyRequestsError` / `GarminConnectAuthenticationError` / `GarminProfileIncompleteError` doivent **toujours remonter** (jamais avalées).
- `GPS_BACKFILL_BATCH` par défaut = **8**.
- Downsampling polyline : **≤ 64 points**, premier et dernier point conservés.
- Conventions de commit : Conventional Commits, body ≤ 100 chars.
- Quality gates : `cd worker && uv run pytest -v` + `uv run ruff check . && uv run mypy src/` (worker) ; `pnpm test && pnpm lint && pnpm typecheck && pnpm build` (frontend). Coverage Sonar 97 % à préserver.
- Branche de travail : `feat/carto-gps-livrable-a` (depuis `main`).
- Le rendu enrichi (trace colorée par métrique, vignettes SVG, heatmap) est **hors périmètre** de ce livrable → Livrable B.

---

## File Structure

**Worker (Python)**
- `supabase/migrations/20260624000000_carto_gps.sql` — *create* — colonnes lat/lng + route_polyline.
- `worker/src/garmin_sync/transformers/activities.py` — *modify* — extraction lat/lng dans les samples.
- `worker/src/garmin_sync/transformers/route.py` — *create* — `build_route_polyline()` (fonction pure).
- `worker/src/garmin_sync/config.py` — *modify* — réglage `gps_backfill_batch`.
- `worker/src/garmin_sync/sync.py` — *modify* — écriture `route_polyline` + passe de backfill.
- `worker/tests/test_transformers/test_activities.py` — *modify* — tests extraction lat/lng.
- `worker/tests/test_transformers/test_route.py` — *create* — tests downsampling.
- `worker/tests/test_config.py` — *modify* — test du défaut `gps_backfill_batch`.
- `worker/tests/test_sync.py` — *modify* — tests route_polyline + backfill.

**Frontend (TypeScript)**
- `package.json` — *modify* — dépendance `maplibre-gl`.
- `lib/maps/route-geojson.ts` — *create* — `buildRouteGeoJson()` + `routeBounds()` (purs).
- `lib/coach/activity-analysis.ts` — *modify* — champs `latitude`/`longitude` sur `ActivitySample`.
- `app/(app)/_components/maps/activity-route-map.tsx` — *create* — composant carte client-only.
- `app/(app)/history/[id]/page.tsx` — *modify* — sélection lat/lng + rendu de la carte.
- `tests/unit/maps/route-geojson.test.ts` — *create* — tests util GeoJSON/bounds.
- `tests/unit/components/activity-route-map.test.tsx` — *create* — test composant (maplibre mocké).

---

## Task 1: Migration DB — colonnes GPS

**Files:**
- Create: `supabase/migrations/20260624000000_carto_gps.sql`

**Interfaces:**
- Produces: colonnes `activity_samples.latitude`, `activity_samples.longitude` (numeric, nullable) ; `activities.route_polyline` (jsonb, nullable).

- [ ] **Step 1: Écrire la migration**

```sql
-- Cartographie GPS — coordonnées des samples + polyligne downsamplée par activité.
-- Additif uniquement (colonnes nullable) : aucun impact sur les lignes existantes.

alter table public.activity_samples
  add column if not exists latitude numeric(9, 6)
    check (latitude is null or latitude between -90 and 90),
  add column if not exists longitude numeric(9, 6)
    check (longitude is null or longitude between -180 and 180);

alter table public.activities
  add column if not exists route_polyline jsonb;

comment on column public.activities.route_polyline is
  'Polyligne GPS downsamplée (<=64 points [lng, lat]) pour vignettes et heatmap. Null si pas de GPS.';
```

- [ ] **Step 2: Appliquer la migration (Supabase MCP) et vérifier**

Appliquer via `mcp__supabase__apply_migration` (project `peiyrqplymdlmlpsbqzu`, name `carto_gps`, query = contenu du fichier).
Puis vérifier avec `mcp__supabase__execute_sql` :

```sql
select column_name, data_type
from information_schema.columns
where table_name = 'activity_samples' and column_name in ('latitude','longitude')
union all
select column_name, data_type
from information_schema.columns
where table_name = 'activities' and column_name = 'route_polyline';
```

Expected : 3 lignes (`latitude` numeric, `longitude` numeric, `route_polyline` jsonb).

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260624000000_carto_gps.sql
git commit -m "feat(db): add GPS columns to activity_samples and route_polyline to activities"
```

---

## Task 2: Worker — extraction lat/lng dans les samples

**Files:**
- Modify: `worker/src/garmin_sync/transformers/activities.py`
- Test: `worker/tests/test_transformers/test_activities.py`

**Interfaces:**
- Consumes: `transform_activity_samples(*, user_id, garmin_activity_id, raw_details)` (existant).
- Produces: chaque dict de sample retourné contient désormais les clés `latitude: float | None` et `longitude: float | None`.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter dans `worker/tests/test_transformers/test_activities.py` :

```python
def test_transform_activity_samples_extracts_gps() -> None:
    raw_details = {
        "activityDetailMetrics": [
            {
                "metrics": [
                    {"key": "directHeartRate", "value": 145},
                    {"key": "directLatitude", "value": 45.764043},
                    {"key": "directLongitude", "value": 4.835659},
                ]
            }
        ]
    }

    rows = transform_activity_samples(user_id="u1", garmin_activity_id=123, raw_details=raw_details)

    assert rows[0]["latitude"] == 45.764043
    assert rows[0]["longitude"] == 4.835659


def test_transform_activity_samples_gps_null_when_absent() -> None:
    raw_details = {
        "activityDetailMetrics": [{"metrics": [{"key": "directHeartRate", "value": 140}]}]
    }

    rows = transform_activity_samples(user_id="u1", garmin_activity_id=123, raw_details=raw_details)

    assert rows[0]["latitude"] is None
    assert rows[0]["longitude"] is None
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `cd worker && uv run pytest tests/test_transformers/test_activities.py::test_transform_activity_samples_extracts_gps -v`
Expected: FAIL (`KeyError: 'latitude'`).

- [ ] **Step 3: Implémenter l'extraction**

Dans `worker/src/garmin_sync/transformers/activities.py`, ajouter les constantes de clés près des autres (après la ligne `_SPEED_KEYS = (...)`) :

```python
_LAT_KEYS = ("directLatitude", "latitude")
_LON_KEYS = ("directLongitude", "longitude")
```

Puis, dans `transform_activity_samples`, ajouter les deux clés au dict appended (juste après la ligne `"speed_m_s": _to_float(_first_value(normalized, _SPEED_KEYS)),`) :

```python
                "latitude": _to_float(_first_value(normalized, _LAT_KEYS)),
                "longitude": _to_float(_first_value(normalized, _LON_KEYS)),
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `cd worker && uv run pytest tests/test_transformers/test_activities.py -v`
Expected: PASS (tous les tests du fichier, anciens + nouveaux).

- [ ] **Step 5: Commit**

```bash
git add worker/src/garmin_sync/transformers/activities.py worker/tests/test_transformers/test_activities.py
git commit -m "feat(worker): extract GPS lat/lng into activity samples"
```

---

## Task 3: Worker — downsampling de la polyligne

**Files:**
- Create: `worker/src/garmin_sync/transformers/route.py`
- Test: `worker/tests/test_transformers/test_route.py`

**Interfaces:**
- Produces: `build_route_polyline(samples: list[dict[str, Any]]) -> list[list[float]] | None`.
  Entrée : liste de samples (dicts avec clés `latitude`/`longitude` éventuellement `None`).
  Sortie : liste de points `[lng, lat]` (≤ 64, arrondis à 6 décimales), ou `None` si < 2 points GPS valides.

- [ ] **Step 1: Écrire le test qui échoue**

Create `worker/tests/test_transformers/test_route.py` :

```python
"""Tests for GPS route downsampling."""

from __future__ import annotations

from garmin_sync.transformers.route import build_route_polyline


def _sample(lat: float | None, lon: float | None) -> dict[str, float | None]:
    return {"latitude": lat, "longitude": lon}


def test_build_route_polyline_returns_lng_lat_pairs() -> None:
    samples = [_sample(45.1, 4.1), _sample(45.2, 4.2)]
    poly = build_route_polyline(samples)
    assert poly == [[4.1, 45.1], [4.2, 45.2]]


def test_build_route_polyline_none_when_under_two_points() -> None:
    assert build_route_polyline([_sample(45.1, 4.1)]) is None
    assert build_route_polyline([_sample(None, None), _sample(45.1, 4.1)]) is None


def test_build_route_polyline_skips_points_without_coords() -> None:
    samples = [_sample(45.1, 4.1), _sample(None, 4.2), _sample(45.3, 4.3)]
    poly = build_route_polyline(samples)
    assert poly == [[4.1, 45.1], [4.3, 45.3]]


def test_build_route_polyline_downsamples_to_64_keeping_ends() -> None:
    samples = [_sample(45.0 + i / 1000, 4.0 + i / 1000) for i in range(500)]
    poly = build_route_polyline(samples)
    assert poly is not None
    assert len(poly) == 64
    assert poly[0] == [4.0, 45.0]
    assert poly[-1] == [round(4.0 + 499 / 1000, 6), round(45.0 + 499 / 1000, 6)]
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `cd worker && uv run pytest tests/test_transformers/test_route.py -v`
Expected: FAIL (`ModuleNotFoundError: garmin_sync.transformers.route`).

- [ ] **Step 3: Implémenter la fonction**

Create `worker/src/garmin_sync/transformers/route.py` :

```python
"""Downsample GPS samples into a compact polyline for thumbnails and heatmaps."""

from __future__ import annotations

from typing import Any

_MAX_ROUTE_POINTS = 64


def build_route_polyline(samples: list[dict[str, Any]]) -> list[list[float]] | None:
    """Return a list of ``[lng, lat]`` points (<=64), or ``None`` if too few GPS points.

    Points are rounded to 6 decimals. The first and last GPS points are always kept;
    intermediate points are evenly spaced.
    """
    points = [
        [round(float(s["longitude"]), 6), round(float(s["latitude"]), 6)]
        for s in samples
        if s.get("latitude") is not None and s.get("longitude") is not None
    ]
    if len(points) < 2:
        return None
    if len(points) <= _MAX_ROUTE_POINTS:
        return points
    step = (len(points) - 1) / (_MAX_ROUTE_POINTS - 1)
    return [points[round(i * step)] for i in range(_MAX_ROUTE_POINTS)]
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `cd worker && uv run pytest tests/test_transformers/test_route.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add worker/src/garmin_sync/transformers/route.py worker/tests/test_transformers/test_route.py
git commit -m "feat(worker): add GPS route polyline downsampling"
```

---

## Task 4: Worker — écrire route_polyline lors du sync des samples

**Files:**
- Modify: `worker/src/garmin_sync/sync.py:112-148` (`_sync_missing_activity_samples`)
- Test: `worker/tests/test_sync.py`

**Interfaces:**
- Consumes: `transform_activity_samples` (Task 2), `build_route_polyline` (Task 3).
- Produces: helper `_persist_samples_and_route(db, user_id, activity_id, raw_details) -> None` — upsert les samples puis, si une polyligne existe, fait un `update` de `activities.route_polyline` filtré par `user_id` + `garmin_activity_id`.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter dans `worker/tests/test_sync.py` :

```python
def test_sync_writes_route_polyline_when_gps_present(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    fake_garmin_client.get_activity_details.return_value = {
        "activityDetailMetrics": [
            {"metrics": [{"key": "directLatitude", "value": 45.1},
                         {"key": "directLongitude", "value": 4.1}]},
            {"metrics": [{"key": "directLatitude", "value": 45.2},
                         {"key": "directLongitude", "value": 4.2}]},
        ]
    }

    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
            mode="activities_only",
        )

    activities_table = fake_admin_client.table.return_value
    update_calls = activities_table.update.call_args_list
    assert any("route_polyline" in call.args[0] for call in update_calls)
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `cd worker && uv run pytest tests/test_sync.py::test_sync_writes_route_polyline_when_gps_present -v`
Expected: FAIL (`update` jamais appelé / assertion False).

- [ ] **Step 3: Implémenter le helper et l'utiliser**

Dans `worker/src/garmin_sync/sync.py`, ajouter l'import en tête (à côté de l'import existant des transformers d'activités) :

```python
from garmin_sync.transformers.route import build_route_polyline
```

Remplacer le corps de la boucle de `_sync_missing_activity_samples` (lignes 128-148) par un appel au nouveau helper :

```python
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
```

Puis ajouter le helper juste après `_sync_missing_activity_samples` :

```python
def _persist_samples_and_route(
    db: Any, user_id: str, activity_id: int, client: Garmin
) -> None:
    """Fetch activity details, upsert samples, and write the downsampled route polyline."""
    raw_details = client.get_activity_details(str(activity_id))
    if not isinstance(raw_details, dict):
        return
    samples = transform_activity_samples(
        user_id=user_id,
        garmin_activity_id=activity_id,
        raw_details=raw_details,
    )
    if not samples:
        return
    db.table("activity_samples").upsert(
        samples,
        on_conflict="user_id,garmin_activity_id,sample_index",
    ).execute()
    polyline = build_route_polyline(samples)
    if polyline is not None:
        db.table("activities").update({"route_polyline": polyline}).eq(
            "user_id", user_id
        ).eq("garmin_activity_id", activity_id).execute()
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `cd worker && uv run pytest tests/test_sync.py -v`
Expected: PASS (anciens tests + nouveau). Le test `test_sync_user_fetches_missing_activity_samples` reste vert (l'upsert samples conserve le même `on_conflict`).

- [ ] **Step 5: Commit**

```bash
git add worker/src/garmin_sync/sync.py worker/tests/test_sync.py
git commit -m "feat(worker): persist route polyline alongside activity samples"
```

---

## Task 5: Worker — backfill GPS throttlé

**Files:**
- Modify: `worker/src/garmin_sync/config.py`
- Modify: `worker/src/garmin_sync/sync.py:90-110` (`_sync_activities`)
- Test: `worker/tests/test_config.py`
- Test: `worker/tests/test_sync.py`

**Interfaces:**
- Consumes: `get_settings().gps_backfill_batch` (int), `_persist_samples_and_route` (Task 4).
- Produces:
  - `Settings.gps_backfill_batch: int` (défaut 8).
  - `_activities_missing_gps(db, user_id, limit) -> list[int]` — IDs Garmin des activités sans `route_polyline`, triées `start_time desc`, limitées à `limit`.
  - `_sync_gps_backfill(db, user_id, client, limit) -> None` — appelle `_persist_samples_and_route` pour chaque candidat ; propage `_AbortSyncErrors`.

- [ ] **Step 1: Écrire le test config qui échoue**

Ajouter dans `worker/tests/test_config.py` :

```python
def test_gps_backfill_batch_defaults_to_8(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from garmin_sync.config import Settings

    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="x",
        fernet_key="a" * 43 + "=",
        worker_shared_token="t",
    )
    assert settings.gps_backfill_batch == 8
```

> Note : adapter les arguments à la signature existante de `Settings` dans le fichier si nécessaire (mêmes champs obligatoires que les autres tests de `test_config.py`).

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `cd worker && uv run pytest tests/test_config.py::test_gps_backfill_batch_defaults_to_8 -v`
Expected: FAIL (`AttributeError: gps_backfill_batch`).

- [ ] **Step 3: Ajouter le réglage**

Dans `worker/src/garmin_sync/config.py`, ajouter dans la classe `Settings` (après `openai_timeout_s`) :

```python
    gps_backfill_batch: int = Field(default=8)
```

- [ ] **Step 4: Vérifier le test config**

Run: `cd worker && uv run pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Écrire le test sync de backfill qui échoue**

Ajouter dans `worker/tests/test_sync.py` :

```python
def test_sync_backfills_activities_missing_gps(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    # No new activities this run, but one old activity lacks a route polyline.
    fake_garmin_client.get_activities_by_date.return_value = []
    table = fake_admin_client.table.return_value
    (
        table.select.return_value.eq.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value.data
    ) = [{"garmin_activity_id": 777}]
    fake_garmin_client.get_activity_details.return_value = {
        "activityDetailMetrics": [
            {"metrics": [{"key": "directLatitude", "value": 45.1},
                         {"key": "directLongitude", "value": 4.1}]},
            {"metrics": [{"key": "directLatitude", "value": 45.2},
                         {"key": "directLongitude", "value": 4.2}]},
        ]
    }

    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
            mode="activities_only",
        )

    fake_garmin_client.get_activity_details.assert_called_once_with("777")
```

- [ ] **Step 6: Lancer le test pour vérifier l'échec**

Run: `cd worker && uv run pytest tests/test_sync.py::test_sync_backfills_activities_missing_gps -v`
Expected: FAIL (`get_activity_details` non appelé : pas de backfill).

- [ ] **Step 7: Implémenter le backfill**

Dans `worker/src/garmin_sync/sync.py`, ajouter l'import config en tête :

```python
from garmin_sync.config import get_settings
```

Dans `_sync_activities`, à l'intérieur du `try`, après le bloc `if rows:` (toujours dans le `try`, pour que les `_AbortSyncErrors` remontent), ajouter l'appel au backfill :

```python
        if rows:
            db.table("activities").upsert(rows, on_conflict="user_id,garmin_activity_id").execute()
            _sync_missing_activity_samples(db, user_id, client, rows)
        _sync_gps_backfill(db, user_id, client, get_settings().gps_backfill_batch)
```

Ajouter les deux fonctions après `_persist_samples_and_route` :

```python
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
```

- [ ] **Step 8: Lancer toute la suite sync pour vérifier**

Run: `cd worker && uv run pytest tests/test_sync.py -v`
Expected: PASS. Vérifier en particulier que `test_sync_skips_existing_activity_samples` reste vert (le backfill ne s'y déclenche pas car la requête `is_` y renvoie le MagicMock par défaut → liste vide via le garde `isinstance`).

> Si `test_sync_skips_existing_activity_samples` régresse parce que le MagicMock par défaut renvoie un objet non-liste pour `.data`, c'est attendu : le garde `if not isinstance(rows, list): return []` neutralise le backfill. Aucune action requise.

- [ ] **Step 9: Lint + types worker**

Run: `cd worker && uv run ruff check . && uv run mypy src/`
Expected: aucun problème.

- [ ] **Step 10: Commit**

```bash
git add worker/src/garmin_sync/config.py worker/src/garmin_sync/sync.py worker/tests/test_config.py worker/tests/test_sync.py
git commit -m "feat(worker): throttled GPS backfill for activities without a route"
```

---

## Task 6: Frontend — dépendance MapLibre + util GeoJSON

**Files:**
- Modify: `package.json`
- Create: `lib/maps/route-geojson.ts`
- Modify: `lib/coach/activity-analysis.ts:22-32` (interface `ActivitySample`)
- Test: `tests/unit/maps/route-geojson.test.ts`

**Interfaces:**
- Produces:
  - `interface RoutePoint { latitude: number | null; longitude: number | null }`
  - `buildRouteGeoJson(samples: RoutePoint[]): GeoJsonLineFeature | null` où
    `GeoJsonLineFeature = { type: 'Feature'; geometry: { type: 'LineString'; coordinates: [number, number][] }; properties: Record<string, never> }`.
  - `routeBounds(coords: [number, number][]): [[number, number], [number, number]] | null` — `[[minLng,minLat],[maxLng,maxLat]]`.
  - `ActivitySample` gagne `latitude: number | null` et `longitude: number | null`.

- [ ] **Step 1: Installer la dépendance**

Run: `pnpm add maplibre-gl`
Expected: `maplibre-gl` ajouté à `dependencies` dans `package.json`.

- [ ] **Step 2: Écrire le test qui échoue**

Create `tests/unit/maps/route-geojson.test.ts` :

```ts
import { describe, expect, it } from 'vitest'
import { buildRouteGeoJson, routeBounds } from '@/lib/maps/route-geojson'

describe('buildRouteGeoJson', () => {
  it('builds a LineString from valid points', () => {
    const feature = buildRouteGeoJson([
      { latitude: 45.1, longitude: 4.1 },
      { latitude: 45.2, longitude: 4.2 },
    ])
    expect(feature).not.toBeNull()
    expect(feature?.geometry.coordinates).toEqual([
      [4.1, 45.1],
      [4.2, 45.2],
    ])
  })

  it('skips points without coordinates', () => {
    const feature = buildRouteGeoJson([
      { latitude: 45.1, longitude: 4.1 },
      { latitude: null, longitude: 4.2 },
      { latitude: 45.3, longitude: 4.3 },
    ])
    expect(feature?.geometry.coordinates).toEqual([
      [4.1, 45.1],
      [4.3, 45.3],
    ])
  })

  it('returns null with fewer than two valid points', () => {
    expect(buildRouteGeoJson([{ latitude: 45.1, longitude: 4.1 }])).toBeNull()
    expect(buildRouteGeoJson([])).toBeNull()
  })
})

describe('routeBounds', () => {
  it('computes the bounding box', () => {
    expect(
      routeBounds([
        [4.1, 45.1],
        [4.3, 45.0],
        [4.2, 45.4],
      ])
    ).toEqual([
      [4.1, 45.0],
      [4.3, 45.4],
    ])
  })

  it('returns null when empty', () => {
    expect(routeBounds([])).toBeNull()
  })
})
```

- [ ] **Step 3: Lancer le test pour vérifier l'échec**

Run: `pnpm test -- route-geojson`
Expected: FAIL (module introuvable).

- [ ] **Step 4: Implémenter l'util**

Create `lib/maps/route-geojson.ts` :

```ts
export interface RoutePoint {
  latitude: number | null
  longitude: number | null
}

export interface GeoJsonLineFeature {
  type: 'Feature'
  geometry: { type: 'LineString'; coordinates: [number, number][] }
  properties: Record<string, never>
}

function hasCoords(p: RoutePoint): p is { latitude: number; longitude: number } {
  return typeof p.latitude === 'number' && typeof p.longitude === 'number'
}

export function buildRouteGeoJson(samples: RoutePoint[]): GeoJsonLineFeature | null {
  const coordinates = samples
    .filter(hasCoords)
    .map((p) => [p.longitude, p.latitude] as [number, number])
  if (coordinates.length < 2) return null
  return { type: 'Feature', geometry: { type: 'LineString', coordinates }, properties: {} }
}

export function routeBounds(
  coords: [number, number][]
): [[number, number], [number, number]] | null {
  if (coords.length === 0) return null
  let minLng = coords[0][0]
  let maxLng = coords[0][0]
  let minLat = coords[0][1]
  let maxLat = coords[0][1]
  for (const [lng, lat] of coords) {
    if (lng < minLng) minLng = lng
    if (lng > maxLng) maxLng = lng
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
  }
  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ]
}
```

- [ ] **Step 5: Étendre le type `ActivitySample`**

Dans `lib/coach/activity-analysis.ts`, ajouter dans l'interface `ActivitySample` (après `speed_m_s: number | null`) :

```ts
  latitude: number | null
  longitude: number | null
```

- [ ] **Step 6: Lancer les tests pour vérifier le succès**

Run: `pnpm test -- route-geojson`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add package.json pnpm-lock.yaml lib/maps/route-geojson.ts lib/coach/activity-analysis.ts tests/unit/maps/route-geojson.test.ts
git commit -m "feat(maps): add maplibre-gl dep and route GeoJSON helpers"
```

---

## Task 7: Frontend — composant carte + intégration page détail

**Files:**
- Create: `app/(app)/_components/maps/activity-route-map.tsx`
- Modify: `app/(app)/history/[id]/page.tsx` (select samples + rendu carte)
- Test: `tests/unit/components/activity-route-map.test.tsx`

**Interfaces:**
- Consumes: `buildRouteGeoJson`, `routeBounds` (Task 6) ; `ActivitySample` avec lat/lng (Task 6).
- Produces: composant `ActivityRouteMap({ samples }: { readonly samples: ActivitySample[] })` — rend un conteneur de carte MapLibre ; ne rend `null` ni map si < 2 points GPS (le parent gère ce cas).

- [ ] **Step 1: Écrire le test qui échoue (maplibre mocké)**

Create `tests/unit/components/activity-route-map.test.tsx` :

```tsx
import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const addSource = vi.fn()
const addLayer = vi.fn()
const fitBounds = vi.fn()
const on = vi.fn((event: string, cb: () => void) => {
  if (event === 'load') cb()
})

vi.mock('maplibre-gl', () => ({
  default: {
    Map: vi.fn(() => ({ on, addSource, addLayer, fitBounds, remove: vi.fn() })),
  },
}))

import { ActivityRouteMap } from '@/app/(app)/_components/maps/activity-route-map'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

function sample(latitude: number | null, longitude: number | null): ActivitySample {
  return {
    sample_index: 0,
    sample_time: null,
    elapsed_s: null,
    distance_m: null,
    elevation_m: null,
    heart_rate_bpm: null,
    power_w: null,
    cadence_rpm: null,
    speed_m_s: null,
    latitude,
    longitude,
  }
}

describe('ActivityRouteMap', () => {
  it('adds the route source once the map loads', () => {
    render(<ActivityRouteMap samples={[sample(45.1, 4.1), sample(45.2, 4.2)]} />)
    expect(addSource).toHaveBeenCalledWith('route', expect.anything())
    expect(addLayer).toHaveBeenCalled()
    expect(fitBounds).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `pnpm test -- activity-route-map`
Expected: FAIL (composant introuvable).

- [ ] **Step 3: Implémenter le composant**

Create `app/(app)/_components/maps/activity-route-map.tsx` :

```tsx
'use client'

import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { buildRouteGeoJson, routeBounds } from '@/lib/maps/route-geojson'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

interface ActivityRouteMapProps {
  readonly samples: ActivitySample[]
  readonly height?: number
}

export function ActivityRouteMap({ samples, height = 360 }: ActivityRouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const container = containerRef.current
    const feature = buildRouteGeoJson(samples)
    if (!container || !feature) return

    const bounds = routeBounds(feature.geometry.coordinates)
    const map = new maplibregl.Map({
      container,
      style: DARK_STYLE,
      attributionControl: false,
    })

    map.on('load', () => {
      map.addSource('route', { type: 'geojson', data: feature })
      map.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#22d3ee', 'line-width': 3 },
      })
      if (bounds) map.fitBounds(bounds, { padding: 32, duration: 0 })
    })

    return () => {
      map.remove()
    }
  }, [samples])

  return <div ref={containerRef} style={{ height }} className="overflow-hidden rounded-md" />
}
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `pnpm test -- activity-route-map`
Expected: PASS.

- [ ] **Step 5: Intégrer dans la page détail**

Dans `app/(app)/history/[id]/page.tsx` :

(a) Étendre le `select` sur `activity_samples` (la requête dans `Promise.all`) pour inclure les coordonnées :

```ts
        .select(
          'sample_index, sample_time, elapsed_s, distance_m, elevation_m, heart_rate_bpm, power_w, cadence_rpm, speed_m_s, latitude, longitude'
        )
```

(b) Ajouter l'import dynamique du composant en tête de fichier (client-only, pas de SSR WebGL) :

```ts
import dynamic from 'next/dynamic'

const ActivityRouteMap = dynamic(
  () => import('../../_components/maps/activity-route-map').then((m) => m.ActivityRouteMap),
  { ssr: false }
)
```

> Retirer l'import statique de `ActivitySamplesChart` ? Non — le laisser. Ajouter seulement l'import dynamique ci-dessus.

(c) Calculer la présence d'une trace (après la ligne `const samples: ActivitySample[] = samplesRes.data ?? []`) :

```ts
  const gpsSampleCount = samples.filter(
    (s) => typeof s.latitude === 'number' && typeof s.longitude === 'number'
  ).length
```

(d) Rendre la carte juste avant le bloc `{samples.length > 0 && (` des "Courbes d'activité" :

```tsx
      {gpsSampleCount >= 2 && (
        <ChartCard title="Trace GPS" description="Parcours de l'activité d'après les données Garmin.">
          <ActivityRouteMap samples={samples} />
        </ChartCard>
      )}
```

- [ ] **Step 6: Vérifier typecheck + build + lint**

Run: `pnpm typecheck && pnpm lint`
Expected: aucun problème.
Run: `rm -rf .next && pnpm build`
Expected: build OK (le `rm -rf .next` évite le cache stale entre branches — piège connu du projet).

- [ ] **Step 7: Vérification manuelle (optionnelle mais recommandée)**

Avec une activité possédant du GPS en base, lancer `pnpm dev`, ouvrir `/history/<id>` et confirmer que la trace s'affiche sur fond sombre, cadrée sur le parcours. Si aucune activité n'a encore de GPS (backfill non exécuté), confirmer simplement que la page se rend sans la carte (pas d'erreur).

- [ ] **Step 8: Commit**

```bash
git add "app/(app)/_components/maps/activity-route-map.tsx" "app/(app)/history/[id]/page.tsx" tests/unit/components/activity-route-map.test.tsx
git commit -m "feat(history): render GPS route map on activity detail page"
```

---

## Task 8: Vérification finale du livrable

- [ ] **Step 1: Suite worker complète**

Run: `cd worker && uv run pytest -v && uv run ruff check . && uv run mypy src/`
Expected: tout vert.

- [ ] **Step 2: Suite frontend complète**

Run: `pnpm test && pnpm lint && pnpm typecheck && rm -rf .next && pnpm build`
Expected: tout vert.

- [ ] **Step 3: Rebuild + push image worker (pour test réel du sync/backfill)**

```bash
docker build -t tellebma/garmin-sync:latest worker/
docker push tellebma/garmin-sync:latest
```

> Rappel piège : le workflow Docker Hub ne build que sur `main`. Pendant le dev feature, ce push manuel est nécessaire pour tester le backfill GPS en réel sur UNRAID.

- [ ] **Step 4: Ouvrir la PR**

```bash
git push -u origin feat/carto-gps-livrable-a
gh pr create --base main --title "feat: GPS routes — Livrable A (pipeline data + carte détail)" \
  --body "Extraction GPS worker + migration + backfill throttlé + carte de trace sur la page détail. Spec: docs/superpowers/specs/2026-06-24-gps-routes-maps-design.md"
```

Attendre la CI verte (lint, typecheck, test, build, audit, secrets, Sonar, worker-ci) avant merge.

---

## Self-Review (effectué)

**Couverture du spec (sous-spec section par section)**
- §1 Modèle de données (lat/lng + route_polyline) → Task 1. ✅
- §2 Worker extraction lat/lng → Task 2 ; downsampling → Task 3 ; route_polyline au sync → Task 4 ; backfill throttlé + config → Task 5. ✅
- §3 Frontend `ActivityRouteMap` (trace simple) + dépendance maplibre → Tasks 6-7. ✅
- §3 vignettes SVG / heatmap / trace colorée → **explicitement Livrable B** (hors périmètre, documenté). ✅
- §4 Tests worker (extraction, downsampling, backfill) → Tasks 2/3/5 ; tests frontend (util, composant) → Tasks 6/7. ✅
- §5 Déploiement (migration additive, rebuild Docker) → Tasks 1/8. ✅

**Scan placeholders** : aucun TBD/TODO ; tout le code est fourni ; pas de « add error handling » vague (l'abort/skip est explicite et copié des patterns existants).

**Cohérence des types/signatures** :
- `build_route_polyline(samples) -> list[list[float]] | None` : défini Task 3, consommé Task 4 (même nom). ✅
- `_persist_samples_and_route(db, user_id, activity_id, client)` : défini Task 4, consommé Task 5 (même signature). ✅
- `buildRouteGeoJson` / `routeBounds` : définis Task 6, consommés Task 7 (mêmes noms). ✅
- `ActivitySample` étendu Task 6, utilisé Task 7. ✅
- `gps_backfill_batch` (config) ↔ `get_settings().gps_backfill_batch` (sync) : cohérent. ✅
