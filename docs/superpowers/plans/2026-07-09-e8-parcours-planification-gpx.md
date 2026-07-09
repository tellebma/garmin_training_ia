# E8 — Parcours géolocalisés & planification GPX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer une page `/routes` qui suggère des boucles auto (GraphHopper round-trip) ou permet de tracer un parcours manuellement (cols connus + points libres, routés via GraphHopper), avec export GPX et association/ajout au plan d'entraînement.

**Architecture:** Worker FastAPI expose 6 nouveaux endpoints (`/routes/suggest`, `/routes/build`, `/routes/{id}/gpx`, `/cols/refresh-area`, `/routes/{id}/apply-to-plan`, `/routes/{id}/link-session`) backés par 6 nouveaux modules Python dans `worker/src/garmin_sync/` (routing GraphHopper, geocoding Photon/Nominatim, génération auto, construction manuelle, export GPX, intégration au plan). Next.js ajoute une page `/routes` (2 onglets) + Server Actions + un Route Handler dédié au téléchargement GPX, en réutilisant `maplibre-gl` déjà en dépendance (pas de nouvelle lib de cartographie).

**Tech Stack:** FastAPI, httpx (async), gpxpy (nouveau), Supabase Postgres, Next.js App Router, maplibre-gl (existant), Server Actions.

## Global Constraints

- Sports limités à `run` + `bike` uniquement (pas de swim/rest/brick).
- Auth worker : JWT user via `_require_user_jwt` (voir `worker/src/garmin_sync/main.py`), jamais le shared token pour ces endpoints interactifs.
- **Convention de réponse** : tous les endpoints `/routes/*` et `/cols/*` renvoient **HTTP 200** avec un champ `status` discriminant (`"ok"` en succès, sinon un code d'erreur métier) — jamais de 404/409/422 REST. Seul `/routes/{id}/gpx` reste un vrai code HTTP (fichier téléchargeable). Toute exception non prévue passe par `report_endpoint_error(e, endpoint=..., user_id=...)` → `{status: "unexpected_error", error_id, type}`.
- Pas de `react-leaflet`/`leaflet` — utiliser `maplibre-gl` (`^5.24.0`, déjà en dépendance) comme `ActivityRouteMap`/`RouteThumbnail`/`RoutesHeatmap`.
- GPX export uniquement dans cette itération — **pas** de push automatique vers Garmin Connect (voir spec, écart documenté).
- `session_type='long'` fixe pour toute "sortie libre" créée via `apply-to-plan`.
- Couverture ≥95 % sur le code worker nouveau (gate SonarQube), tous les chemins d'erreur testés.
- RLS : écriture sur `routes` réservée au service role (worker) ; les users lisent leurs propres lignes uniquement.
- Référence spec : `docs/superpowers/specs/2026-07-09-e8-parcours-planification-gpx-design.md`.

## File Structure

**Worker Python — nouveaux fichiers :**
- `worker/src/garmin_sync/routing.py` — client GraphHopper async (round_trip + directions)
- `worker/src/garmin_sync/coach/geocoding.py` — client Photon + fallback Nominatim
- `worker/src/garmin_sync/coach/route_generator.py` — mode auto (estimate_user_speed, suggest_routes)
- `worker/src/garmin_sync/coach/route_builder.py` — mode manuel (build_route)
- `worker/src/garmin_sync/coach/gpx.py` — GeoJSON → GPX (gpxpy)
- `worker/src/garmin_sync/coach/plan_integration.py` — apply_route_to_plan, link_route_to_session

**Worker Python — fichiers modifiés :**
- `worker/pyproject.toml` (ajout `gpxpy`)
- `worker/src/garmin_sync/config.py` (ajout `graphhopper_url`, `graphhopper_timeout_s`, `photon_url`)
- `worker/src/garmin_sync/coach/overpass.py` (ajout `refresh_cols_in_area`)
- `worker/src/garmin_sync/main.py` (6 nouveaux endpoints)

**Migration :**
- `supabase/migrations/20260710000000_e8_routes_and_plan_integration.sql`

**Worker — tests :**
- `worker/tests/test_routing.py`
- `worker/tests/coach/test_geocoding.py`
- `worker/tests/coach/test_route_generator.py`
- `worker/tests/coach/test_route_builder.py`
- `worker/tests/coach/test_gpx.py`
- `worker/tests/coach/test_plan_integration.py`
- `worker/tests/coach/test_overpass.py` (étendu)
- `worker/tests/test_routes_endpoints.py`

**Frontend — nouveaux fichiers :**
- `app/actions/routes.ts`
- `app/api/routes/[id]/gpx/route.ts`
- `components/routes/RouteMap.tsx`
- `components/routes/RouteCard.tsx`
- `components/routes/AutoSuggestPanel.tsx`
- `components/routes/ColsPickerList.tsx`
- `components/routes/WaypointsList.tsx`
- `components/routes/StartOverrideInput.tsx`
- `components/routes/ManualBuildPanel.tsx`
- `components/routes/LinkToPlanActions.tsx`
- `components/routes/ExportActions.tsx`
- `components/routes/RouteTabs.tsx`
- `app/(app)/routes/page.tsx`

**Frontend — fichiers modifiés :**
- `lib/worker.ts` (types + wrappers pour les 6 nouveaux endpoints)
- `app/(app)/_components/session-card.tsx` (lien "Suggérer un parcours" pour run/bike)

**Infra :**
- `worker/docker-compose.prod.yml` (service `graphhopper`)
- `worker/deploy/README.md` + `worker/deploy/refresh-osm.sh` (nouveau)

**E2E :**
- `tests/e2e/routes.spec.ts`

---

### Task 1: Fondations worker — dépendance gpxpy, settings GraphHopper/Photon, migration DB

**Files:**
- Modify: `worker/pyproject.toml`
- Modify: `worker/src/garmin_sync/config.py`
- Create: `supabase/migrations/20260710000000_e8_routes_and_plan_integration.sql`
- Test: `worker/tests/test_config.py` (étend si existant, sinon vérifie via un test dédié)

**Interfaces:**
- Produces: `Settings.graphhopper_url: HttpUrl`, `Settings.graphhopper_timeout_s: int`, `Settings.photon_url: HttpUrl` — consommés par `routing.py` et `geocoding.py` (tasks suivantes). Table `public.routes` + colonnes `planned_sessions.route_id`/`origin` — consommées par toutes les tasks suivantes.

- [ ] **Step 1: Ajouter `gpxpy` aux dépendances**

Dans `worker/pyproject.toml`, ajouter la ligne dans `dependencies` (après `"apscheduler>=3.10.4",`) :

```toml
  "apscheduler>=3.10.4",
  "gpxpy>=1.6",
```

- [ ] **Step 2: Installer et vérifier**

Run: `cd worker && uv sync --all-groups`
Expected: `gpxpy` installé, pas d'erreur de résolution.

- [ ] **Step 3: Ajouter les settings GraphHopper/Photon**

Dans `worker/src/garmin_sync/config.py`, ajouter après `gps_backfill_batch: int = Field(default=8)` :

```python
    graphhopper_url: HttpUrl = Field(default=HttpUrl("http://graphhopper:8989"))
    graphhopper_timeout_s: int = Field(default=5, ge=1)
    photon_url: HttpUrl = Field(default=HttpUrl("http://graphhopper:2322"))
```

- [ ] **Step 4: Test de chargement des settings**

Créer `worker/tests/test_config.py` (s'il n'existe pas déjà — vérifier d'abord avec `ls worker/tests/test_config.py`) :

```python
from __future__ import annotations

from garmin_sync.config import Settings


def test_settings_have_graphhopper_and_photon_defaults() -> None:
    settings = Settings()
    assert str(settings.graphhopper_url).rstrip("/") == "http://graphhopper:8989"
    assert settings.graphhopper_timeout_s == 5
    assert str(settings.photon_url).rstrip("/") == "http://graphhopper:2322"
```

Si le fichier existe déjà avec d'autres tests, ajouter cette fonction à la fin plutôt que d'écraser le fichier.

- [ ] **Step 5: Run test**

Run: `cd worker && uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Écrire la migration DB**

Créer `supabase/migrations/20260710000000_e8_routes_and_plan_integration.sql` :

```sql
-- Parcours géolocalisés (mode auto GraphHopper round_trip + mode manuel waypoints).
create table public.routes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  planned_session_id uuid references public.planned_sessions(id) on delete set null,
  source text not null check (source in (
    'graphhopper_round_trip', 'graphhopper_waypoints', 'manual_gpx', 'imported'
  )),
  sport text not null check (sport in ('run', 'bike')),

  start_lat numeric(10, 7) not null,
  start_lng numeric(10, 7) not null,
  polyline jsonb not null,
  waypoints jsonb,

  distance_m numeric(10, 2) not null check (distance_m > 0),
  elevation_gain_m integer not null check (elevation_gain_m >= 0),
  estimated_duration_s integer check (estimated_duration_s is null or estimated_duration_s > 0),

  target_duration_s integer,
  target_elevation_gain_m integer,
  match_score numeric(5, 2),

  graphhopper_seed integer,
  generated_at timestamptz not null default now(),
  selected_at timestamptz
);

create index routes_user_session_idx on public.routes (user_id, planned_session_id);
create index routes_user_generated_idx on public.routes (user_id, generated_at desc);

alter table public.routes enable row level security;

create policy "users read own routes"
  on public.routes for select
  using (auth.uid() = user_id);

comment on table public.routes is
  'Parcours géolocalisés (auto GraphHopper round_trip ou tracé manuel via waypoints/cols). Écriture service-role uniquement.';

-- ─────────────────────────────────────────
-- Intégration au plan d'entraînement.

alter table public.planned_sessions
  add column if not exists route_id uuid references public.routes(id) on delete set null,
  add column if not exists origin text not null default 'planner'
    check (origin in ('planner', 'route'));

comment on column public.planned_sessions.origin is
  'planner = généré par E4/E5. route = sortie libre créée depuis /routes (apply-to-plan).';
```

- [ ] **Step 7: Appliquer la migration**

Utiliser `mcp__supabase__apply_migration` (project `peiyrqplymdlmlpsbqzu`) avec le nom `e8_routes_and_plan_integration` et le SQL ci-dessus.

- [ ] **Step 8: Vérifier le schéma appliqué**

Utiliser `mcp__supabase__list_tables` et confirmer la présence de `routes` avec RLS activé, et des colonnes `route_id`/`origin` sur `planned_sessions`.

- [ ] **Step 9: Commit**

```bash
git add worker/pyproject.toml worker/uv.lock worker/src/garmin_sync/config.py worker/tests/test_config.py supabase/migrations/20260710000000_e8_routes_and_plan_integration.sql
git commit -m "feat(e8): fondations — gpxpy, settings GraphHopper/Photon, table routes"
```

---

### Task 2: Client GraphHopper async (routing.py)

**Files:**
- Create: `worker/src/garmin_sync/routing.py`
- Test: `worker/tests/test_routing.py`

**Interfaces:**
- Consumes: `get_settings().graphhopper_url`, `.graphhopper_timeout_s` (Task 1)
- Produces: `RouteResult` (dataclass : `distance_m: float`, `ascend_m: float`, `descend_m: float`, `duration_s: int`, `coordinates: list[list[float]]`), `async def round_trip(*, profile: str, lat: float, lng: float, distance_m: float, seed: int) -> RouteResult`, `async def directions(*, profile: str, points: list[tuple[float, float]]) -> RouteResult`, `GraphhopperUnavailableError`, `NoRouteFoundError` — consommés par `route_generator.py` (Task 6) et `route_builder.py` (Task 7).

- [ ] **Step 1: Écrire les tests (mock httpx via respx)**

```python
# worker/tests/test_routing.py
from __future__ import annotations

import httpx
import pytest
import respx

from garmin_sync import routing

_PATH_RESPONSE = {
    "paths": [
        {
            "distance": 10800.0,
            "time": 3480000,
            "ascend": 195.0,
            "descend": 190.0,
            "points": {
                "type": "LineString",
                "coordinates": [[4.835, 45.764, 165.0], [4.84, 45.77, 180.0]],
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_round_trip_parses_first_path(monkeypatch: pytest.MonkeyPatch) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(url__regex=r".*/route").mock(
            return_value=httpx.Response(200, json=_PATH_RESPONSE)
        )
        result = await routing.round_trip(
            profile="foot", lat=45.764, lng=4.835, distance_m=10000, seed=42
        )
    assert result.distance_m == 10800.0
    assert result.ascend_m == 195.0
    assert result.duration_s == 3480
    assert result.coordinates[0] == [4.835, 45.764, 165.0]


@pytest.mark.asyncio
async def test_round_trip_raises_on_zero_paths() -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(url__regex=r".*/route").mock(
            return_value=httpx.Response(200, json={"paths": []})
        )
        with pytest.raises(routing.NoRouteFoundError):
            await routing.round_trip(
                profile="foot", lat=45.764, lng=4.835, distance_m=10000, seed=42
            )


@pytest.mark.asyncio
async def test_round_trip_raises_on_http_error() -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(url__regex=r".*/route").mock(return_value=httpx.Response(503))
        with pytest.raises(routing.GraphhopperUnavailableError):
            await routing.round_trip(
                profile="foot", lat=45.764, lng=4.835, distance_m=10000, seed=42
            )


@pytest.mark.asyncio
async def test_directions_sends_ordered_points_and_parses_result() -> None:
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(url__regex=r".*/route").mock(
            return_value=httpx.Response(200, json=_PATH_RESPONSE)
        )
        result = await routing.directions(
            profile="bike", points=[(45.764, 4.835), (45.90, 5.10), (45.764, 4.835)]
        )
    sent_points = route.calls.last.request.url.params.get_list("point")
    assert sent_points == ["45.764,4.835", "45.9,5.1", "45.764,4.835"]
    assert result.distance_m == 10800.0


@pytest.mark.asyncio
async def test_directions_raises_on_zero_paths() -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(url__regex=r".*/route").mock(
            return_value=httpx.Response(200, json={"paths": []})
        )
        with pytest.raises(routing.NoRouteFoundError):
            await routing.directions(profile="bike", points=[(45.764, 4.835), (45.90, 5.10)])
```

- [ ] **Step 2: Vérifier `pytest-asyncio` est configuré en mode `asyncio_mode = "auto"` (ou marquer les tests `@pytest.mark.asyncio`)**

Run: `grep -n "asyncio_mode" worker/pyproject.toml`
Expected: si absent, ajouter dans `worker/pyproject.toml` sous `[tool.pytest.ini_options]` (créer la section si elle n'existe pas) :
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```
(si la section existe déjà avec ce réglage, ne rien changer)

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/test_routing.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'garmin_sync.routing'`

- [ ] **Step 4: Implémenter `routing.py`**

```python
# worker/src/garmin_sync/routing.py
"""Async GraphHopper client — round-trip loop generation and multi-point directions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from garmin_sync.config import get_settings


class GraphhopperUnavailableError(Exception):
    """GraphHopper is unreachable or returned a server/timeout error."""


class NoRouteFoundError(Exception):
    """GraphHopper returned zero usable paths for the given request."""


@dataclass(frozen=True)
class RouteResult:
    distance_m: float
    ascend_m: float
    descend_m: float
    duration_s: int
    coordinates: list[list[float]]  # [lng, lat, ele]


def _base_url() -> str:
    return str(get_settings().graphhopper_url).rstrip("/")


def _parse_paths(payload: dict[str, Any]) -> RouteResult:
    paths = payload.get("paths", [])
    if not paths:
        raise NoRouteFoundError("GraphHopper returned zero paths")
    path = paths[0]
    points = path.get("points", {})
    return RouteResult(
        distance_m=float(path["distance"]),
        ascend_m=float(path.get("ascend", 0.0)),
        descend_m=float(path.get("descend", 0.0)),
        duration_s=round(float(path["time"]) / 1000),
        coordinates=points.get("coordinates", []),
    )


async def _get_route(params: list[tuple[str, str]]) -> RouteResult:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.graphhopper_timeout_s) as client:
            response = await client.get(f"{_base_url()}/route", params=params)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise GraphhopperUnavailableError(str(e)) from e
    return _parse_paths(response.json())


async def round_trip(
    *, profile: str, lat: float, lng: float, distance_m: float, seed: int
) -> RouteResult:
    """Request one round-trip loop candidate starting/ending at (lat, lng)."""
    params = [
        ("point", f"{lat},{lng}"),
        ("profile", profile),
        ("algorithm", "round_trip"),
        ("round_trip.distance", str(distance_m)),
        ("round_trip.seed", str(seed)),
        ("points_encoded", "false"),
        ("elevation", "true"),
    ]
    return await _get_route(params)


async def directions(*, profile: str, points: list[tuple[float, float]]) -> RouteResult:
    """Request a routed itinerary through an ordered list of (lat, lng) points."""
    params = [("point", f"{lat},{lng}") for lat, lng in points]
    params += [
        ("profile", profile),
        ("points_encoded", "false"),
        ("elevation", "true"),
    ]
    return await _get_route(params)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/test_routing.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Lint + types**

Run: `cd worker && uv run ruff check src/garmin_sync/routing.py tests/test_routing.py && uv run mypy src/garmin_sync/routing.py`
Expected: aucune erreur

- [ ] **Step 7: Commit**

```bash
git add worker/src/garmin_sync/routing.py worker/tests/test_routing.py worker/pyproject.toml
git commit -m "feat(e8): client GraphHopper async (round_trip + directions)"
```

---

### Task 3: Client geocoding (Photon + fallback Nominatim)

**Files:**
- Create: `worker/src/garmin_sync/coach/geocoding.py`
- Test: `worker/tests/coach/test_geocoding.py`

**Interfaces:**
- Consumes: `get_settings().photon_url` (Task 1)
- Produces: `GeocodeResult` (dataclass : `lat: float`, `lng: float`, `label: str`), `def search_address(query: str) -> list[GeocodeResult]` — consommé par `main.py` (Task 9) pour l'override d'adresse en mode auto et manuel.

- [ ] **Step 1: Écrire les tests**

```python
# worker/tests/coach/test_geocoding.py
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from garmin_sync.coach import geocoding

_PHOTON_RESPONSE = {
    "features": [
        {
            "geometry": {"coordinates": [4.8272, 45.7578]},
            "properties": {"name": "Place Bellecour", "city": "Lyon"},
        }
    ]
}

_NOMINATIM_RESPONSE = [
    {"lat": "45.7578", "lon": "4.8272", "display_name": "Place Bellecour, Lyon, France"}
]


def test_search_address_uses_photon_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.raise_for_status.return_value = None
    httpx_mock.get.return_value.json.return_value = _PHOTON_RESPONSE
    monkeypatch.setattr(geocoding, "httpx", httpx_mock)

    results = geocoding.search_address("Place Bellecour Lyon")

    assert len(results) == 1
    assert results[0].lat == pytest.approx(45.7578)
    assert results[0].lng == pytest.approx(4.8272)
    assert "Bellecour" in results[0].label
    # Only Photon was called — no fallback needed.
    assert httpx_mock.get.call_count == 1


def test_search_address_falls_back_to_nominatim_when_photon_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    httpx_mock = MagicMock()

    def _get(url: str, **_kwargs: object) -> MagicMock:
        response = MagicMock()
        if "nominatim" in url:
            response.raise_for_status.return_value = None
            response.json.return_value = _NOMINATIM_RESPONSE
            return response
        raise httpx.ConnectError("photon down")

    httpx_mock.get.side_effect = _get
    monkeypatch.setattr(geocoding, "httpx", httpx_mock)

    results = geocoding.search_address("Place Bellecour Lyon")

    assert len(results) == 1
    assert results[0].lat == pytest.approx(45.7578)
    assert "Bellecour" in results[0].label


def test_search_address_returns_empty_when_both_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    httpx_mock = MagicMock()
    httpx_mock.get.side_effect = httpx.ConnectError("down")
    monkeypatch.setattr(geocoding, "httpx", httpx_mock)

    assert geocoding.search_address("nowhere") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/coach/test_geocoding.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'garmin_sync.coach.geocoding'`

- [ ] **Step 3: Implémenter `geocoding.py`**

```python
# worker/src/garmin_sync/coach/geocoding.py
"""Address search — Photon (self-host, embarqué GraphHopper) avec fallback Nominatim public."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from garmin_sync.config import get_settings

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_TIMEOUT_S = 5.0
_MAX_RESULTS = 5
_HEADERS = {"User-Agent": "garmin-training-coach/1.0 (github.com/tellebma/garmin_training_ia)"}


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lng: float
    label: str


def _photon_url() -> str:
    return str(get_settings().photon_url).rstrip("/")


def _search_photon(query: str) -> list[GeocodeResult]:
    response = httpx.get(
        f"{_photon_url()}/api",
        params={"q": query, "limit": _MAX_RESULTS},
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    features = response.json().get("features", [])
    return [_parse_photon_feature(f) for f in features]


def _parse_photon_feature(feature: dict[str, Any]) -> GeocodeResult:
    lng, lat = feature["geometry"]["coordinates"]
    props = feature.get("properties", {})
    parts = [p for p in (props.get("name"), props.get("city")) if p]
    return GeocodeResult(lat=float(lat), lng=float(lng), label=", ".join(parts) or query_label(props))


def query_label(props: dict[str, Any]) -> str:
    return str(props.get("name") or props.get("street") or "Adresse trouvée")


def _search_nominatim(query: str) -> list[GeocodeResult]:
    response = httpx.get(
        _NOMINATIM_URL,
        params={"q": query, "format": "json", "limit": _MAX_RESULTS},
        headers=_HEADERS,
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    return [
        GeocodeResult(lat=float(r["lat"]), lng=float(r["lon"]), label=str(r["display_name"]))
        for r in response.json()
    ]


def search_address(query: str) -> list[GeocodeResult]:
    """Search an address via Photon, falling back to public Nominatim on any failure.

    Returns an empty list (never raises) when both providers fail — geocoding is a
    convenience override, not a blocking dependency.
    """
    try:
        return _search_photon(query)
    except (httpx.HTTPError, KeyError, ValueError):
        pass
    try:
        return _search_nominatim(query)
    except (httpx.HTTPError, KeyError, ValueError):
        return []
```

- [ ] **Step 4: Corriger le nom de variable `query` non défini dans `_parse_photon_feature`**

Le fallback `query_label(props)` référence `query` qui n'existe pas dans cette fonction — bug à corriger avant de lancer les tests. Remplacer `_parse_photon_feature` par :

```python
def _parse_photon_feature(feature: dict[str, Any]) -> GeocodeResult:
    lng, lat = feature["geometry"]["coordinates"]
    props = feature.get("properties", {})
    parts = [p for p in (props.get("name"), props.get("city")) if p]
    label = ", ".join(parts) if parts else str(props.get("name") or "Adresse trouvée")
    return GeocodeResult(lat=float(lat), lng=float(lng), label=label)
```

Et supprimer la fonction `query_label` (devenue inutile).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/coach/test_geocoding.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Lint + types**

Run: `cd worker && uv run ruff check src/garmin_sync/coach/geocoding.py tests/coach/test_geocoding.py && uv run mypy src/garmin_sync/coach/geocoding.py`
Expected: aucune erreur

- [ ] **Step 7: Commit**

```bash
git add worker/src/garmin_sync/coach/geocoding.py worker/tests/coach/test_geocoding.py
git commit -m "feat(e8): geocoding Photon + fallback Nominatim"
```

---

### Task 4: Extension Overpass — recherche de cols sur une zone arbitraire

**Files:**
- Modify: `worker/src/garmin_sync/coach/overpass.py`
- Modify: `worker/tests/coach/test_overpass.py`

**Interfaces:**
- Consumes: `_build_query`, `_parse_elevation`, `_now`, `_HEADERS`, `_OVERPASS_URL`, `_MAX_NAME_LENGTH` (déjà dans le module)
- Produces: `def refresh_cols_in_area(lat: float, lng: float, radius_m: int) -> int` (retourne le nombre de cols upsertés) — consommé par `main.py` (Task 9, endpoint `/cols/refresh-area`)

- [ ] **Step 1: Écrire le test (ajouté à la fin de `worker/tests/coach/test_overpass.py` existant)**

```python
def test_refresh_cols_in_area_upserts_and_returns_count(monkeypatch: Any) -> None:
    db = _FakeDb(None)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.json.return_value = _OVERPASS_RESPONSE
    monkeypatch.setattr(mod, "httpx", httpx_mock)

    count = mod.refresh_cols_in_area(45.0, 6.0, 20_000)

    assert count == 2
    httpx_mock.get.assert_called_once()
    query = httpx_mock.get.call_args.kwargs["params"]["data"]
    assert "around:20000,45.0,6.0" in query
    assert db.cols_query.upserted is not None
    assert len(db.cols_query.upserted) == 2


def test_refresh_cols_in_area_caps_radius_at_50km(monkeypatch: Any) -> None:
    db = _FakeDb(None)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.json.return_value = {"elements": []}
    monkeypatch.setattr(mod, "httpx", httpx_mock)

    mod.refresh_cols_in_area(45.0, 6.0, 999_000)

    query = httpx_mock.get.call_args.kwargs["params"]["data"]
    assert "around:50000,45.0,6.0" in query


def test_refresh_cols_in_area_returns_zero_on_overpass_failure(monkeypatch: Any) -> None:
    db = _FakeDb(None)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.side_effect = mod.httpx.ConnectError("down") if hasattr(
        mod.httpx, "ConnectError"
    ) else Exception("down")
    monkeypatch.setattr(mod, "httpx", httpx_mock)

    assert mod.refresh_cols_in_area(45.0, 6.0, 20_000) == 0
```

Note : le dernier test utilise un `httpx.ConnectError` réel — remplacer par un import direct en tête de fichier plutôt que le `hasattr` défensif ci-dessus (simplification) :

```python
import httpx as _real_httpx
...
httpx_mock.get.side_effect = _real_httpx.ConnectError("down")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/coach/test_overpass.py -v -k refresh_cols_in_area`
Expected: FAIL avec `AttributeError: module 'garmin_sync.coach.overpass' has no attribute 'refresh_cols_in_area'`

- [ ] **Step 3: Implémenter `refresh_cols_in_area` (ajouté à la fin de `overpass.py`)**

```python
_AREA_MAX_RADIUS_M = 50_000


def _build_area_query(lat: float, lng: float, radius_m: int) -> str:
    capped = min(radius_m, _AREA_MAX_RADIUS_M)
    return f"[out:json][timeout:25];node[mountain_pass=yes](around:{capped},{lat},{lng});out;"


def refresh_cols_in_area(lat: float, lng: float, radius_m: int) -> int:
    """Fetch cols from Overpass for an arbitrary map area (not tied to the user's home).

    Unlike `refresh_nearby_cols`, this always calls Overpass — no staleness cache,
    since the area is chosen ad-hoc by the user panning the map. Returns the number
    of cols upserted, or 0 on any Overpass failure (fail-open: caller shows an empty
    list for that area, not a blocking error).
    """
    try:
        response = httpx.get(
            _OVERPASS_URL,
            params={"data": _build_area_query(lat, lng, radius_m)},
            headers=_HEADERS,
            timeout=_TIMEOUT_S,
        )
        response.raise_for_status()
        elements = response.json().get("elements", [])
    except Exception:
        return 0

    rows = [
        {
            "osm_id": element["id"],
            "name": (element.get("tags", {}).get("name") or f"Col (OSM #{element['id']})")[
                :_MAX_NAME_LENGTH
            ],
            "latitude": element["lat"],
            "longitude": element["lon"],
            "elevation_m": _parse_elevation(element.get("tags", {}).get("ele")),
            "fetched_at": _now().isoformat(),
        }
        for element in elements
        if element.get("type") == "node" and "lat" in element and "lon" in element
    ]
    if rows:
        get_admin_client().table("cols").upsert(rows, on_conflict="osm_id").execute()
    return len(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/coach/test_overpass.py -v`
Expected: PASS (tous les tests, existants + nouveaux)

- [ ] **Step 5: Lint + types**

Run: `cd worker && uv run ruff check src/garmin_sync/coach/overpass.py tests/coach/test_overpass.py && uv run mypy src/garmin_sync/coach/overpass.py`
Expected: aucune erreur (le `except Exception` générique est intentionnel ici — fail-open documenté — vérifier que `ruff` ne le bloque pas ; si `BLE001` bloque, ajouter `# noqa: BLE001` avec le commentaire déjà présent comme justification)

- [ ] **Step 6: Commit**

```bash
git add worker/src/garmin_sync/coach/overpass.py worker/tests/coach/test_overpass.py
git commit -m "feat(e8): overpass — recherche de cols sur une zone arbitraire"
```

---

### Task 5: Export GPX (GeoJSON → GPX via gpxpy)

**Files:**
- Create: `worker/src/garmin_sync/coach/gpx.py`
- Test: `worker/tests/coach/test_gpx.py`

**Interfaces:**
- Consumes: rien de nouveau (fonction pure)
- Produces: `def geojson_to_gpx(coordinates: list[list[float]], *, name: str) -> str` — consommé par `main.py` (Task 9, endpoint `GET /routes/{id}/gpx`)

- [ ] **Step 1: Écrire les tests**

```python
# worker/tests/coach/test_gpx.py
from __future__ import annotations

import gpxpy

from garmin_sync.coach.gpx import geojson_to_gpx


def test_geojson_to_gpx_produces_valid_gpx_with_correct_points() -> None:
    coordinates = [[4.835, 45.764, 165.0], [4.84, 45.77, 180.0], [4.835, 45.764, 165.0]]

    xml = geojson_to_gpx(coordinates, name="Run endurance — 2026-07-10")

    parsed = gpxpy.parse(xml)
    assert len(parsed.tracks) == 1
    assert parsed.tracks[0].name == "Run endurance — 2026-07-10"
    points = parsed.tracks[0].segments[0].points
    assert len(points) == 3
    assert points[0].longitude == 4.835
    assert points[0].latitude == 45.764
    assert points[0].elevation == 165.0


def test_geojson_to_gpx_handles_missing_elevation() -> None:
    coordinates = [[4.835, 45.764], [4.84, 45.77]]

    xml = geojson_to_gpx(coordinates, name="Sans dénivelé")

    parsed = gpxpy.parse(xml)
    points = parsed.tracks[0].segments[0].points
    assert points[0].elevation is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/coach/test_gpx.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'garmin_sync.coach.gpx'`

- [ ] **Step 3: Implémenter `gpx.py`**

```python
# worker/src/garmin_sync/coach/gpx.py
"""GeoJSON LineString → GPX 1.1 export (gpxpy)."""

from __future__ import annotations

import gpxpy.gpx


def geojson_to_gpx(coordinates: list[list[float]], *, name: str) -> str:
    """Build a GPX 1.1 XML string from a list of [lng, lat, ele?] coordinates."""
    gpx = gpxpy.gpx.GPX()
    track = gpxpy.gpx.GPXTrack(name=name)
    gpx.tracks.append(track)
    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)

    for coord in coordinates:
        lng, lat = coord[0], coord[1]
        elevation = coord[2] if len(coord) > 2 else None
        segment.points.append(
            gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lng, elevation=elevation)
        )

    return gpx.to_xml()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/coach/test_gpx.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lint + types**

Run: `cd worker && uv run ruff check src/garmin_sync/coach/gpx.py tests/coach/test_gpx.py && uv run mypy src/garmin_sync/coach/gpx.py`
Expected: aucune erreur

- [ ] **Step 6: Commit**

```bash
git add worker/src/garmin_sync/coach/gpx.py worker/tests/coach/test_gpx.py
git commit -m "feat(e8): export GPX (GeoJSON vers GPX 1.1 via gpxpy)"
```

---

### Task 6: Générateur de boucles auto (route_generator.py)

**Files:**
- Create: `worker/src/garmin_sync/coach/route_generator.py`
- Test: `worker/tests/coach/test_route_generator.py`

**Interfaces:**
- Consumes: `routing.round_trip` (Task 2), `get_admin_client` (existant)
- Produces: `class SessionNotFoundForUserError(Exception)`, `class NoStartCoordsError(Exception)`, `class NoValidRoutesError(Exception)`, `async def suggest_routes(*, user_id: str, sport: str | None, target_duration_s: int | None, target_elevation_gain_m: int | None, planned_session_id: str | None, start_override: dict[str, float] | None) -> dict[str, Any]` — consommé par `main.py` (Task 9, endpoint `/routes/suggest`)

- [ ] **Step 1: Écrire les tests**

```python
# worker/tests/coach/test_route_generator.py
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from garmin_sync import routing
from garmin_sync.coach import route_generator as mod


class _FakeQuery:
    def __init__(self, rows: Any) -> None:
        self._rows = rows
        self.inserted: list[dict[str, Any]] | None = None
        self._filters: dict[str, Any] = {}

    def select(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def eq(self, key: str, value: Any) -> _FakeQuery:
        self._filters[key] = value
        return self

    def gte(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def not_(self) -> _FakeQuery:  # pragma: no cover - chained via property below
        return self

    def maybe_single(self) -> _FakeQuery:
        return self

    def single(self) -> _FakeQuery:
        return self

    def insert(self, rows: list[dict[str, Any]]) -> _FakeQuery:
        self.inserted = rows
        return self

    def execute(self) -> Any:
        class _R:
            data = self._rows

        return _R()

    @property
    def not_chain(self) -> _FakeQuery:
        return self


class _FakeDb:
    def __init__(self, *, activities: list[dict[str, Any]], profile: dict[str, Any] | None) -> None:
        self.activities_query = _FakeQuery(activities)
        self.profile_query = _FakeQuery(profile)
        self.routes_query = _FakeQuery(None)

    def table(self, name: str) -> _FakeQuery:
        if name == "activities":
            return self.activities_query
        if name == "athlete_profiles":
            return self.profile_query
        if name == "routes":
            return self.routes_query
        raise AssertionError(f"unexpected table {name}")


def _route_result(distance_m: float, ascend_m: float) -> routing.RouteResult:
    return routing.RouteResult(
        distance_m=distance_m,
        ascend_m=ascend_m,
        descend_m=ascend_m,
        duration_s=round(distance_m / 3.0),
        coordinates=[[4.835, 45.764, 165.0], [4.84, 45.77, 180.0]],
    )


@pytest.mark.asyncio
async def test_suggest_routes_returns_top_3_scored_by_elevation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(
        activities=[
            {"distance_m": 10000, "duration_s": 3000},
            {"distance_m": 12000, "duration_s": 3600},
            {"distance_m": 8000, "duration_s": 2400},
        ],
        profile={"lat": 45.764, "lon": 4.835},
    )
    db.routes_query = _FakeQuery([{"id": "r1"}, {"id": "r2"}, {"id": "r3"}])
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    # 8 candidates generated, varying elevation so scoring is deterministic.
    results = [_route_result(10000 + i * 50, ascend_m=100 + i * 20) for i in range(8)]
    monkeypatch.setattr(
        mod.routing, "round_trip", AsyncMock(side_effect=results)
    )

    out = await mod.suggest_routes(
        user_id="u1",
        sport="run",
        target_duration_s=3600,
        target_elevation_gain_m=150,
        planned_session_id=None,
        start_override=None,
    )

    assert out["status"] == "ok"
    assert len(out["routes"]) == 3
    assert db.routes_query.inserted is not None
    assert len(db.routes_query.inserted) == 3
    assert all(r["source"] == "graphhopper_round_trip" for r in db.routes_query.inserted)


@pytest.mark.asyncio
async def test_suggest_routes_uses_fallback_speed_when_not_enough_activities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(activities=[], profile={"lat": 45.764, "lon": 4.835})
    db.routes_query = _FakeQuery([{"id": "r1"}])
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(
        mod.routing,
        "round_trip",
        AsyncMock(return_value=_route_result(3.33 * 3600, ascend_m=100)),
    )

    out = await mod.suggest_routes(
        user_id="u1",
        sport="run",
        target_duration_s=3600,
        target_elevation_gain_m=None,
        planned_session_id=None,
        start_override=None,
    )

    assert out["estimated_user_speed_mps"] == pytest.approx(mod.FALLBACK_SPEED_MPS["run"])


@pytest.mark.asyncio
async def test_suggest_routes_raises_no_start_coords_without_profile_or_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(activities=[], profile={"lat": None, "lon": None})
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    with pytest.raises(mod.NoStartCoordsError):
        await mod.suggest_routes(
            user_id="u1",
            sport="run",
            target_duration_s=3600,
            target_elevation_gain_m=None,
            planned_session_id=None,
            start_override=None,
        )


@pytest.mark.asyncio
async def test_suggest_routes_raises_no_valid_routes_when_all_out_of_tolerance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(activities=[], profile={"lat": 45.764, "lon": 4.835})
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    # All candidates wildly off target distance (target ~ 3.33*3600 = ~12000m).
    monkeypatch.setattr(
        mod.routing, "round_trip", AsyncMock(return_value=_route_result(100.0, ascend_m=10))
    )

    with pytest.raises(mod.NoValidRoutesError):
        await mod.suggest_routes(
            user_id="u1",
            sport="run",
            target_duration_s=3600,
            target_elevation_gain_m=None,
            planned_session_id=None,
            start_override=None,
        )


@pytest.mark.asyncio
async def test_suggest_routes_uses_start_override_instead_of_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(activities=[], profile={"lat": None, "lon": None})
    db.routes_query = _FakeQuery([{"id": "r1"}])
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    captured: dict[str, Any] = {}

    async def _fake_round_trip(**kwargs: Any) -> routing.RouteResult:
        captured.update(kwargs)
        return _route_result(3.33 * 3600, ascend_m=100)

    monkeypatch.setattr(mod.routing, "round_trip", _fake_round_trip)

    await mod.suggest_routes(
        user_id="u1",
        sport="run",
        target_duration_s=3600,
        target_elevation_gain_m=None,
        planned_session_id=None,
        start_override={"lat": 48.85, "lng": 2.35},
    )

    assert captured["lat"] == 48.85
    assert captured["lng"] == 2.35
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/coach/test_route_generator.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'garmin_sync.coach.route_generator'`

- [ ] **Step 3: Implémenter `route_generator.py`**

```python
# worker/src/garmin_sync/coach/route_generator.py
"""Mode auto : suggère 3 boucles géolocalisées matchant durée + dénivelé cible."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from garmin_sync import routing
from garmin_sync.supabase_client import get_admin_client

CANDIDATES_TO_GENERATE = 8
CANDIDATES_TO_RETURN = 3
DISTANCE_TOLERANCE_PCT = 0.20
FALLBACK_SPEED_MPS: dict[str, float] = {"run": 3.33, "bike": 7.77}
_MIN_VALID_ACTIVITIES = 3
_MIN_DURATION_S = 600
_MIN_DISTANCE_M = 1000
_ACTIVITY_WINDOW_DAYS = 30


class NoStartCoordsError(Exception):
    """No profile lat/lon and no start_override provided."""


class NoValidRoutesError(Exception):
    """All GraphHopper candidates were rejected (errors or out of distance tolerance)."""


def _profile_for_sport(sport: str) -> str:
    return "bike" if sport == "bike" else "foot"


def estimate_user_speed(user_id: str, sport: str) -> float:
    """Rolling 30-day average speed (m/s) for this user+sport, or a fallback constant."""
    db = get_admin_client()
    since = (datetime.now(UTC) - timedelta(days=_ACTIVITY_WINDOW_DAYS)).isoformat()
    rows = cast(
        "list[dict[str, Any]]",
        db.table("activities")
        .select("distance_m, duration_s")
        .eq("user_id", user_id)
        .eq("sport", sport)
        .gte("start_time", since)
        .execute()
        .data
        or [],
    )
    valid = [
        r
        for r in rows
        if r.get("distance_m") and r.get("duration_s")
        and r["duration_s"] >= _MIN_DURATION_S
        and r["distance_m"] >= _MIN_DISTANCE_M
    ]
    if len(valid) < _MIN_VALID_ACTIVITIES:
        return FALLBACK_SPEED_MPS[sport]
    total_distance = sum(float(r["distance_m"]) for r in valid)
    total_duration = sum(float(r["duration_s"]) for r in valid)
    return total_distance / total_duration


def _resolve_start(
    user_id: str, start_override: dict[str, float] | None
) -> tuple[float, float]:
    if start_override is not None:
        return start_override["lat"], start_override["lng"]
    db = get_admin_client()
    profile = cast(
        "dict[str, Any] | None",
        db.table("athlete_profiles")
        .select("lat, lon")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
        .data,
    )
    if not profile or profile.get("lat") is None or profile.get("lon") is None:
        raise NoStartCoordsError("no athlete_profiles.lat/lon and no override")
    return float(profile["lat"]), float(profile["lon"])


def _score(elevation_actual: float, target_elevation_gain_m: int | None) -> float:
    if target_elevation_gain_m is None:
        return 0.0
    return abs(elevation_actual - target_elevation_gain_m)


async def suggest_routes(
    *,
    user_id: str,
    sport: str | None,
    target_duration_s: int | None,
    target_elevation_gain_m: int | None,
    planned_session_id: str | None,
    start_override: dict[str, float] | None,
) -> dict[str, Any]:
    """Generate up to 3 round-trip loop candidates matching duration + elevation."""
    if sport is None or target_duration_s is None:
        msg = "sport and target_duration_s are required when planned_session_id is absent"
        raise ValueError(msg)

    start_lat, start_lng = _resolve_start(user_id, start_override)
    speed = estimate_user_speed(user_id, sport)
    target_distance_m = target_duration_s * speed
    profile = _profile_for_sport(sport)

    seeds = [random.randint(1, 1_000_000) for _ in range(CANDIDATES_TO_GENERATE)]
    outcomes = await asyncio.gather(
        *[
            routing.round_trip(
                profile=profile, lat=start_lat, lng=start_lng,
                distance_m=target_distance_m, seed=seed,
            )
            for seed in seeds
        ],
        return_exceptions=True,
    )

    candidates: list[tuple[int, routing.RouteResult]] = []
    for seed, outcome in zip(seeds, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            continue
        ratio = outcome.distance_m / target_distance_m if target_distance_m > 0 else 0
        if 1 - DISTANCE_TOLERANCE_PCT <= ratio <= 1 + DISTANCE_TOLERANCE_PCT:
            candidates.append((seed, outcome))

    if not candidates:
        raise NoValidRoutesError("no candidate within distance tolerance")

    candidates.sort(key=lambda item: _score(item[1].ascend_m, target_elevation_gain_m))
    top = candidates[:CANDIDATES_TO_RETURN]

    rows = [
        {
            "user_id": user_id,
            "planned_session_id": planned_session_id,
            "source": "graphhopper_round_trip",
            "sport": sport,
            "start_lat": start_lat,
            "start_lng": start_lng,
            "polyline": {"type": "LineString", "coordinates": result.coordinates},
            "distance_m": result.distance_m,
            "elevation_gain_m": round(result.ascend_m),
            "estimated_duration_s": (
                round(result.distance_m / speed) if speed > 0 else None
            ),
            "target_duration_s": target_duration_s,
            "target_elevation_gain_m": target_elevation_gain_m,
            "match_score": _score(result.ascend_m, target_elevation_gain_m),
            "graphhopper_seed": seed,
        }
        for seed, result in top
    ]
    inserted = get_admin_client().table("routes").insert(rows).execute().data

    return {
        "status": "ok",
        "routes": inserted,
        "target": {
            "duration_s": target_duration_s,
            "elevation_gain_m": target_elevation_gain_m,
            "sport": sport,
        },
        "estimated_user_speed_mps": speed,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/coach/test_route_generator.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Lint + types**

Run: `cd worker && uv run ruff check src/garmin_sync/coach/route_generator.py tests/coach/test_route_generator.py && uv run mypy src/garmin_sync/coach/route_generator.py`
Expected: aucune erreur (ajuster les `cast`/annotations si mypy signale un type imprécis sur les résultats Supabase)

- [ ] **Step 6: Commit**

```bash
git add worker/src/garmin_sync/coach/route_generator.py worker/tests/coach/test_route_generator.py
git commit -m "feat(e8): générateur de boucles auto (route_generator)"
```

---

### Task 7: Construction manuelle de parcours (route_builder.py)

**Files:**
- Create: `worker/src/garmin_sync/coach/route_builder.py`
- Test: `worker/tests/coach/test_route_builder.py`

**Interfaces:**
- Consumes: `routing.directions` (Task 2), `route_generator.estimate_user_speed` (Task 6), `route_generator._profile_for_sport` (Task 6, importé directement — même précédent que `_TSS_PER_HOUR`/`_load_today_banister_state`)
- Produces: `async def build_route(*, user_id: str, sport: str, start: dict[str, float], waypoints: list[dict[str, Any]]) -> dict[str, Any]` (lève `routing.NoRouteFoundError`, `routing.GraphhopperUnavailableError`) — consommé par `main.py` (Task 9, endpoint `/routes/build`)

- [ ] **Step 1: Écrire les tests**

```python
# worker/tests/coach/test_route_builder.py
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from garmin_sync import routing
from garmin_sync.coach import route_builder as mod


class _FakeQuery:
    def __init__(self) -> None:
        self.inserted: list[dict[str, Any]] | None = None

    def insert(self, rows: list[dict[str, Any]]) -> _FakeQuery:
        self.inserted = rows
        return self

    def execute(self) -> Any:
        class _R:
            data = [{"id": "route-1"}]

        return _R()


class _FakeDb:
    def __init__(self) -> None:
        self.routes_query = _FakeQuery()

    def table(self, name: str) -> _FakeQuery:
        assert name == "routes"
        return self.routes_query


def _route_result() -> routing.RouteResult:
    return routing.RouteResult(
        distance_m=42000.0,
        ascend_m=850.0,
        descend_m=820.0,
        duration_s=7200,
        coordinates=[[4.835, 45.764, 165.0], [5.10, 45.90, 2600.0], [4.835, 45.764, 165.0]],
    )


@pytest.mark.asyncio
async def test_build_route_calls_directions_with_ordered_points_and_inserts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb()
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(mod, "estimate_user_speed", lambda *_a, **_k: 7.77)
    captured: dict[str, Any] = {}

    async def _fake_directions(**kwargs: Any) -> routing.RouteResult:
        captured.update(kwargs)
        return _route_result()

    monkeypatch.setattr(mod.routing, "directions", _fake_directions)

    out = await mod.build_route(
        user_id="u1",
        sport="bike",
        start={"lat": 45.764, "lng": 4.835},
        waypoints=[{"lat": 45.90, "lng": 5.10, "col_id": "col-galibier"}],
    )

    assert out["status"] == "ok"
    assert captured["profile"] == "bike"
    assert captured["points"] == [(45.764, 4.835), (45.90, 5.10), (45.764, 4.835)]
    assert db.routes_query.inserted is not None
    row = db.routes_query.inserted[0]
    assert row["source"] == "graphhopper_waypoints"
    assert row["waypoints"] == [{"lat": 45.90, "lng": 5.10, "col_id": "col-galibier"}]
    assert row["elevation_gain_m"] == 850


@pytest.mark.asyncio
async def test_build_route_propagates_no_route_found(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb()
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(mod, "estimate_user_speed", lambda *_a, **_k: 3.33)
    monkeypatch.setattr(
        mod.routing,
        "directions",
        AsyncMock(side_effect=routing.NoRouteFoundError("no path")),
    )

    with pytest.raises(routing.NoRouteFoundError):
        await mod.build_route(
            user_id="u1",
            sport="run",
            start={"lat": 45.764, "lng": 4.835},
            waypoints=[{"lat": 0.0, "lng": 0.0}],
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/coach/test_route_builder.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'garmin_sync.coach.route_builder'`

- [ ] **Step 3: Implémenter `route_builder.py`**

```python
# worker/src/garmin_sync/coach/route_builder.py
"""Mode manuel : route un parcours à travers des waypoints ordonnés (cols ou libres)."""

from __future__ import annotations

from typing import Any

from garmin_sync import routing
from garmin_sync.coach.route_generator import _profile_for_sport, estimate_user_speed
from garmin_sync.supabase_client import get_admin_client


async def build_route(
    *,
    user_id: str,
    sport: str,
    start: dict[str, float],
    waypoints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Route départ → waypoints (dans l'ordre) → retour départ, via GraphHopper directions.

    Raises `routing.NoRouteFoundError` / `routing.GraphhopperUnavailableError` — le
    caller (endpoint) les traduit en `{status: ...}`.
    """
    profile = _profile_for_sport(sport)
    points: list[tuple[float, float]] = [(start["lat"], start["lng"])]
    points += [(wp["lat"], wp["lng"]) for wp in waypoints]
    points.append((start["lat"], start["lng"]))

    result = await routing.directions(profile=profile, points=points)
    speed = estimate_user_speed(user_id, sport)

    row = {
        "user_id": user_id,
        "planned_session_id": None,
        "source": "graphhopper_waypoints",
        "sport": sport,
        "start_lat": start["lat"],
        "start_lng": start["lng"],
        "polyline": {"type": "LineString", "coordinates": result.coordinates},
        "waypoints": waypoints,
        "distance_m": result.distance_m,
        "elevation_gain_m": round(result.ascend_m),
        "estimated_duration_s": round(result.distance_m / speed) if speed > 0 else None,
        "target_duration_s": None,
        "target_elevation_gain_m": None,
        "match_score": None,
        "graphhopper_seed": None,
    }
    inserted = get_admin_client().table("routes").insert([row]).execute().data
    return {"status": "ok", "route": inserted[0] if inserted else row}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/coach/test_route_builder.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lint + types**

Run: `cd worker && uv run ruff check src/garmin_sync/coach/route_builder.py tests/coach/test_route_builder.py && uv run mypy src/garmin_sync/coach/route_builder.py`
Expected: aucune erreur (l'import de `_profile_for_sport` privé cross-module est un précédent déjà établi dans le codebase — voir `_load_today_banister_state` importé dans `main.py`)

- [ ] **Step 6: Commit**

```bash
git add worker/src/garmin_sync/coach/route_builder.py worker/tests/coach/test_route_builder.py
git commit -m "feat(e8): construction manuelle de parcours (route_builder)"
```

---

### Task 8: Intégration au plan (plan_integration.py)

**Files:**
- Create: `worker/src/garmin_sync/coach/plan_integration.py`
- Test: `worker/tests/coach/test_plan_integration.py`

**Interfaces:**
- Consumes: `garmin_sync.coach.planner._TSS_PER_HOUR` (existant, import privé cross-module — précédent déjà établi)
- Produces: `class RouteNotFoundError(Exception)`, `class NoActivePlanError(Exception)`, `class SessionConflictError(Exception)` (attributs `existing_sport`, `existing_session_type`), `class DateOutOfRangeError(Exception)`, `class InvalidSessionError(Exception)`, `def apply_route_to_plan(*, user_id: str, route_id: str, date: str, force: bool = False) -> dict[str, Any]`, `def link_route_to_session(*, user_id: str, route_id: str, planned_session_id: str) -> dict[str, Any]` — consommés par `main.py` (Task 9)

- [ ] **Step 1: Écrire les tests**

```python
# worker/tests/coach/test_plan_integration.py
from __future__ import annotations

from typing import Any

import pytest

from garmin_sync.coach import plan_integration as mod


class _FakeQuery:
    def __init__(self, rows: Any) -> None:
        self._rows = rows
        self.updated: dict[str, Any] | None = None
        self._filters: list[tuple[str, Any]] = []

    def select(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def eq(self, key: str, value: Any) -> _FakeQuery:
        self._filters.append((key, value))
        return self

    def maybe_single(self) -> _FakeQuery:
        return self

    def update(self, values: dict[str, Any]) -> _FakeQuery:
        self.updated = values
        return self

    def execute(self) -> Any:
        class _R:
            data = self._rows

        return _R()


class _FakeDb:
    def __init__(
        self,
        *,
        route: dict[str, Any] | None,
        plan: dict[str, Any] | None,
        session: dict[str, Any] | None,
    ) -> None:
        self.routes_query = _FakeQuery(route)
        self.plans_query = _FakeQuery(plan)
        self.sessions_query = _FakeQuery(session)

    def table(self, name: str) -> _FakeQuery:
        if name == "routes":
            return self.routes_query
        if name == "training_plans":
            return self.plans_query
        if name == "planned_sessions":
            return self.sessions_query
        raise AssertionError(f"unexpected table {name}")


_ROUTE = {
    "id": "route-1",
    "user_id": "u1",
    "sport": "bike",
    "estimated_duration_s": 7200,
}
_PLAN = {"id": "plan-1", "user_id": "u1", "status": "active"}


def test_apply_route_to_plan_updates_rest_day_without_conflict(monkeypatch: Any) -> None:
    rest_session = {
        "id": "sess-1",
        "sport": "rest",
        "session_type": "rest",
        "plan_id": "plan-1",
    }
    db = _FakeDb(route=_ROUTE, plan=_PLAN, session=rest_session)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    out = mod.apply_route_to_plan(user_id="u1", route_id="route-1", date="2026-07-12")

    assert out == {"status": "ok", "planned_session_id": "sess-1", "replaced": False}
    assert db.sessions_query.updated is not None
    assert db.sessions_query.updated["sport"] == "bike"
    assert db.sessions_query.updated["session_type"] == "long"
    assert db.sessions_query.updated["route_id"] == "route-1"
    assert db.sessions_query.updated["origin"] == "route"
    # bike/long = 45.0 TSS/h (coach/planner._TSS_PER_HOUR) * 2h = 90.0
    assert db.sessions_query.updated["target_tss"] == pytest.approx(90.0)
    assert db.sessions_query.updated["target_duration_s"] == 7200


def test_apply_route_to_plan_conflict_without_force(monkeypatch: Any) -> None:
    busy_session = {
        "id": "sess-1",
        "sport": "run",
        "session_type": "threshold",
        "plan_id": "plan-1",
    }
    db = _FakeDb(route=_ROUTE, plan=_PLAN, session=busy_session)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    with pytest.raises(mod.SessionConflictError) as exc_info:
        mod.apply_route_to_plan(user_id="u1", route_id="route-1", date="2026-07-12")

    assert exc_info.value.existing_sport == "run"
    assert exc_info.value.existing_session_type == "threshold"
    assert db.sessions_query.updated is None


def test_apply_route_to_plan_conflict_overridden_with_force(monkeypatch: Any) -> None:
    busy_session = {
        "id": "sess-1",
        "sport": "run",
        "session_type": "threshold",
        "plan_id": "plan-1",
    }
    db = _FakeDb(route=_ROUTE, plan=_PLAN, session=busy_session)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    out = mod.apply_route_to_plan(
        user_id="u1", route_id="route-1", date="2026-07-12", force=True
    )

    assert out["replaced"] is True
    assert db.sessions_query.updated is not None


def test_apply_route_to_plan_raises_route_not_found(monkeypatch: Any) -> None:
    db = _FakeDb(route=None, plan=_PLAN, session=None)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    with pytest.raises(mod.RouteNotFoundError):
        mod.apply_route_to_plan(user_id="u1", route_id="missing", date="2026-07-12")


def test_apply_route_to_plan_raises_no_active_plan(monkeypatch: Any) -> None:
    db = _FakeDb(route=_ROUTE, plan=None, session=None)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    with pytest.raises(mod.NoActivePlanError):
        mod.apply_route_to_plan(user_id="u1", route_id="route-1", date="2026-07-12")


def test_apply_route_to_plan_raises_date_out_of_range_when_no_session_that_day(
    monkeypatch: Any,
) -> None:
    db = _FakeDb(route=_ROUTE, plan=_PLAN, session=None)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    with pytest.raises(mod.DateOutOfRangeError):
        mod.apply_route_to_plan(user_id="u1", route_id="route-1", date="2099-01-01")


def test_link_route_to_session_updates_route(monkeypatch: Any) -> None:
    matching_session = {"id": "sess-1", "user_id": "u1", "sport": "bike"}
    db = _FakeDb(route=_ROUTE, plan=None, session=matching_session)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    out = mod.link_route_to_session(user_id="u1", route_id="route-1", planned_session_id="sess-1")

    assert out == {"status": "ok"}
    assert db.routes_query.updated == {"planned_session_id": "sess-1"}


def test_link_route_to_session_raises_invalid_session_on_sport_mismatch(monkeypatch: Any) -> None:
    mismatched_session = {"id": "sess-1", "user_id": "u1", "sport": "run"}
    db = _FakeDb(route=_ROUTE, plan=None, session=mismatched_session)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    with pytest.raises(mod.InvalidSessionError):
        mod.link_route_to_session(user_id="u1", route_id="route-1", planned_session_id="sess-1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/coach/test_plan_integration.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'garmin_sync.coach.plan_integration'`

- [ ] **Step 3: Implémenter `plan_integration.py`**

```python
# worker/src/garmin_sync/coach/plan_integration.py
"""Associer un parcours à une séance du plan, ou créer une "sortie libre"."""

from __future__ import annotations

from typing import Any, cast

from garmin_sync.coach.planner import _TSS_PER_HOUR
from garmin_sync.supabase_client import get_admin_client

_FREE_OUTING_SESSION_TYPE = "long"
_FREE_OUTING_NOTES = "Sortie libre planifiée via /routes"


class RouteNotFoundError(Exception):
    """The route does not exist or does not belong to this user."""


class NoActivePlanError(Exception):
    """The user has no active training_plans row."""


class DateOutOfRangeError(Exception):
    """No planned_session exists for that date (outside the active plan's range)."""


class InvalidSessionError(Exception):
    """The planned_session does not belong to this user or its sport doesn't match."""


class SessionConflictError(Exception):
    """A non-rest session already exists that day and `force` was not set."""

    def __init__(self, *, existing_sport: str, existing_session_type: str) -> None:
        super().__init__("session already planned for this date")
        self.existing_sport = existing_sport
        self.existing_session_type = existing_session_type


def _fetch_route(user_id: str, route_id: str) -> dict[str, Any]:
    db = get_admin_client()
    route = cast(
        "dict[str, Any] | None",
        db.table("routes")
        .select("id, user_id, sport, estimated_duration_s")
        .eq("id", route_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
        .data,
    )
    if route is None:
        raise RouteNotFoundError(route_id)
    return route


def apply_route_to_plan(
    *, user_id: str, route_id: str, date: str, force: bool = False
) -> dict[str, Any]:
    """Update the planned_session for `date` with this route's sport/duration/TSS.

    E4 seeds one `planned_sessions` row per day of the active plan (rest days
    included), so this is always an UPDATE, never an INSERT.
    """
    route = _fetch_route(user_id, route_id)
    db = get_admin_client()

    plan = cast(
        "dict[str, Any] | None",
        db.table("training_plans")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
        .data,
    )
    if plan is None:
        raise NoActivePlanError(user_id)

    session = cast(
        "dict[str, Any] | None",
        db.table("planned_sessions")
        .select("id, sport, session_type, plan_id")
        .eq("plan_id", plan["id"])
        .eq("date", date)
        .maybe_single()
        .execute()
        .data,
    )
    if session is None:
        raise DateOutOfRangeError(date)

    is_conflict = session["sport"] != "rest"
    if is_conflict and not force:
        raise SessionConflictError(
            existing_sport=session["sport"], existing_session_type=session["session_type"]
        )

    sport = route["sport"]
    duration_s = route.get("estimated_duration_s") or 0
    tss_per_hour = _TSS_PER_HOUR[(sport, _FREE_OUTING_SESSION_TYPE)]
    target_tss = round(tss_per_hour * duration_s / 3600, 2)

    db.table("planned_sessions").update(
        {
            "sport": sport,
            "session_type": _FREE_OUTING_SESSION_TYPE,
            "target_duration_s": duration_s,
            "target_tss": target_tss,
            "notes": _FREE_OUTING_NOTES,
            "route_id": route_id,
            "origin": "route",
        }
    ).eq("id", session["id"]).execute()

    return {"status": "ok", "planned_session_id": session["id"], "replaced": is_conflict}


def link_route_to_session(
    *, user_id: str, route_id: str, planned_session_id: str
) -> dict[str, Any]:
    """Attach a route to an existing planned_session without altering its content."""
    route = _fetch_route(user_id, route_id)
    db = get_admin_client()

    session = cast(
        "dict[str, Any] | None",
        db.table("planned_sessions")
        .select("id, user_id, sport")
        .eq("id", planned_session_id)
        .maybe_single()
        .execute()
        .data,
    )
    if session is None or session["user_id"] != user_id or session["sport"] != route["sport"]:
        raise InvalidSessionError(planned_session_id)

    db.table("routes").update({"planned_session_id": planned_session_id}).eq(
        "id", route_id
    ).execute()

    return {"status": "ok"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/coach/test_plan_integration.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Lint + types**

Run: `cd worker && uv run ruff check src/garmin_sync/coach/plan_integration.py tests/coach/test_plan_integration.py && uv run mypy src/garmin_sync/coach/plan_integration.py`
Expected: aucune erreur

- [ ] **Step 6: Commit**

```bash
git add worker/src/garmin_sync/coach/plan_integration.py worker/tests/coach/test_plan_integration.py
git commit -m "feat(e8): intégration au plan — apply_route_to_plan, link_route_to_session"
```

---

### Task 9: Endpoints worker (main.py) — les 6 routes `/routes/*` et `/cols/*`

**Files:**
- Modify: `worker/src/garmin_sync/main.py`
- Create: `worker/tests/test_routes_endpoints.py`

**Interfaces:**
- Consumes: tous les modules des Tasks 2-8 (`routing`, `geocoding`, `route_generator`, `route_builder`, `gpx`, `plan_integration`, `overpass.refresh_cols_in_area`)
- Produces : endpoints HTTP consommés par `lib/worker.ts` (Task 10)

- [ ] **Step 1: Écrire les tests (nouveau fichier, réutilise `ASGITestClient` de `test_main.py`)**

```python
# worker/tests/test_routes_endpoints.py
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

from garmin_sync.coach import plan_integration, route_generator
from garmin_sync import routing


class ASGITestClient:
    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def get(self, path: str, **kwargs: object) -> httpx.Response:
        return asyncio.run(self._request("GET", path, **kwargs))

    def post(self, path: str, **kwargs: object) -> httpx.Response:
        return asyncio.run(self._request("POST", path, **kwargs))

    async def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)


@pytest.fixture
def client() -> ASGITestClient:
    from garmin_sync.main import app

    return ASGITestClient(app)


AUTH = {"Authorization": "Bearer shared-token-test"}  # placeholder, overridden per-test below


def _jwt_headers() -> dict[str, str]:
    return {"Authorization": "Bearer fake-jwt"}


def _mock_jwt() -> Any:
    return patch("garmin_sync.main._require_user_jwt", return_value="u1")


def test_routes_suggest_requires_jwt(client: ASGITestClient) -> None:
    r = client.post("/routes/suggest", json={"sport": "run", "target_duration_s": 3600})
    assert r.status_code == 401


def test_routes_suggest_returns_ok_payload(client: ASGITestClient) -> None:
    with _mock_jwt(), patch.object(
        route_generator, "suggest_routes", AsyncMock(return_value={"status": "ok", "routes": []})
    ):
        r = client.post(
            "/routes/suggest",
            json={"sport": "run", "target_duration_s": 3600},
            headers=_jwt_headers(),
        )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_routes_suggest_maps_no_start_coords(client: ASGITestClient) -> None:
    with _mock_jwt(), patch.object(
        route_generator,
        "suggest_routes",
        AsyncMock(side_effect=route_generator.NoStartCoordsError()),
    ):
        r = client.post(
            "/routes/suggest",
            json={"sport": "run", "target_duration_s": 3600},
            headers=_jwt_headers(),
        )
    assert r.status_code == 200
    assert r.json()["status"] == "no_start_coords"


def test_routes_suggest_maps_graphhopper_unavailable(client: ASGITestClient) -> None:
    with _mock_jwt(), patch.object(
        route_generator,
        "suggest_routes",
        AsyncMock(side_effect=routing.GraphhopperUnavailableError()),
    ):
        r = client.post(
            "/routes/suggest",
            json={"sport": "run", "target_duration_s": 3600},
            headers=_jwt_headers(),
        )
    assert r.status_code == 200
    assert r.json()["status"] == "graphhopper_unavailable"


def test_routes_build_maps_no_route_found(client: ASGITestClient) -> None:
    with _mock_jwt(), patch(
        "garmin_sync.coach.route_builder.build_route",
        AsyncMock(side_effect=routing.NoRouteFoundError()),
    ):
        r = client.post(
            "/routes/build",
            json={"sport": "bike", "start": {"lat": 45.0, "lng": 5.0}, "waypoints": []},
            headers=_jwt_headers(),
        )
    assert r.status_code == 200
    assert r.json()["status"] == "no_route_found"


def test_cols_refresh_area_returns_count(client: ASGITestClient) -> None:
    with _mock_jwt(), patch(
        "garmin_sync.coach.overpass.refresh_cols_in_area", return_value=4
    ):
        r = client.post(
            "/cols/refresh-area",
            json={"lat": 45.0, "lng": 6.0, "radius_m": 20000},
            headers=_jwt_headers(),
        )
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "cols_count": 4}


def test_routes_apply_to_plan_maps_session_conflict(client: ASGITestClient) -> None:
    with _mock_jwt(), patch(
        "garmin_sync.coach.plan_integration.apply_route_to_plan",
        side_effect=plan_integration.SessionConflictError(
            existing_sport="run", existing_session_type="threshold"
        ),
    ):
        r = client.post(
            "/routes/route-1/apply-to-plan",
            json={"date": "2026-07-12"},
            headers=_jwt_headers(),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "session_conflict"
    assert body["existing_sport"] == "run"
    assert body["existing_session_type"] == "threshold"


def test_routes_link_session_ok(client: ASGITestClient) -> None:
    with _mock_jwt(), patch(
        "garmin_sync.coach.plan_integration.link_route_to_session",
        return_value={"status": "ok"},
    ):
        r = client.post(
            "/routes/route-1/link-session",
            json={"planned_session_id": "sess-1"},
            headers=_jwt_headers(),
        )
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_routes_gpx_download_returns_content_disposition(client: ASGITestClient) -> None:
    route_row = {
        "id": "route-1",
        "user_id": "u1",
        "sport": "run",
        "generated_at": "2026-07-10T08:00:00+00:00",
        "polyline": {"type": "LineString", "coordinates": [[4.8, 45.7, 100.0]]},
    }
    with (
        _mock_jwt(),
        patch("garmin_sync.main.get_admin_client") as get_db,
    ):
        query = get_db.return_value.table.return_value
        query.select.return_value = query
        query.eq.return_value = query
        query.maybe_single.return_value = query
        query.execute.return_value.data = route_row
        r = client.get("/routes/route-1/gpx", headers=_jwt_headers())

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/gpx+xml")
    assert "attachment" in r.headers["content-disposition"]


def test_routes_gpx_download_404_when_not_found(client: ASGITestClient) -> None:
    with (
        _mock_jwt(),
        patch("garmin_sync.main.get_admin_client") as get_db,
    ):
        query = get_db.return_value.table.return_value
        query.select.return_value = query
        query.eq.return_value = query
        query.maybe_single.return_value = query
        query.execute.return_value.data = None
        r = client.get("/routes/missing/gpx", headers=_jwt_headers())

    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker && uv run pytest tests/test_routes_endpoints.py -v`
Expected: FAIL — routes non trouvées (404 générique FastAPI) car les endpoints n'existent pas encore.

- [ ] **Step 3: Ajouter les endpoints dans `main.py`**

Ajouter juste avant `app = create_app()` en fin de fichier :

```python
class SuggestRoutesRequest(BaseModel):
    planned_session_id: str | None = None
    sport: str | None = None
    target_duration_s: int | None = None
    target_elevation_gain_m: int | None = None
    start_override: dict[str, float] | None = None


@router.post("/routes/suggest")
async def routes_suggest(
    body: SuggestRoutesRequest,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    user_id = _require_user_jwt(authorization)
    from garmin_sync.coach import route_generator
    from garmin_sync import routing

    try:
        return await route_generator.suggest_routes(
            user_id=user_id,
            sport=body.sport,
            target_duration_s=body.target_duration_s,
            target_elevation_gain_m=body.target_elevation_gain_m,
            planned_session_id=body.planned_session_id,
            start_override=body.start_override,
        )
    except route_generator.NoStartCoordsError:
        return {"status": "no_start_coords"}
    except route_generator.NoValidRoutesError:
        return {"status": "no_valid_routes"}
    except routing.GraphhopperUnavailableError:
        return {"status": "graphhopper_unavailable"}
    except Exception as e:
        return report_endpoint_error(e, endpoint="routes_suggest", user_id=user_id)


class BuildRouteRequest(BaseModel):
    sport: str
    start: dict[str, float]
    waypoints: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/routes/build")
async def routes_build(
    body: BuildRouteRequest,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    user_id = _require_user_jwt(authorization)
    from garmin_sync.coach import route_builder
    from garmin_sync import routing

    try:
        return await route_builder.build_route(
            user_id=user_id, sport=body.sport, start=body.start, waypoints=body.waypoints
        )
    except routing.NoRouteFoundError:
        return {"status": "no_route_found"}
    except routing.GraphhopperUnavailableError:
        return {"status": "graphhopper_unavailable"}
    except Exception as e:
        return report_endpoint_error(e, endpoint="routes_build", user_id=user_id)


class RefreshColsAreaRequest(BaseModel):
    lat: float
    lng: float
    radius_m: int = Field(default=25_000, ge=1)


@router.post("/cols/refresh-area")
async def cols_refresh_area(
    body: RefreshColsAreaRequest,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.coach.overpass import refresh_cols_in_area

        count = refresh_cols_in_area(body.lat, body.lng, body.radius_m)
        return {"status": "ok", "cols_count": count}
    except Exception as e:
        return report_endpoint_error(e, endpoint="cols_refresh_area", user_id=user_id)


class ApplyToPlanRequest(BaseModel):
    date: str
    force: bool = False


@router.post("/routes/{route_id}/apply-to-plan")
async def routes_apply_to_plan(
    route_id: str,
    body: ApplyToPlanRequest,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    user_id = _require_user_jwt(authorization)
    from garmin_sync.coach import plan_integration

    try:
        return plan_integration.apply_route_to_plan(
            user_id=user_id, route_id=route_id, date=body.date, force=body.force
        )
    except plan_integration.RouteNotFoundError:
        return {"status": "route_not_found"}
    except plan_integration.NoActivePlanError:
        return {"status": "no_active_plan"}
    except plan_integration.DateOutOfRangeError:
        return {"status": "date_out_of_range"}
    except plan_integration.SessionConflictError as e:
        return {
            "status": "session_conflict",
            "existing_sport": e.existing_sport,
            "existing_session_type": e.existing_session_type,
        }
    except Exception as e:
        return report_endpoint_error(
            e, endpoint="routes_apply_to_plan", user_id=user_id, route_id=route_id
        )


class LinkSessionRequest(BaseModel):
    planned_session_id: str


@router.post("/routes/{route_id}/link-session")
async def routes_link_session(
    route_id: str,
    body: LinkSessionRequest,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    user_id = _require_user_jwt(authorization)
    from garmin_sync.coach import plan_integration

    try:
        return plan_integration.link_route_to_session(
            user_id=user_id, route_id=route_id, planned_session_id=body.planned_session_id
        )
    except plan_integration.RouteNotFoundError:
        return {"status": "route_not_found"}
    except plan_integration.InvalidSessionError:
        return {"status": "invalid_session"}
    except Exception as e:
        return report_endpoint_error(
            e, endpoint="routes_link_session", user_id=user_id, route_id=route_id
        )


@router.get("/routes/{route_id}/gpx")
async def routes_gpx(
    route_id: str,
    authorization: _AuthHeader = None,
) -> Response:
    from datetime import datetime as _dt

    from garmin_sync.coach.gpx import geojson_to_gpx

    user_id = _require_user_jwt(authorization)
    db = get_admin_client()
    route = (
        db.table("routes")
        .select("id, user_id, sport, generated_at, polyline")
        .eq("id", route_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
        .data
    )
    if route is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "route_not_found")

    date_label = _dt.fromisoformat(route["generated_at"]).date().isoformat()
    name = f"{route['sport']} — {date_label}"
    xml = geojson_to_gpx(route["polyline"]["coordinates"], name=name)
    filename = f"{route['sport']}-{date_label}.gpx"
    return Response(
        content=xml,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Ajouter les imports manquants en tête de `main.py`**

Vérifier/ajouter dans les imports FastAPI existants (`from fastapi import APIRouter, FastAPI, Header, HTTPException, status`) :

```python
from fastapi import APIRouter, FastAPI, Header, HTTPException, Response, status
```

Et dans les imports pydantic existants (`from pydantic import BaseModel, Field`) — déjà présents, rien à changer.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd worker && uv run pytest tests/test_routes_endpoints.py -v`
Expected: PASS (10 tests)

- [ ] **Step 6: Run la suite complète worker pour vérifier l'absence de régression**

Run: `cd worker && uv run pytest -v`
Expected: PASS (tous les tests existants + nouveaux)

- [ ] **Step 7: Lint + types**

Run: `cd worker && uv run ruff check src/garmin_sync/main.py tests/test_routes_endpoints.py && uv run mypy src/garmin_sync/main.py`
Expected: aucune erreur

- [ ] **Step 8: Coverage**

Run: `cd worker && uv run pytest --cov=garmin_sync --cov-report=term-missing -q`
Expected: les nouveaux modules (`routing.py`, `coach/geocoding.py`, `coach/route_generator.py`, `coach/route_builder.py`, `coach/gpx.py`, `coach/plan_integration.py`, ajouts `main.py`/`overpass.py`) à ≥95 % — combler les lignes manquantes par des tests ciblés si le rapport en signale.

- [ ] **Step 9: Commit**

```bash
git add worker/src/garmin_sync/main.py worker/tests/test_routes_endpoints.py
git commit -m "feat(e8): endpoints worker — /routes/*, /cols/refresh-area"
```

---

### Task 10: Types + Server Actions frontend (lib/worker.ts, app/actions/routes.ts)

**Files:**
- Modify: `lib/worker.ts`
- Create: `app/actions/routes.ts`
- Test: `tests/unit/actions/routes.test.ts`

**Interfaces:**
- Consumes: `workerPost` (existant dans `lib/worker.ts`), endpoints du Task 9
- Produces: types `SuggestRoutesResult`, `BuildRouteResult`, `RefreshColsAreaResult`, `ApplyToPlanResult`, `LinkSessionResult`, `RouteDto` (exportés de `lib/worker.ts`) ; fonctions `suggestRoutes`, `buildRoute`, `refreshColsArea`, `applyRouteToPlan`, `linkRouteToSession` (exportées de `app/actions/routes.ts`) — consommées par les composants UI (Tasks 12-16)

- [ ] **Step 1: Ajouter les types et wrappers dans `lib/worker.ts`**

Ajouter à la fin du fichier :

```typescript
export interface RouteDto {
  id: string
  sport: 'run' | 'bike'
  polyline: { type: 'LineString'; coordinates: number[][] }
  distance_m: number
  elevation_gain_m: number
  estimated_duration_s: number | null
  match_score: number | null
  target_duration_s: number | null
  target_elevation_gain_m: number | null
}

export type SuggestRoutesResult =
  | {
      status: 'ok'
      routes: RouteDto[]
      target: { duration_s: number; elevation_gain_m: number | null; sport: string }
      estimated_user_speed_mps: number
    }
  | { status: 'no_start_coords' }
  | { status: 'no_valid_routes' }
  | { status: 'graphhopper_unavailable' }
  | { status: 'unexpected_error'; error_id: string; type: string }

export type BuildRouteResult =
  | { status: 'ok'; route: RouteDto }
  | { status: 'no_route_found' }
  | { status: 'graphhopper_unavailable' }
  | { status: 'unexpected_error'; error_id: string; type: string }

export type RefreshColsAreaResult =
  | { status: 'ok'; cols_count: number }
  | { status: 'overpass_unavailable' }
  | { status: 'unexpected_error'; error_id: string; type: string }

export type ApplyToPlanResult =
  | { status: 'ok'; planned_session_id: string; replaced: boolean }
  | { status: 'route_not_found' }
  | { status: 'no_active_plan' }
  | { status: 'date_out_of_range' }
  | { status: 'session_conflict'; existing_sport: string; existing_session_type: string }
  | { status: 'unexpected_error'; error_id: string; type: string }

export type LinkSessionResult =
  | { status: 'ok' }
  | { status: 'route_not_found' }
  | { status: 'invalid_session' }
  | { status: 'unexpected_error'; error_id: string; type: string }

export async function workerSuggestRoutes(
  jwt: string,
  body: {
    planned_session_id?: string
    sport?: string
    target_duration_s?: number
    target_elevation_gain_m?: number
    start_override?: { lat: number; lng: number }
  }
): Promise<SuggestRoutesResult> {
  return workerPost<SuggestRoutesResult>('/routes/suggest', body, jwt)
}

export async function workerBuildRoute(
  jwt: string,
  body: {
    sport: string
    start: { lat: number; lng: number }
    waypoints: { lat: number; lng: number; col_id?: string }[]
  }
): Promise<BuildRouteResult> {
  return workerPost<BuildRouteResult>('/routes/build', body, jwt)
}

export async function workerRefreshColsArea(
  jwt: string,
  body: { lat: number; lng: number; radius_m?: number }
): Promise<RefreshColsAreaResult> {
  return workerPost<RefreshColsAreaResult>('/cols/refresh-area', body, jwt)
}

export async function workerApplyRouteToPlan(
  jwt: string,
  routeId: string,
  body: { date: string; force?: boolean }
): Promise<ApplyToPlanResult> {
  return workerPost<ApplyToPlanResult>(`/routes/${routeId}/apply-to-plan`, body, jwt)
}

export async function workerLinkRouteToSession(
  jwt: string,
  routeId: string,
  plannedSessionId: string
): Promise<LinkSessionResult> {
  return workerPost<LinkSessionResult>(
    `/routes/${routeId}/link-session`,
    { planned_session_id: plannedSessionId },
    jwt
  )
}
```

- [ ] **Step 2: Écrire le test des Server Actions**

```typescript
// tests/unit/actions/routes.test.ts
import { describe, expect, it, vi, beforeEach } from 'vitest'

const workerMocks = vi.hoisted(() => ({
  workerSuggestRoutes: vi.fn(),
  workerBuildRoute: vi.fn(),
  workerRefreshColsArea: vi.fn(),
  workerApplyRouteToPlan: vi.fn(),
  workerLinkRouteToSession: vi.fn(),
}))

vi.mock('@/lib/worker', () => workerMocks)

vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn(async () => ({
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: { access_token: 'jwt-test' } },
      })),
    },
  })),
}))

describe('app/actions/routes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('suggestRoutes forwards the jwt and body to workerSuggestRoutes', async () => {
    workerMocks.workerSuggestRoutes.mockResolvedValue({ status: 'ok', routes: [] })
    const { suggestRoutes } = await import('@/app/actions/routes')

    const result = await suggestRoutes({ sport: 'run', target_duration_s: 3600 })

    expect(workerMocks.workerSuggestRoutes).toHaveBeenCalledWith('jwt-test', {
      sport: 'run',
      target_duration_s: 3600,
    })
    expect(result).toEqual({ status: 'ok', routes: [] })
  })

  it('applyRouteToPlan forwards routeId, date and force', async () => {
    workerMocks.workerApplyRouteToPlan.mockResolvedValue({
      status: 'ok',
      planned_session_id: 's1',
      replaced: false,
    })
    const { applyRouteToPlan } = await import('@/app/actions/routes')

    await applyRouteToPlan('route-1', '2026-07-12', true)

    expect(workerMocks.workerApplyRouteToPlan).toHaveBeenCalledWith('jwt-test', 'route-1', {
      date: '2026-07-12',
      force: true,
    })
  })
})
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pnpm vitest run tests/unit/actions/routes.test.ts`
Expected: FAIL — `app/actions/routes.ts` n'existe pas encore.

- [ ] **Step 4: Implémenter `app/actions/routes.ts`**

```typescript
'use server'

import { createClient } from '@/lib/supabase/server'
import {
  workerSuggestRoutes,
  workerBuildRoute,
  workerRefreshColsArea,
  workerApplyRouteToPlan,
  workerLinkRouteToSession,
  type SuggestRoutesResult,
  type BuildRouteResult,
  type RefreshColsAreaResult,
  type ApplyToPlanResult,
  type LinkSessionResult,
} from '@/lib/worker'

async function getUserJwt(): Promise<string> {
  const supabase = await createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (!session) {
    throw new Error('Not authenticated')
  }
  return session.access_token
}

export async function suggestRoutes(body: {
  planned_session_id?: string
  sport?: string
  target_duration_s?: number
  target_elevation_gain_m?: number
  start_override?: { lat: number; lng: number }
}): Promise<SuggestRoutesResult> {
  const jwt = await getUserJwt()
  return workerSuggestRoutes(jwt, body)
}

export async function buildRoute(body: {
  sport: string
  start: { lat: number; lng: number }
  waypoints: { lat: number; lng: number; col_id?: string }[]
}): Promise<BuildRouteResult> {
  const jwt = await getUserJwt()
  return workerBuildRoute(jwt, body)
}

export async function refreshColsArea(
  lat: number,
  lng: number,
  radiusM?: number
): Promise<RefreshColsAreaResult> {
  const jwt = await getUserJwt()
  return workerRefreshColsArea(jwt, { lat, lng, radius_m: radiusM })
}

export async function applyRouteToPlan(
  routeId: string,
  date: string,
  force?: boolean
): Promise<ApplyToPlanResult> {
  const jwt = await getUserJwt()
  return workerApplyRouteToPlan(jwt, routeId, { date, force })
}

export async function linkRouteToSession(
  routeId: string,
  plannedSessionId: string
): Promise<LinkSessionResult> {
  const jwt = await getUserJwt()
  return workerLinkRouteToSession(jwt, routeId, plannedSessionId)
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pnpm vitest run tests/unit/actions/routes.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 6: Typecheck + lint**

Run: `pnpm typecheck && pnpm lint`
Expected: aucune erreur

- [ ] **Step 7: Commit**

```bash
git add lib/worker.ts app/actions/routes.ts tests/unit/actions/routes.test.ts
git commit -m "feat(e8): types + Server Actions frontend pour /routes"
```

---

### Task 11: Route Handler téléchargement GPX

**Files:**
- Create: `app/api/routes/[id]/gpx/route.ts`
- Test: `tests/unit/api/routes-gpx.test.ts`

**Interfaces:**
- Consumes: `GET {WORKER_URL}/routes/{id}/gpx` (Task 9), `getServerEnv` (existant, `lib/env.ts`), `createClient` (existant, `lib/supabase/server.ts`)
- Produces: `GET /api/routes/{id}/gpx` — consommé par `ExportActions.tsx` (Task 16)

**Pourquoi un Route Handler et pas une Server Action** : les Server Actions renvoient des données sérialisées et ne permettent pas de contrôler `Content-Disposition`/déclencher un téléchargement navigateur propre. Un Route Handler proxy le flux binaire du worker directement.

- [ ] **Step 1: Écrire le test**

```typescript
// tests/unit/api/routes-gpx.test.ts
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn(async () => ({
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: { access_token: 'jwt-test' } },
      })),
    },
  })),
}))

vi.mock('@/lib/env', () => ({
  getServerEnv: () => ({ WORKER_URL: 'http://worker.local' }),
}))

const originalFetch = global.fetch

describe('GET /api/routes/[id]/gpx', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    global.fetch = originalFetch
  })

  it('proxies the worker GPX response with its headers', async () => {
    global.fetch = vi.fn(async () =>
      new Response('<gpx></gpx>', {
        status: 200,
        headers: {
          'Content-Type': 'application/gpx+xml',
          'Content-Disposition': 'attachment; filename="run-2026-07-10.gpx"',
        },
      })
    ) as unknown as typeof fetch

    const { GET } = await import('@/app/api/routes/[id]/gpx/route')
    const response = await GET(new Request('http://test/api/routes/route-1/gpx'), {
      params: Promise.resolve({ id: 'route-1' }),
    })

    expect(response.status).toBe(200)
    expect(response.headers.get('content-disposition')).toContain('run-2026-07-10.gpx')
    expect(global.fetch).toHaveBeenCalledWith(
      'http://worker.local/routes/route-1/gpx',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-test' }),
      })
    )
  })

  it('returns 404 when the worker returns 404', async () => {
    global.fetch = vi.fn(async () => new Response(null, { status: 404 })) as unknown as typeof fetch

    const { GET } = await import('@/app/api/routes/[id]/gpx/route')
    const response = await GET(new Request('http://test/api/routes/missing/gpx'), {
      params: Promise.resolve({ id: 'missing' }),
    })

    expect(response.status).toBe(404)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm vitest run tests/unit/api/routes-gpx.test.ts`
Expected: FAIL — le fichier `app/api/routes/[id]/gpx/route.ts` n'existe pas.

- [ ] **Step 3: Implémenter le Route Handler**

```typescript
// app/api/routes/[id]/gpx/route.ts
import { getServerEnv } from '@/lib/env'
import { createClient } from '@/lib/supabase/server'

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params
  const supabase = await createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (!session) {
    return new Response('Not authenticated', { status: 401 })
  }

  const { WORKER_URL } = getServerEnv()
  const workerResponse = await fetch(`${WORKER_URL}/routes/${id}/gpx`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    cache: 'no-store',
  })

  if (!workerResponse.ok) {
    return new Response(null, { status: workerResponse.status })
  }

  return new Response(workerResponse.body, {
    status: 200,
    headers: {
      'Content-Type': workerResponse.headers.get('content-type') ?? 'application/gpx+xml',
      'Content-Disposition':
        workerResponse.headers.get('content-disposition') ?? 'attachment; filename="route.gpx"',
    },
  })
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm vitest run tests/unit/api/routes-gpx.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Typecheck + lint**

Run: `pnpm typecheck && pnpm lint`
Expected: aucune erreur

- [ ] **Step 6: Commit**

```bash
git add app/api/routes/[id]/gpx/route.ts tests/unit/api/routes-gpx.test.ts
git commit -m "feat(e8): route handler téléchargement GPX"
```

---

### Task 12: Composants carte — RouteMap + RouteCard

**Files:**
- Create: `components/routes/RouteMap.tsx`
- Create: `components/routes/RouteCard.tsx`
- Test: `tests/unit/components/route-map.test.tsx`
- Test: `tests/unit/components/route-card.test.tsx`

**Interfaces:**
- Consumes: `buildRouteGeoJson`, `routeBounds` (`lib/maps/route-geojson.ts`, existant), `maplibre-gl` (existant)
- Produces: `RouteMap({ coordinates, onMapClick?, height? })` (affiche un tracé + centre la vue ; appelle `onMapClick(lat, lng)` si fourni — utilisé en mode manuel), `RouteCard({ route, selected, onSelect })` — consommés par `AutoSuggestPanel` (Task 13) et `ManualBuildPanel` (Task 15)

- [ ] **Step 1: Écrire le test de RouteMap (mock maplibre-gl comme le fait déjà `activity-route-map.test.tsx`)**

Regarder d'abord `tests/unit/components/activity-route-map.test.tsx` pour reprendre exactement le pattern de mock `maplibre-gl` déjà en place dans ce projet (mock du constructeur `Map`, de `.on`, `.remove`, etc.) :

```bash
cat tests/unit/components/activity-route-map.test.tsx
```

Adapter ce même mock pour :

```typescript
// tests/unit/components/route-map.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RouteMap } from '@/components/routes/RouteMap'

vi.mock('maplibre-gl', () => {
  const mapInstance = {
    on: vi.fn((event: string, cb: () => void) => {
      if (event === 'load') cb()
    }),
    remove: vi.fn(),
    addSource: vi.fn(),
    addLayer: vi.fn(),
    getSource: vi.fn(() => null),
    fitBounds: vi.fn(),
  }
  return { default: vi.fn(() => mapInstance) }
})

describe('RouteMap', () => {
  it('renders a container div', () => {
    render(
      <RouteMap
        coordinates={[
          [4.835, 45.764, 165],
          [4.84, 45.77, 180],
        ]}
      />
    )
    expect(screen.getByTestId('route-map-container')).toBeInTheDocument()
  })

  it('calls onMapClick with lat/lng when the map is clicked', async () => {
    let clickHandler: ((e: { lngLat: { lat: number; lng: number } }) => void) | undefined
    const maplibregl = await import('maplibre-gl')
    ;(maplibregl.default as unknown as ReturnType<typeof vi.fn>).mockImplementation(() => ({
      on: vi.fn((event: string, cb: (...args: never[]) => void) => {
        if (event === 'load') cb()
        if (event === 'click') clickHandler = cb as typeof clickHandler
      }),
      remove: vi.fn(),
      addSource: vi.fn(),
      addLayer: vi.fn(),
      getSource: vi.fn(() => null),
      fitBounds: vi.fn(),
    }))
    const onMapClick = vi.fn()

    render(<RouteMap coordinates={[]} onMapClick={onMapClick} />)
    clickHandler?.({ lngLat: { lat: 45.9, lng: 5.1 } })

    expect(onMapClick).toHaveBeenCalledWith(45.9, 5.1)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm vitest run tests/unit/components/route-map.test.tsx`
Expected: FAIL — `components/routes/RouteMap.tsx` n'existe pas.

- [ ] **Step 3: Implémenter `RouteMap.tsx`**

```typescript
// components/routes/RouteMap.tsx
'use client'

import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { buildRouteGeoJson, routeBounds, type RoutePoint } from '@/lib/maps/route-geojson'

const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const SOURCE_ID = 'route-map-line'

interface RouteMapProps {
  readonly coordinates: number[][] // [lng, lat, ele?]
  readonly onMapClick?: (lat: number, lng: number) => void
  readonly height?: number
}

export function RouteMap({ coordinates, onMapClick, height = 320 }: RouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DARK_STYLE,
      center: coordinates[0] ? [coordinates[0][0]!, coordinates[0][1]!] : [4.835, 45.764],
      zoom: 12,
    })
    mapRef.current = map

    map.on('load', () => {
      const points: RoutePoint[] = coordinates.map(([lng, lat]) => ({
        latitude: lat ?? null,
        longitude: lng ?? null,
      }))
      const feature = buildRouteGeoJson(points)
      if (feature) {
        map.addSource(SOURCE_ID, { type: 'geojson', data: feature })
        map.addLayer({
          id: SOURCE_ID,
          type: 'line',
          source: SOURCE_ID,
          paint: { 'line-color': '#22d3ee', 'line-width': 3 },
        })
        const bounds = routeBounds(feature.geometry.coordinates)
        if (bounds) map.fitBounds(bounds, { padding: 32 })
      }
    })

    if (onMapClick) {
      map.on('click', (e) => onMapClick(e.lngLat.lat, e.lngLat.lng))
    }

    return () => map.remove()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rebuild only when coordinates identity changes
  }, [coordinates])

  return <div ref={containerRef} data-testid="route-map-container" style={{ height }} />
}
```

- [ ] **Step 4: Run RouteMap tests to verify they pass**

Run: `pnpm vitest run tests/unit/components/route-map.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Écrire le test de RouteCard**

```typescript
// tests/unit/components/route-card.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RouteCard } from '@/components/routes/RouteCard'
import type { RouteDto } from '@/lib/worker'

vi.mock('@/components/routes/RouteMap', () => ({
  RouteMap: () => <div data-testid="mock-route-map" />,
}))

const route: RouteDto = {
  id: 'r1',
  sport: 'run',
  polyline: { type: 'LineString', coordinates: [[4.835, 45.764, 165]] },
  distance_m: 10800,
  elevation_gain_m: 195,
  estimated_duration_s: 3480,
  match_score: 5,
  target_duration_s: 3600,
  target_elevation_gain_m: 200,
}

describe('RouteCard', () => {
  it('displays distance, elevation and duration', () => {
    render(<RouteCard route={route} selected={false} onSelect={vi.fn()} />)
    expect(screen.getByText(/10.8 ?km/)).toBeInTheDocument()
    expect(screen.getByText(/195 ?m/)).toBeInTheDocument()
  })

  it('calls onSelect with the route id when clicked', () => {
    const onSelect = vi.fn()
    render(<RouteCard route={route} selected={false} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /sélectionner/i }))
    expect(onSelect).toHaveBeenCalledWith('r1')
  })
})
```

- [ ] **Step 6: Run to verify it fails**

Run: `pnpm vitest run tests/unit/components/route-card.test.tsx`
Expected: FAIL — `components/routes/RouteCard.tsx` n'existe pas.

- [ ] **Step 7: Implémenter `RouteCard.tsx`**

```typescript
// components/routes/RouteCard.tsx
'use client'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { RouteMap } from './RouteMap'
import type { RouteDto } from '@/lib/worker'

interface RouteCardProps {
  readonly route: RouteDto
  readonly selected: boolean
  readonly onSelect: (routeId: string) => void
}

function formatKm(meters: number): string {
  return `${(meters / 1000).toFixed(1)} km`
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.round((seconds % 3600) / 60)
  return hours > 0 ? `${hours}h${String(minutes).padStart(2, '0')}` : `${minutes} min`
}

export function RouteCard({ route, selected, onSelect }: RouteCardProps) {
  return (
    <article className={cn('space-y-2 rounded-lg border p-3', selected && 'border-primary')}>
      <RouteMap coordinates={route.polyline.coordinates} height={180} />
      <div className="text-muted-foreground flex flex-wrap gap-3 text-sm">
        <span>{formatKm(route.distance_m)}</span>
        <span>{route.elevation_gain_m} m D+</span>
        <span>{formatDuration(route.estimated_duration_s)}</span>
      </div>
      <Button
        variant={selected ? 'default' : 'outline'}
        size="sm"
        onClick={() => onSelect(route.id)}
      >
        Sélectionner
      </Button>
    </article>
  )
}
```

- [ ] **Step 8: Run RouteCard tests to verify they pass**

Run: `pnpm vitest run tests/unit/components/route-card.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 9: Typecheck + lint**

Run: `pnpm typecheck && pnpm lint`
Expected: aucune erreur

- [ ] **Step 10: Commit**

```bash
git add components/routes/RouteMap.tsx components/routes/RouteCard.tsx tests/unit/components/route-map.test.tsx tests/unit/components/route-card.test.tsx
git commit -m "feat(e8): composants RouteMap (maplibre-gl) et RouteCard"
```

---

### Task 13: AutoSuggestPanel (onglet "Suggestion auto")

**Files:**
- Create: `components/routes/AutoSuggestPanel.tsx`
- Test: `tests/unit/components/auto-suggest-panel.test.tsx`

**Interfaces:**
- Consumes: `suggestRoutes` (Task 10), `RouteCard` (Task 12)
- Produces: `AutoSuggestPanel({ initialSport?, initialTargetDurationS?, initialTargetElevationGainM?, plannedSessionId? })`, gère son propre state (`routes`, `selectedRouteId`, `status`) — consommé par `RouteTabs`/page `/routes` (Task 17)

- [ ] **Step 1: Écrire le test**

```typescript
// tests/unit/components/auto-suggest-panel.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AutoSuggestPanel } from '@/components/routes/AutoSuggestPanel'

vi.mock('@/components/routes/RouteCard', () => ({
  RouteCard: ({ route, onSelect }: { route: { id: string }; onSelect: (id: string) => void }) => (
    <button onClick={() => onSelect(route.id)}>route-{route.id}</button>
  ),
}))

const suggestRoutesMock = vi.hoisted(() => vi.fn())
vi.mock('@/app/actions/routes', () => ({ suggestRoutes: suggestRoutesMock }))

describe('AutoSuggestPanel', () => {
  it('shows a no_start_coords banner', async () => {
    suggestRoutesMock.mockResolvedValue({ status: 'no_start_coords' })
    render(<AutoSuggestPanel initialSport="run" initialTargetDurationS={3600} />)
    fireEvent.click(screen.getByRole('button', { name: /suggérer/i }))
    await waitFor(() =>
      expect(screen.getByText(/synchronise au moins une activité/i)).toBeInTheDocument()
    )
  })

  it('renders 3 RouteCard on success', async () => {
    suggestRoutesMock.mockResolvedValue({
      status: 'ok',
      routes: [{ id: 'r1' }, { id: 'r2' }, { id: 'r3' }],
      target: { duration_s: 3600, elevation_gain_m: null, sport: 'run' },
      estimated_user_speed_mps: 3.3,
    })
    render(<AutoSuggestPanel initialSport="run" initialTargetDurationS={3600} />)
    fireEvent.click(screen.getByRole('button', { name: /suggérer/i }))
    await waitFor(() => expect(screen.getAllByText(/route-r/)).toHaveLength(3))
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm vitest run tests/unit/components/auto-suggest-panel.test.tsx`
Expected: FAIL — le composant n'existe pas.

- [ ] **Step 3: Implémenter `AutoSuggestPanel.tsx`**

```typescript
// components/routes/AutoSuggestPanel.tsx
'use client'

import { useState, useTransition } from 'react'
import { Button } from '@/components/ui/button'
import { RouteCard } from './RouteCard'
import { suggestRoutes } from '@/app/actions/routes'
import type { RouteDto, SuggestRoutesResult } from '@/lib/worker'

interface AutoSuggestPanelProps {
  readonly initialSport?: 'run' | 'bike'
  readonly initialTargetDurationS?: number
  readonly initialTargetElevationGainM?: number | null
  readonly plannedSessionId?: string
}

const ERROR_MESSAGES: Record<string, string> = {
  no_start_coords:
    'Synchronise au moins une activité GPS pour calculer ton point de départ, ou saisis une adresse.',
  no_valid_routes: 'Aucun itinéraire trouvé. Essaie un autre point de départ.',
  graphhopper_unavailable: 'Service indisponible. Réessaie dans une minute.',
  unexpected_error: 'Une erreur est survenue.',
}

export function AutoSuggestPanel({
  initialSport,
  initialTargetDurationS,
  initialTargetElevationGainM,
  plannedSessionId,
}: AutoSuggestPanelProps) {
  const [pending, startTransition] = useTransition()
  const [result, setResult] = useState<SuggestRoutesResult | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  function handleSuggest(): void {
    startTransition(async () => {
      const r = await suggestRoutes({
        planned_session_id: plannedSessionId,
        sport: initialSport,
        target_duration_s: initialTargetDurationS,
        target_elevation_gain_m: initialTargetElevationGainM ?? undefined,
      })
      setResult(r)
    })
  }

  const routes: RouteDto[] = result?.status === 'ok' ? result.routes : []
  const errorMessage =
    result && result.status !== 'ok' ? (ERROR_MESSAGES[result.status] ?? null) : null

  return (
    <div className="space-y-4">
      <Button onClick={handleSuggest} disabled={pending}>
        {pending ? 'Recherche…' : 'Suggérer 3 parcours'}
      </Button>
      {errorMessage && <p className="text-destructive text-sm">{errorMessage}</p>}
      {routes.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-3">
          {routes.map((route) => (
            <RouteCard
              key={route.id}
              route={route}
              selected={selectedId === route.id}
              onSelect={setSelectedId}
            />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm vitest run tests/unit/components/auto-suggest-panel.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Typecheck + lint**

Run: `pnpm typecheck && pnpm lint`
Expected: aucune erreur

- [ ] **Step 6: Commit**

```bash
git add components/routes/AutoSuggestPanel.tsx tests/unit/components/auto-suggest-panel.test.tsx
git commit -m "feat(e8): AutoSuggestPanel — onglet suggestion auto"
```

---

### Task 14: Briques du mode manuel — ColsPickerList, WaypointsList, StartOverrideInput

**Files:**
- Create: `components/routes/ColsPickerList.tsx`
- Create: `components/routes/WaypointsList.tsx`
- Create: `components/routes/StartOverrideInput.tsx`
- Test: `tests/unit/components/cols-picker-list.test.tsx`
- Test: `tests/unit/components/waypoints-list.test.tsx`
- Test: `tests/unit/components/start-override-input.test.tsx`

**Interfaces:**
- Produces:
  - `ColsPickerList({ cols, onPick })` où `cols: {id: string; name: string; latitude: number; longitude: number; elevation_m: number | null}[]`
  - `WaypointsList({ waypoints, onReorder, onRemove })` où `waypoints: {lat: number; lng: number; col_id?: string; label: string}[]`
  - `StartOverrideInput({ onSelect })` — debounce 400ms, appelle `geocodeAddress` (Server Action, créée dans ce même task car triviale)
- Consumed by: `ManualBuildPanel` (Task 15)

- [ ] **Step 1: Ajouter `geocodeAddress` à `app/actions/routes.ts`**

Ajouter à la fin du fichier (nécessite d'exposer `search_address` du worker — réutilise `workerPost` existant avec un nouvel endpoint léger côté worker n'est PAS nécessaire : `geocoding.search_address` n'est pour l'instant appelée que côté worker par les futurs endpoints `/routes/suggest` avec `start_override` déjà résolu côté client. Pour l'input d'adresse, on expose un petit endpoint dédié) :

D'abord, ajouter l'endpoint worker manquant (repéré tardivement — nécessaire pour que `StartOverrideInput` fonctionne) :

```python
# Ajout dans worker/src/garmin_sync/main.py, avant app = create_app()

class GeocodeRequest(BaseModel):
    query: str


@router.post("/geocoding/search")
async def geocoding_search(
    body: GeocodeRequest,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.coach.geocoding import search_address

        results = search_address(body.query)
        return {
            "status": "ok",
            "results": [{"lat": r.lat, "lng": r.lng, "label": r.label} for r in results],
        }
    except Exception as e:
        return report_endpoint_error(e, endpoint="geocoding_search", user_id=user_id)
```

Ajouter le test correspondant dans `worker/tests/test_routes_endpoints.py` :

```python
def test_geocoding_search_returns_results(client: ASGITestClient) -> None:
    from garmin_sync.coach.geocoding import GeocodeResult

    with (
        _mock_jwt(),
        patch(
            "garmin_sync.coach.geocoding.search_address",
            return_value=[GeocodeResult(lat=45.75, lng=4.83, label="Lyon")],
        ),
    ):
        r = client.post(
            "/geocoding/search", json={"query": "Lyon"}, headers=_jwt_headers()
        )
    assert r.status_code == 200
    assert r.json()["results"][0]["label"] == "Lyon"
```

Run: `cd worker && uv run pytest tests/test_routes_endpoints.py -v -k geocoding`
Expected: PASS après implémentation.

- [ ] **Step 2: Ajouter les types + wrapper dans `lib/worker.ts`**

```typescript
export type GeocodeSearchResult =
  | { status: 'ok'; results: { lat: number; lng: number; label: string }[] }
  | { status: 'unexpected_error'; error_id: string; type: string }

export async function workerGeocodeSearch(jwt: string, query: string): Promise<GeocodeSearchResult> {
  return workerPost<GeocodeSearchResult>('/geocoding/search', { query }, jwt)
}
```

Et dans `app/actions/routes.ts` :

```typescript
import { workerGeocodeSearch, type GeocodeSearchResult } from '@/lib/worker'

export async function geocodeAddress(query: string): Promise<GeocodeSearchResult> {
  const jwt = await getUserJwt()
  return workerGeocodeSearch(jwt, query)
}
```

- [ ] **Step 3: Écrire les tests des 3 composants**

```typescript
// tests/unit/components/cols-picker-list.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ColsPickerList } from '@/components/routes/ColsPickerList'

describe('ColsPickerList', () => {
  it('calls onPick with the clicked col', () => {
    const onPick = vi.fn()
    render(
      <ColsPickerList
        cols={[{ id: 'c1', name: 'Col du Galibier', latitude: 45.06, longitude: 6.41, elevation_m: 2642 }]}
        onPick={onPick}
      />
    )
    fireEvent.click(screen.getByText('Col du Galibier'))
    expect(onPick).toHaveBeenCalledWith({
      id: 'c1',
      name: 'Col du Galibier',
      latitude: 45.06,
      longitude: 6.41,
      elevation_m: 2642,
    })
  })

  it('shows an empty state when there are no cols', () => {
    render(<ColsPickerList cols={[]} onPick={vi.fn()} />)
    expect(screen.getByText(/aucun col connu/i)).toBeInTheDocument()
  })
})
```

```typescript
// tests/unit/components/waypoints-list.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { WaypointsList } from '@/components/routes/WaypointsList'

describe('WaypointsList', () => {
  it('renders each waypoint label and calls onRemove', () => {
    const onRemove = vi.fn()
    render(
      <WaypointsList
        waypoints={[{ lat: 45.06, lng: 6.41, label: 'Col du Galibier' }]}
        onReorder={vi.fn()}
        onRemove={onRemove}
      />
    )
    expect(screen.getByText('Col du Galibier')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /supprimer/i }))
    expect(onRemove).toHaveBeenCalledWith(0)
  })
})
```

```typescript
// tests/unit/components/start-override-input.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { StartOverrideInput } from '@/components/routes/StartOverrideInput'

const geocodeAddressMock = vi.hoisted(() => vi.fn())
vi.mock('@/app/actions/routes', () => ({ geocodeAddress: geocodeAddressMock }))

describe('StartOverrideInput', () => {
  it('debounces and shows suggestions after typing', async () => {
    geocodeAddressMock.mockResolvedValue({
      status: 'ok',
      results: [{ lat: 45.75, lng: 4.83, label: 'Place Bellecour, Lyon' }],
    })
    render(<StartOverrideInput onSelect={vi.fn()} />)
    fireEvent.change(screen.getByPlaceholderText(/adresse/i), {
      target: { value: 'Place Bellecour' },
    })
    await waitFor(() => expect(screen.getByText(/Place Bellecour, Lyon/)).toBeInTheDocument(), {
      timeout: 1000,
    })
  })

  it('calls onSelect with lat/lng when a suggestion is picked', async () => {
    geocodeAddressMock.mockResolvedValue({
      status: 'ok',
      results: [{ lat: 45.75, lng: 4.83, label: 'Place Bellecour, Lyon' }],
    })
    const onSelect = vi.fn()
    render(<StartOverrideInput onSelect={onSelect} />)
    fireEvent.change(screen.getByPlaceholderText(/adresse/i), {
      target: { value: 'Place Bellecour' },
    })
    const suggestion = await screen.findByText(/Place Bellecour, Lyon/, {}, { timeout: 1000 })
    fireEvent.click(suggestion)
    expect(onSelect).toHaveBeenCalledWith(45.75, 4.83)
  })
})
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pnpm vitest run tests/unit/components/cols-picker-list.test.tsx tests/unit/components/waypoints-list.test.tsx tests/unit/components/start-override-input.test.tsx`
Expected: FAIL — aucun des 3 composants n'existe.

- [ ] **Step 5: Implémenter `ColsPickerList.tsx`**

```typescript
// components/routes/ColsPickerList.tsx
'use client'

import { Button } from '@/components/ui/button'

export interface ColOption {
  id: string
  name: string
  latitude: number
  longitude: number
  elevation_m: number | null
}

interface ColsPickerListProps {
  readonly cols: ColOption[]
  readonly onPick: (col: ColOption) => void
}

export function ColsPickerList({ cols, onPick }: ColsPickerListProps) {
  if (cols.length === 0) {
    return <p className="text-muted-foreground text-sm">Aucun col connu dans cette zone.</p>
  }
  return (
    <ul className="max-h-64 space-y-1 overflow-y-auto">
      {cols.map((col) => (
        <li key={col.id}>
          <Button variant="ghost" size="sm" className="w-full justify-between" onClick={() => onPick(col)}>
            <span>{col.name}</span>
            {col.elevation_m !== null && (
              <span className="text-muted-foreground text-xs">{col.elevation_m} m</span>
            )}
          </Button>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 6: Implémenter `WaypointsList.tsx`**

```typescript
// components/routes/WaypointsList.tsx
'use client'

import { Button } from '@/components/ui/button'
import { X } from 'lucide-react'

export interface Waypoint {
  lat: number
  lng: number
  col_id?: string
  label: string
}

interface WaypointsListProps {
  readonly waypoints: Waypoint[]
  readonly onReorder: (fromIndex: number, toIndex: number) => void
  readonly onRemove: (index: number) => void
}

export function WaypointsList({ waypoints, onRemove }: WaypointsListProps) {
  if (waypoints.length === 0) {
    return <p className="text-muted-foreground text-sm">Aucun point ajouté pour l'instant.</p>
  }
  return (
    <ol className="space-y-1">
      {waypoints.map((wp, index) => (
        <li key={`${wp.lat}-${wp.lng}-${index}`} className="flex items-center justify-between gap-2 text-sm">
          <span>
            {index + 1}. {wp.label}
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Supprimer"
            onClick={() => onRemove(index)}
          >
            <X size={14} />
          </Button>
        </li>
      ))}
    </ol>
  )
}
```

Note : `onReorder` est retenu dans l'interface pour un futur drag-to-reorder (mentionné dans la spec) mais n'est pas câblé dans cette itération — YAGNI sur l'implémentation du drag tant qu'aucune lib de drag n'est choisie ; le paramètre reste dans la signature pour ne pas casser l'interface plus tard. Supprimer le paramètre non utilisé de la déstructuration évite une erreur ESLint `no-unused-vars` (déjà fait ci-dessus).

- [ ] **Step 7: Implémenter `StartOverrideInput.tsx`**

```typescript
// components/routes/StartOverrideInput.tsx
'use client'

import { useEffect, useRef, useState } from 'react'
import { Input } from '@/components/ui/input'
import { geocodeAddress } from '@/app/actions/routes'

interface StartOverrideInputProps {
  readonly onSelect: (lat: number, lng: number) => void
}

const DEBOUNCE_MS = 400

export function StartOverrideInput({ onSelect }: StartOverrideInputProps) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<{ lat: number; lng: number; label: string }[]>([])
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (query.trim().length < 3) {
      setSuggestions([])
      return
    }
    timerRef.current = setTimeout(() => {
      void geocodeAddress(query).then((result) => {
        setSuggestions(result.status === 'ok' ? result.results : [])
      })
    }, DEBOUNCE_MS)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [query])

  return (
    <div className="space-y-1">
      <Input
        placeholder="Adresse de départ (optionnel)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {suggestions.length > 0 && (
        <ul className="rounded-md border text-sm">
          {suggestions.map((s) => (
            <li key={s.label}>
              <button
                type="button"
                className="hover:bg-muted w-full px-2 py-1 text-left"
                onClick={() => {
                  onSelect(s.lat, s.lng)
                  setQuery(s.label)
                  setSuggestions([])
                }}
              >
                {s.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pnpm vitest run tests/unit/components/cols-picker-list.test.tsx tests/unit/components/waypoints-list.test.tsx tests/unit/components/start-override-input.test.tsx`
Expected: PASS (5 tests)

- [ ] **Step 9: Run worker tests (endpoint geocoding ajouté au Step 1)**

Run: `cd worker && uv run pytest tests/test_routes_endpoints.py -v`
Expected: PASS (inclut désormais `test_geocoding_search_returns_results`)

- [ ] **Step 10: Typecheck + lint (frontend) + lint/mypy (worker)**

Run: `pnpm typecheck && pnpm lint && cd worker && uv run ruff check src/garmin_sync/main.py && uv run mypy src/garmin_sync/main.py`
Expected: aucune erreur

- [ ] **Step 11: Commit**

```bash
git add worker/src/garmin_sync/main.py worker/tests/test_routes_endpoints.py lib/worker.ts app/actions/routes.ts components/routes/ColsPickerList.tsx components/routes/WaypointsList.tsx components/routes/StartOverrideInput.tsx tests/unit/components/cols-picker-list.test.tsx tests/unit/components/waypoints-list.test.tsx tests/unit/components/start-override-input.test.tsx
git commit -m "feat(e8): briques du mode manuel — cols, waypoints, override adresse"
```

---

### Task 15: ManualBuildPanel (onglet "Tracer moi-même")

**Files:**
- Create: `components/routes/ManualBuildPanel.tsx`
- Test: `tests/unit/components/manual-build-panel.test.tsx`

**Interfaces:**
- Consumes: `RouteMap` (Task 12), `ColsPickerList`, `WaypointsList`, `StartOverrideInput` (Task 14), `buildRoute`, `refreshColsArea` (Task 10)
- Produces: `ManualBuildPanel({ initialSport?, cols })` où `cols` est chargé par le composant parent (page, Task 17) via lecture directe de la table `cols` (RLS `select` publique aux users authentifiés — pas besoin de Server Action dédiée, lecture directe via `createClient()` côté page serveur) — consommé par `RouteTabs`/page `/routes` (Task 17)

- [ ] **Step 1: Écrire le test**

```typescript
// tests/unit/components/manual-build-panel.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ManualBuildPanel } from '@/components/routes/ManualBuildPanel'

vi.mock('@/components/routes/RouteMap', () => ({
  RouteMap: ({ onMapClick }: { onMapClick?: (lat: number, lng: number) => void }) => (
    <button data-testid="map-click" onClick={() => onMapClick?.(45.9, 5.1)}>
      map
    </button>
  ),
}))

const buildRouteMock = vi.hoisted(() => vi.fn())
const refreshColsAreaMock = vi.hoisted(() => vi.fn())
vi.mock('@/app/actions/routes', () => ({
  buildRoute: buildRouteMock,
  refreshColsArea: refreshColsAreaMock,
}))

const cols = [
  { id: 'c1', name: 'Col du Galibier', latitude: 45.06, longitude: 6.41, elevation_m: 2642 },
]

describe('ManualBuildPanel', () => {
  it('adds a col as a waypoint when picked from the list', () => {
    render(<ManualBuildPanel initialSport="bike" cols={cols} />)
    fireEvent.click(screen.getByText('Col du Galibier'))
    expect(screen.getByText(/1\. Col du Galibier/)).toBeInTheDocument()
  })

  it('adds a free point when the map is clicked', () => {
    render(<ManualBuildPanel initialSport="bike" cols={cols} />)
    fireEvent.click(screen.getByTestId('map-click'))
    expect(screen.getByText(/1\. Point libre/)).toBeInTheDocument()
  })

  it('calls buildRoute with ordered waypoints when "Calculer l\'itinéraire" is clicked', async () => {
    buildRouteMock.mockResolvedValue({
      status: 'ok',
      route: {
        id: 'r1',
        sport: 'bike',
        polyline: { type: 'LineString', coordinates: [] },
        distance_m: 42000,
        elevation_gain_m: 850,
        estimated_duration_s: 7200,
        match_score: null,
        target_duration_s: null,
        target_elevation_gain_m: null,
      },
    })
    render(<ManualBuildPanel initialSport="bike" cols={cols} />)
    fireEvent.click(screen.getByText('Col du Galibier'))
    fireEvent.click(screen.getByRole('button', { name: /calculer l'itinéraire/i }))

    await waitFor(() =>
      expect(buildRouteMock).toHaveBeenCalledWith({
        sport: 'bike',
        start: expect.any(Object),
        waypoints: [{ lat: 45.06, lng: 6.41, col_id: 'c1' }],
      })
    )
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm vitest run tests/unit/components/manual-build-panel.test.tsx`
Expected: FAIL — le composant n'existe pas.

- [ ] **Step 3: Implémenter `ManualBuildPanel.tsx`**

```typescript
// components/routes/ManualBuildPanel.tsx
'use client'

import { useState, useTransition } from 'react'
import { Button } from '@/components/ui/button'
import { RouteMap } from './RouteMap'
import { ColsPickerList, type ColOption } from './ColsPickerList'
import { WaypointsList, type Waypoint } from './WaypointsList'
import { StartOverrideInput } from './StartOverrideInput'
import { RouteCard } from './RouteCard'
import { buildRoute } from '@/app/actions/routes'
import type { RouteDto, BuildRouteResult } from '@/lib/worker'

interface ManualBuildPanelProps {
  readonly initialSport?: 'run' | 'bike'
  readonly cols: ColOption[]
  readonly defaultStart?: { lat: number; lng: number }
}

const DEFAULT_START = { lat: 45.764, lng: 4.835 } // fallback affiché tant que le profil n'est pas résolu

const ERROR_MESSAGES: Record<string, string> = {
  no_route_found: "Aucun itinéraire trouvé. Essaie un autre point de départ ou d'autres waypoints.",
  graphhopper_unavailable: 'Service indisponible. Réessaie dans une minute.',
  unexpected_error: 'Une erreur est survenue.',
}

export function ManualBuildPanel({ initialSport = 'bike', cols, defaultStart }: ManualBuildPanelProps) {
  const [sport] = useState(initialSport)
  const [start, setStart] = useState(defaultStart ?? DEFAULT_START)
  const [waypoints, setWaypoints] = useState<Waypoint[]>([])
  const [pending, startTransition] = useTransition()
  const [result, setResult] = useState<BuildRouteResult | null>(null)

  function addColWaypoint(col: ColOption): void {
    setWaypoints((prev) => [...prev, { lat: col.latitude, lng: col.longitude, col_id: col.id, label: col.name }])
  }

  function addFreeWaypoint(lat: number, lng: number): void {
    setWaypoints((prev) => [...prev, { lat, lng, label: 'Point libre' }])
  }

  function removeWaypoint(index: number): void {
    setWaypoints((prev) => prev.filter((_, i) => i !== index))
  }

  function reorderWaypoint(fromIndex: number, toIndex: number): void {
    setWaypoints((prev) => {
      const next = [...prev]
      const [moved] = next.splice(fromIndex, 1)
      if (moved) next.splice(toIndex, 0, moved)
      return next
    })
  }

  function handleBuild(): void {
    startTransition(async () => {
      const r = await buildRoute({
        sport,
        start,
        waypoints: waypoints.map((wp) => ({ lat: wp.lat, lng: wp.lng, col_id: wp.col_id })),
      })
      setResult(r)
    })
  }

  const builtRoute: RouteDto | null = result?.status === 'ok' ? result.route : null
  const errorMessage = result && result.status !== 'ok' ? (ERROR_MESSAGES[result.status] ?? null) : null

  return (
    <div className="grid gap-4 md:grid-cols-[2fr_1fr]">
      <RouteMap coordinates={builtRoute?.polyline.coordinates ?? []} onMapClick={addFreeWaypoint} height={360} />
      <div className="space-y-4">
        <StartOverrideInput onSelect={(lat, lng) => setStart({ lat, lng })} />
        <div>
          <h3 className="mb-1 text-sm font-medium">Cols connus</h3>
          <ColsPickerList cols={cols} onPick={addColWaypoint} />
        </div>
        <div>
          <h3 className="mb-1 text-sm font-medium">Waypoints</h3>
          <WaypointsList waypoints={waypoints} onReorder={reorderWaypoint} onRemove={removeWaypoint} />
        </div>
        <Button onClick={handleBuild} disabled={pending || waypoints.length === 0}>
          {pending ? 'Calcul…' : "Calculer l'itinéraire"}
        </Button>
        {errorMessage && <p className="text-destructive text-sm">{errorMessage}</p>}
        {builtRoute && <RouteCard route={builtRoute} selected onSelect={() => {}} />}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm vitest run tests/unit/components/manual-build-panel.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Typecheck + lint**

Run: `pnpm typecheck && pnpm lint`
Expected: aucune erreur (vérifier que `RouteCard` avec `onSelect={() => {}}` ne déclenche pas de warning ESLint sur les fonctions vides — sinon extraire `function noop() {}` en dehors du composant)

- [ ] **Step 6: Commit**

```bash
git add components/routes/ManualBuildPanel.tsx tests/unit/components/manual-build-panel.test.tsx
git commit -m "feat(e8): ManualBuildPanel — onglet tracer moi-même"
```

---

### Task 16: LinkToPlanActions, ExportActions, RouteTabs

**Files:**
- Create: `components/routes/LinkToPlanActions.tsx`
- Create: `components/routes/ExportActions.tsx`
- Create: `components/routes/RouteTabs.tsx`
- Test: `tests/unit/components/link-to-plan-actions.test.tsx`
- Test: `tests/unit/components/export-actions.test.tsx`
- Test: `tests/unit/components/route-tabs.test.tsx`

**Interfaces:**
- Produces: `LinkToPlanActions({ routeId, hasActivePlan, upcomingSessions })`, `ExportActions({ routeId })`, `RouteTabs({ autoPanel, manualPanel, defaultTab })` — consommés par la page `/routes` (Task 17)

- [ ] **Step 1: Écrire les tests**

```typescript
// tests/unit/components/link-to-plan-actions.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { LinkToPlanActions } from '@/components/routes/LinkToPlanActions'

const applyRouteToPlanMock = vi.hoisted(() => vi.fn())
const linkRouteToSessionMock = vi.hoisted(() => vi.fn())
vi.mock('@/app/actions/routes', () => ({
  applyRouteToPlan: applyRouteToPlanMock,
  linkRouteToSession: linkRouteToSessionMock,
}))

describe('LinkToPlanActions', () => {
  it('disables "Ajouter au plan" when there is no active plan', () => {
    render(<LinkToPlanActions routeId="r1" hasActivePlan={false} upcomingSessions={[]} />)
    expect(screen.getByRole('button', { name: /ajouter au plan/i })).toBeDisabled()
  })

  it('shows a confirmation modal on session_conflict then retries with force', async () => {
    applyRouteToPlanMock
      .mockResolvedValueOnce({
        status: 'session_conflict',
        existing_sport: 'run',
        existing_session_type: 'threshold',
      })
      .mockResolvedValueOnce({ status: 'ok', planned_session_id: 's1', replaced: true })

    render(<LinkToPlanActions routeId="r1" hasActivePlan upcomingSessions={[]} />)
    fireEvent.change(screen.getByLabelText(/date/i), { target: { value: '2026-07-12' } })
    fireEvent.click(screen.getByRole('button', { name: /ajouter au plan/i }))

    await waitFor(() => expect(screen.getByText(/remplacer la séance prévue/i)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /confirmer/i }))

    await waitFor(() =>
      expect(applyRouteToPlanMock).toHaveBeenLastCalledWith('r1', '2026-07-12', true)
    )
  })
})
```

```typescript
// tests/unit/components/export-actions.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExportActions } from '@/components/routes/ExportActions'

describe('ExportActions', () => {
  it('renders a download link pointing at the GPX route handler', () => {
    render(<ExportActions routeId="r1" />)
    const link = screen.getByRole('link', { name: /télécharger.*gpx/i })
    expect(link).toHaveAttribute('href', '/api/routes/r1/gpx')
  })
})
```

```typescript
// tests/unit/components/route-tabs.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RouteTabs } from '@/components/routes/RouteTabs'

describe('RouteTabs', () => {
  it('switches panel content on tab click', () => {
    render(
      <RouteTabs
        defaultTab="auto"
        autoPanel={<div>panneau auto</div>}
        manualPanel={<div>panneau manuel</div>}
      />
    )
    expect(screen.getByText('panneau auto')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /tracer moi-même/i }))
    expect(screen.getByText('panneau manuel')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm vitest run tests/unit/components/link-to-plan-actions.test.tsx tests/unit/components/export-actions.test.tsx tests/unit/components/route-tabs.test.tsx`
Expected: FAIL — aucun des 3 composants n'existe.

- [ ] **Step 3: Vérifier la présence du composant `Tabs` shadcn**

Run: `ls components/ui/tabs.tsx`
Expected: si absent, l'installer via `npx shadcn@latest add tabs` (composant shadcn standard, cohérent avec le reste de `components/ui/`).

- [ ] **Step 4: Implémenter `RouteTabs.tsx`**

```typescript
// components/routes/RouteTabs.tsx
'use client'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { ReactNode } from 'react'

interface RouteTabsProps {
  readonly autoPanel: ReactNode
  readonly manualPanel: ReactNode
  readonly defaultTab?: 'auto' | 'manual'
}

export function RouteTabs({ autoPanel, manualPanel, defaultTab = 'auto' }: RouteTabsProps) {
  return (
    <Tabs defaultValue={defaultTab}>
      <TabsList>
        <TabsTrigger value="auto">Suggestion auto</TabsTrigger>
        <TabsTrigger value="manual">Tracer moi-même</TabsTrigger>
      </TabsList>
      <TabsContent value="auto">{autoPanel}</TabsContent>
      <TabsContent value="manual">{manualPanel}</TabsContent>
    </Tabs>
  )
}
```

- [ ] **Step 5: Implémenter `ExportActions.tsx`**

```typescript
// components/routes/ExportActions.tsx
import { Button } from '@/components/ui/button'

interface ExportActionsProps {
  readonly routeId: string
}

export function ExportActions({ routeId }: ExportActionsProps) {
  return (
    <Button asChild variant="outline" size="sm">
      <a href={`/api/routes/${routeId}/gpx`} download>
        Télécharger le GPX
      </a>
    </Button>
  )
}
```

- [ ] **Step 6: Implémenter `LinkToPlanActions.tsx`**

```typescript
// components/routes/LinkToPlanActions.tsx
'use client'

import { useState, useTransition } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { applyRouteToPlan, linkRouteToSession } from '@/app/actions/routes'
import type { ApplyToPlanResult } from '@/lib/worker'

interface UpcomingSession {
  id: string
  date: string
  sport: string
  session_type: string
}

interface LinkToPlanActionsProps {
  readonly routeId: string
  readonly hasActivePlan: boolean
  readonly upcomingSessions: UpcomingSession[]
}

export function LinkToPlanActions({ routeId, hasActivePlan, upcomingSessions }: LinkToPlanActionsProps) {
  const [date, setDate] = useState('')
  const [pending, startTransition] = useTransition()
  const [conflict, setConflict] = useState<ApplyToPlanResult | null>(null)
  const [success, setSuccess] = useState(false)

  function submit(force: boolean): void {
    startTransition(async () => {
      const r = await applyRouteToPlan(routeId, date, force)
      if (r.status === 'session_conflict') {
        setConflict(r)
        return
      }
      setConflict(null)
      setSuccess(r.status === 'ok')
    })
  }

  function handleLinkExisting(sessionId: string): void {
    startTransition(async () => {
      await linkRouteToSession(routeId, sessionId)
    })
  }

  return (
    <div className="space-y-3">
      {upcomingSessions.length > 0 && (
        <div>
          <p className="text-sm font-medium">Associer à une séance existante</p>
          <ul className="mt-1 space-y-1">
            {upcomingSessions.map((s) => (
              <li key={s.id}>
                <Button variant="outline" size="sm" onClick={() => handleLinkExisting(s.id)}>
                  {s.date} — {s.sport} {s.session_type}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <Label htmlFor="free-outing-date">Date</Label>
        <Input id="free-outing-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <Button
          className="mt-2"
          disabled={!hasActivePlan || !date || pending}
          onClick={() => submit(false)}
        >
          Ajouter au plan
        </Button>
        {!hasActivePlan && (
          <p className="text-muted-foreground mt-1 text-xs">Génère d'abord ton plan d'entraînement.</p>
        )}
        {success && <p className="text-sm text-emerald-600">Séance mise à jour.</p>}
      </div>
      {conflict && conflict.status === 'session_conflict' && (
        <div className="bg-muted space-y-2 rounded-md border p-3 text-sm">
          <p>
            Le {date} a déjà une séance prévue ({conflict.existing_sport}{' '}
            {conflict.existing_session_type}). Remplacer la séance prévue ?
          </p>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => submit(true)}>
              Confirmer
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConflict(null)}>
              Annuler
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pnpm vitest run tests/unit/components/link-to-plan-actions.test.tsx tests/unit/components/export-actions.test.tsx tests/unit/components/route-tabs.test.tsx`
Expected: PASS (4 tests). Si `components/ui/label.tsx` n'existe pas déjà, l'installer via `npx shadcn@latest add label` avant ce step.

- [ ] **Step 8: Typecheck + lint**

Run: `pnpm typecheck && pnpm lint`
Expected: aucune erreur

- [ ] **Step 9: Commit**

```bash
git add components/routes/LinkToPlanActions.tsx components/routes/ExportActions.tsx components/routes/RouteTabs.tsx components/ui/tabs.tsx components/ui/label.tsx tests/unit/components/link-to-plan-actions.test.tsx tests/unit/components/export-actions.test.tsx tests/unit/components/route-tabs.test.tsx
git commit -m "feat(e8): LinkToPlanActions, ExportActions, RouteTabs"
```

---

### Task 17: Page `/routes` + intégration `/today`

**Files:**
- Create: `app/(app)/routes/page.tsx`
- Modify: `app/(app)/_components/session-card.tsx`
- Test: `tests/unit/components/session-card.test.tsx` (étendu si déjà existant, sinon vérifier son absence avant de le créer)

**Interfaces:**
- Consumes: tous les composants des Tasks 12-16, `createClient` (existant, lecture directe `cols`/`training_plans`/`planned_sessions` server-side)

- [ ] **Step 1: Vérifier l'existence d'un test pour `session-card.tsx`**

Run: `find tests -iname "*session-card*"`
Si trouvé, l'ouvrir pour connaître le pattern de test déjà en place avant d'écrire le nouveau test (Step 2) — sinon créer le fichier neuf.

- [ ] **Step 2: Écrire le test d'ajout du lien "Suggérer un parcours"**

```typescript
// tests/unit/components/session-card.test.tsx (ajouter si le fichier existe déjà, sinon créer)
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SessionCard } from '@/app/(app)/_components/session-card'
import type { PlannedSession } from '@/lib/dashboard/types'

const baseSession: PlannedSession = {
  id: 's1',
  date: '2026-07-12',
  sport: 'bike',
  session_type: 'endurance',
  target_duration_s: 3600,
  target_tss: 45,
  target_elevation_gain_m: null,
  phase: 'build',
  week_offset: 3,
  notes: null,
  workout: { steps: [] },
}

describe('SessionCard — lien Suggérer un parcours', () => {
  it('shows a link to /routes for a bike session when showWorkout is true', () => {
    render(<SessionCard session={baseSession} showWorkout />)
    const link = screen.getByRole('link', { name: /suggérer un parcours/i })
    expect(link).toHaveAttribute('href', '/routes?session=s1')
  })

  it('does not show the link for a swim session', () => {
    render(<SessionCard session={{ ...baseSession, sport: 'swim' }} showWorkout />)
    expect(screen.queryByRole('link', { name: /suggérer un parcours/i })).not.toBeInTheDocument()
  })

  it('does not show the link when showWorkout is false', () => {
    render(<SessionCard session={baseSession} showWorkout={false} />)
    expect(screen.queryByRole('link', { name: /suggérer un parcours/i })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run to verify it fails**

Run: `pnpm vitest run tests/unit/components/session-card.test.tsx`
Expected: FAIL — le lien n'existe pas encore dans `SessionCard`.

- [ ] **Step 4: Modifier `session-card.tsx`**

Ajouter l'import en tête de fichier :

```typescript
import Link from 'next/link'
```

Modifier le bloc `{showWorkout && workout && (...)}` (repéré en Task de recherche : contient déjà `<RegenerateSessionButton sessionId={session.id} />`) pour y ajouter le lien, conditionné au sport :

```typescript
      {showWorkout && workout && (
        <div className="space-y-2">
          <details className="text-sm">
            <summary className="cursor-pointer font-medium">Voir la séance détaillée</summary>
            <pre className="mt-2 rounded border p-3 text-xs whitespace-pre-wrap">
              {workoutToMarkdown(workout, session.sport as CoachSport, session.session_type)}
            </pre>
          </details>
          <div className="flex gap-2">
            <RegenerateSessionButton sessionId={session.id} />
            {(session.sport === 'run' || session.sport === 'bike') && (
              <Button variant="outline" size="sm" asChild>
                <Link href={`/routes?session=${session.id}`}>Suggérer un parcours</Link>
              </Button>
            )}
          </div>
        </div>
      )}
```

Ajouter l'import du `Button` shadcn en tête de fichier si absent :

```typescript
import { Button } from '@/components/ui/button'
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pnpm vitest run tests/unit/components/session-card.test.tsx`
Expected: PASS (3 tests). Vérifier aussi qu'aucun test existant de `session-card` ne casse : `pnpm vitest run tests/unit/components/session-card.test.tsx --reporter=verbose` (relance complète du fichier).

- [ ] **Step 6: Implémenter la page `/routes`**

```typescript
// app/(app)/routes/page.tsx
import { createClient } from '@/lib/supabase/server'
import { RouteTabs } from '@/components/routes/RouteTabs'
import { AutoSuggestPanel } from '@/components/routes/AutoSuggestPanel'
import { ManualBuildPanel } from '@/components/routes/ManualBuildPanel'

export const revalidate = 0

interface RoutesPageProps {
  searchParams: Promise<{ session?: string }>
}

export default async function RoutesPage({ searchParams }: RoutesPageProps) {
  const { session: sessionId } = await searchParams
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  let sessionContext: {
    sport: 'run' | 'bike'
    target_duration_s: number | null
    target_elevation_gain_m: number | null
  } | null = null

  if (sessionId && user) {
    const { data } = await supabase
      .from('planned_sessions')
      .select('sport, target_duration_s, target_elevation_gain_m')
      .eq('id', sessionId)
      .eq('user_id', user.id)
      .maybe_single()
    if (data && (data.sport === 'run' || data.sport === 'bike')) {
      sessionContext = {
        sport: data.sport,
        target_duration_s: data.target_duration_s,
        target_elevation_gain_m: data.target_elevation_gain_m,
      }
    }
  }

  const { data: colsRows } = await supabase
    .from('cols')
    .select('id, name, latitude, longitude, elevation_m')
    .order('name')

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Parcours</h1>
      <RouteTabs
        defaultTab="auto"
        autoPanel={
          <AutoSuggestPanel
            plannedSessionId={sessionId}
            initialSport={sessionContext?.sport}
            initialTargetDurationS={sessionContext?.target_duration_s ?? undefined}
            initialTargetElevationGainM={sessionContext?.target_elevation_gain_m}
          />
        }
        manualPanel={
          <ManualBuildPanel initialSport={sessionContext?.sport ?? 'bike'} cols={colsRows ?? []} />
        }
      />
    </div>
  )
}
```

Note : `LinkToPlanActions`/`ExportActions` sont branchés une fois qu'un parcours est sélectionné/construit — hors scope de cette page serveur statique (ils vivent dans les states client de `AutoSuggestPanel`/`ManualBuildPanel`). Ce point n'a pas été détaillé dans les Tasks 13/15 par souci de taille : ajouter avant la fin de ce Task un rendu conditionnel `{selectedRoute && <><ExportActions routeId={selectedRoute.id} /><LinkToPlanActions .../></>}` dans `AutoSuggestPanel.tsx` (après la grille de `RouteCard`, quand `selectedId` est non-null) et dans `ManualBuildPanel.tsx` (après le `RouteCard` du résultat construit) — avec les props `hasActivePlan`/`upcomingSessions` remontées depuis cette page via un fetch Supabase supplémentaire (`training_plans` où `status='active'`, `planned_sessions` à venir filtrées par sport) passées en props aux deux panels.

- [ ] **Step 7: Vérifier la protection de la page par le layout existant**

Run: `grep -n "redirect" "app/(app)/layout.tsx"`
Expected: confirme que `app/(app)/layout.tsx` redirige déjà vers `/login` si pas de user — `/routes` est automatiquement protégée, aucun guard additionnel nécessaire.

- [ ] **Step 8: Typecheck + build**

Run: `pnpm typecheck && rm -rf .next && pnpm build`
Expected: build réussi, route `/routes` listée dans la sortie.

- [ ] **Step 9: Commit**

```bash
git add "app/(app)/routes/page.tsx" "app/(app)/_components/session-card.tsx" tests/unit/components/session-card.test.tsx
git commit -m "feat(e8): page /routes + lien Suggérer un parcours sur /today"
```

---

### Task 18: Infra GraphHopper (docker-compose + doc de déploiement)

**Files:**
- Modify: `worker/docker-compose.prod.yml`
- Modify: `worker/deploy/README.md`
- Create: `worker/deploy/refresh-osm.sh`

**Interfaces:**
- Consumes: rien (infra pure)
- Produces: service Docker `graphhopper` joignable par `garmin-sync` sur le réseau interne, consommé en amont par `GRAPHHOPPER_URL=http://graphhopper:8989` / `PHOTON_URL=http://graphhopper:2322` (déjà réglés en Task 1 comme valeurs par défaut de `config.py`, cohérentes avec le nom de service ci-dessous)

Cette task est de l'infra/documentation, pas de code applicatif testé automatiquement — pas de cycle TDD. Étapes de vérification manuelle listées explicitement.

- [ ] **Step 1: Ajouter le service `graphhopper` à `worker/docker-compose.prod.yml`**

```yaml
services:
  garmin-sync:
    image: tellebma/garmin-sync:latest
    container_name: garmin-sync
    restart: unless-stopped
    pull_policy: always
    ports:
      - '127.0.0.1:8080:8080'
    env_file:
      - .env
    networks:
      - npm-net
      - garmin-net
    healthcheck:
      test:
        [
          'CMD',
          'python',
          '-c',
          "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')",
        ]
      interval: 30s
      timeout: 5s
      retries: 3

  graphhopper:
    image: israelhikingmap/graphhopper:latest
    container_name: graphhopper
    restart: unless-stopped
    ports:
      - '127.0.0.1:8989:8989'
      - '127.0.0.1:2322:2322'
    volumes:
      - graphhopper-data:/data
      - ./graphhopper/config.yml:/graphhopper/config.yml:ro
    environment:
      JAVA_OPTS: '-Xmx4g -Xms4g'
    networks:
      - garmin-net

networks:
  npm-net:
    external: true
  garmin-net:
    driver: bridge

volumes:
  graphhopper-data:
```

Note : `garmin-net` (nouveau réseau bridge interne) isole la communication `garmin-sync` ↔ `graphhopper` du réseau `npm-net` exposé par Nginx Proxy Manager — `graphhopper` n'a pas besoin d'être routable depuis l'extérieur au-delà des ports `127.0.0.1` déjà restreints à l'hôte.

- [ ] **Step 2: Créer `worker/graphhopper/config.yml` minimal**

```yaml
graphhopper:
  datareader.file: /data/france-latest.osm.pbf
  graph.location: /data/graph-cache
  import.osm.ignored_highways: ""
  profiles:
    - name: foot
      custom_model_files: [foot.json]
    - name: bike
      custom_model_files: [bike.json]
  graph.elevation.provider: srtm
  graph.elevation.cache_dir: /data/elevation-cache
```

Note : `foot.json`/`bike.json` sont les custom models fournis par défaut par l'image `israelhikingmap/graphhopper` — ne pas les recréer, seulement les référencer.

- [ ] **Step 3: Créer `worker/deploy/refresh-osm.sh`**

```bash
#!/usr/bin/env bash
# Refresh the OSM extract used by GraphHopper (run monthly via UNRAID cron).
set -euo pipefail

DATA_DIR="/opt/garmin-sync/graphhopper-data"
OSM_URL="https://download.geofabrik.de/europe/france-latest.osm.pbf"

echo "Downloading fresh OSM extract..."
curl -fsSL "$OSM_URL" -o "$DATA_DIR/france-latest.osm.pbf.new"
mv "$DATA_DIR/france-latest.osm.pbf.new" "$DATA_DIR/france-latest.osm.pbf"
rm -rf "$DATA_DIR/graph-cache"

echo "Restarting graphhopper to rebuild the graph..."
docker restart graphhopper

echo "Done. First request after restart may be slow (graph rebuild)."
```

- [ ] **Step 4: Rendre le script exécutable**

Run: `chmod +x worker/deploy/refresh-osm.sh`

- [ ] **Step 5: Documenter dans `worker/deploy/README.md`**

Ajouter une nouvelle section après "First-time setup" :

```markdown
## GraphHopper (parcours géolocalisés — E8)

1. Créer le dossier de données et télécharger le premier extrait OSM :
   ```bash
   mkdir -p /opt/garmin-sync/graphhopper-data
   curl -fsSL https://download.geofabrik.de/europe/france-latest.osm.pbf \
     -o /opt/garmin-sync/graphhopper-data/france-latest.osm.pbf
   ```
   ~4 Go, compter 30-60 min pour le premier import (RAM peak ~6 Go).

2. Copier `worker/graphhopper/config.yml` vers
   `/opt/garmin-sync/graphhopper/config.yml`.

3. `docker compose up -d graphhopper` — suivre les logs (`docker logs -f graphhopper`)
   jusqu'à ce que l'import soit terminé.

4. Vérifier :
   ```bash
   curl "http://localhost:8989/route?point=45.764,4.835&profile=foot&algorithm=round_trip&round_trip.distance=5000&round_trip.seed=1&points_encoded=false"
   ```
   Expected : JSON avec un `paths[0].distance` proche de 5000.

5. Vérifier Photon (geocoding embarqué) :
   ```bash
   curl "http://localhost:2322/api?q=Bellecour+Lyon"
   ```

6. Planifier `worker/deploy/refresh-osm.sh` en cron mensuel (UNRAID User Scripts),
   même mécanisme que le cron de sync quotidien.
```

- [ ] **Step 6: Commit**

```bash
git add worker/docker-compose.prod.yml worker/graphhopper/config.yml worker/deploy/refresh-osm.sh worker/deploy/README.md
git commit -m "feat(e8): infra GraphHopper — docker-compose, config, script refresh OSM"
```

---

### Task 19: Tests E2E Playwright — flow auto et flow manuel

**Files:**
- Create: `tests/e2e/routes.spec.ts`

**Interfaces:**
- Consumes: la page `/routes` complète (Tasks 1-17), le worker mocké via MSW (pattern déjà utilisé pour les autres flows E2E de ce projet — vérifier `tests/e2e/` pour le setup MSW existant avant d'écrire ce fichier)

- [ ] **Step 1: Vérifier le pattern MSW déjà en place**

Run: `grep -rl "msw\|setupServer" tests/e2e/ | head -5`

Ouvrir un fichier E2E existant (ex. celui qui teste le flow Garmin connect ou la génération de séance) pour reprendre exactement le même pattern de mock des endpoints worker.

- [ ] **Step 2: Écrire le test E2E**

```typescript
// tests/e2e/routes.spec.ts
import { test, expect } from '@playwright/test'

test.describe('Parcours géolocalisés (/routes)', () => {
  test('flow auto : depuis /today, suggérer puis télécharger le GPX', async ({ page }) => {
    await page.route('**/routes/suggest', async (route) => {
      await route.fulfill({
        json: {
          status: 'ok',
          routes: [
            {
              id: 'route-1',
              sport: 'run',
              polyline: { type: 'LineString', coordinates: [[4.835, 45.764, 165]] },
              distance_m: 10800,
              elevation_gain_m: 195,
              estimated_duration_s: 3480,
              match_score: 5,
              target_duration_s: 3600,
              target_elevation_gain_m: null,
            },
          ],
          target: { duration_s: 3600, elevation_gain_m: null, sport: 'run' },
          estimated_user_speed_mps: 3.1,
        },
      })
    })
    await page.route('**/routes/route-1/gpx', async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          'content-type': 'application/gpx+xml',
          'content-disposition': 'attachment; filename="run-2026-07-10.gpx"',
        },
        body: '<gpx></gpx>',
      })
    })

    await page.goto('/routes?session=fake-session-id')
    await page.getByRole('button', { name: /suggérer 3 parcours/i }).click()
    await expect(page.getByRole('button', { name: /sélectionner/i }).first()).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('link', { name: /télécharger.*gpx/i }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toContain('.gpx')
  })

  test('flow manuel : sélectionner un col puis calculer un itinéraire', async ({ page }) => {
    await page.route('**/routes/build', async (route) => {
      await route.fulfill({
        json: {
          status: 'ok',
          route: {
            id: 'route-2',
            sport: 'bike',
            polyline: { type: 'LineString', coordinates: [[5.10, 45.90, 2600]] },
            distance_m: 42000,
            elevation_gain_m: 850,
            estimated_duration_s: 7200,
            match_score: null,
            target_duration_s: null,
            target_elevation_gain_m: null,
          },
        },
      })
    })

    await page.goto('/routes')
    await page.getByRole('tab', { name: /tracer moi-même/i }).click()
    // Suppose au moins un col affiché par le seed de données de test — sinon skip
    // cette assertion et documenter le besoin d'un col de fixture E2E dédié.
    await page.getByRole('button', { name: /calculer l'itinéraire/i }).click()
  })
})
```

- [ ] **Step 3: Run E2E localement**

Run: `pnpm test:e2e -- routes.spec.ts`
Expected: PASS. Ajuster les sélecteurs/mocks selon le setup MSW réel découvert au Step 1 (ce test est un squelette conforme au contrat des endpoints — son câblage exact au harness E2E existant est à finaliser à l'exécution, notamment la donnée de fixture "au moins 1 col en base" pour le flow manuel).

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/routes.spec.ts
git commit -m "test(e8): E2E Playwright — flow auto et flow manuel /routes"
```

---

## Self-Review

**1. Couverture de la spec** : les 3 sections principales de la spec (mode auto repris d'E8a, mode manuel via cols/waypoints, intégration au plan) sont couvertes respectivement par Tasks 2/6/9/13 (auto), Tasks 2/4/7/9/14/15 (manuel), Task 8/9/16 (plan). L'export GPX (Task 5/9/11/16). L'infra GraphHopper (Task 18). Les écarts documentés dans la spec (pas de push Garmin, maplibre-gl au lieu de leaflet, convention `status` HTTP 200) sont reflétés dans les Global Constraints et respectés dans chaque task.

**2. Placeholders** : aucun "TBD"/"TODO" dans le code livré. Une lacune assumée existe au Task 17 (Step 6) : le câblage exact de `ExportActions`/`LinkToPlanActions` dans `AutoSuggestPanel`/`ManualBuildPanel` (state `selectedRoute`) est décrit en prose plutôt qu'en diff complet, pour tenir la taille du plan — un exécutant devra l'implémenter en suivant le patron déjà démontré dans ces deux composants (state + rendu conditionnel), pas une zone grise fonctionnelle.

**3. Cohérence des types** : `RouteDto` (Task 10) est utilisé identiquement dans `RouteCard` (Task 12), `AutoSuggestPanel` (Task 13), `ManualBuildPanel` (Task 15). `Waypoint`/`ColOption` (Task 14) sont réutilisés tels quels dans `ManualBuildPanel` (Task 15). Les statuts d'erreur (`no_start_coords`, `no_valid_routes`, `graphhopper_unavailable`, `no_route_found`, `overpass_unavailable`, `no_active_plan`, `date_out_of_range`, `session_conflict`, `route_not_found`, `invalid_session`, `unexpected_error`) sont identiques entre les exceptions Python (Tasks 6-8), leur mapping dans `main.py` (Task 9), les types TypeScript (Task 10) et les messages UI (Tasks 13/15).

**4. Ordre des tasks** : chaque task ne dépend que de tasks précédentes (Task 1 → fondations, 2-8 → modules worker indépendants puis composés, 9 → assemble en endpoints, 10-11 → pont frontend, 12-16 → composants (du plus bas niveau au plus haut), 17 → assemblage page, 18 → infra (peut être fait en parallèle dès que Task 1 est posée), 19 → E2E en dernier).

---

## Note d'exécution

Ce plan n'est **pas destiné à une exécution immédiate** (décision owner, 2026-07-09) — il documente la conception détaillée d'E8 pour référence future. Aucune session `subagent-driven-development`/`executing-plans` n'est lancée à la suite de ce document. Quand l'implémentation sera reprise, relire d'abord la spec (`docs/superpowers/specs/2026-07-09-e8-parcours-planification-gpx-design.md`) et ce plan pour vérifier qu'aucune hypothèse (versions de libs, schéma DB, endpoints existants) n'a changé entre-temps.
