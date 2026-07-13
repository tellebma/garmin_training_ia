# Sommets (natural=peak) dans le widget cols — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Étendre le widget « Mes cols » pour inclure les sommets OSM (`natural=peak`) en plus
des cols routiers (`mountain_pass=yes`), sans nouvelle table, avec un filtre d'altitude sur les
sommets pour limiter le bruit.

**Architecture:** La table `cols` existante gagne une colonne `type` (`'col'` | `'peak'`). Le
worker fait une requête Overpass unique combinant les deux tags OSM et classe chaque nœud par
type, avec un filtre d'altitude ≥ 500 m appliqué uniquement aux sommets. Le pipeline de
détection de franchissement (`col_matching.py`) reste inchangé — il sélectionne déjà
`id, latitude, longitude` sans filtrer par type. Côté frontend, `computeColsSummary` regroupe
les résultats en deux listes (`cols`, `peaks`), et `ColsWidget` les affiche en deux sections
indépendamment triées et repliables.

**Tech Stack:** Next.js (Server Components) + Supabase (migration SQL) + Python worker
(Overpass/httpx) + Vitest + pytest.

## Global Constraints

- Aucune nouvelle table : extension de `public.cols` par une colonne `type text not null
  default 'col' check (type in ('col', 'peak'))`. `col_crossings` ne change pas de schéma.
- Rayon Overpass inchangé : 50 km autour du domicile calculé.
- Filtre d'altitude : uniquement sur `type='peak'`, seuil **≥ 500 m** ; un `peak` sans tag
  `ele` OSM est exclu (ne pas upserter la ligne).
- Un nœud matchant à la fois `mountain_pass=yes` et `natural=peak` est classé `'col'`
  (priorité au col).
- Requête Overpass : **un seul appel HTTP** combinant les deux filtres via union `(...)`.
- Détection de franchissement (`recompute_col_crossings`, seuil 150 m) : **inchangée**, aucune
  modification de fichier requise.
- Widget renommé **« Mes cols & sommets »**, description « Cols et sommets dans un rayon de
  50 km autour de chez toi ». Deux sections « Cols » / « Sommets », chacune masquée si vide.
  État vide combiné uniquement si les deux listes sont vides : titre « Aucun col ni sommet
  recensé », description « Aucun col ni sommet dans un rayon de 50 km autour de chez toi. »
- Nom par défaut d'un nœud sans tag `name` : `"Col (OSM #<id>)"` pour `type='col'` (inchangé),
  `"Sommet (OSM #<id>)"` pour `type='peak'` (nouveau).
- Commandes de vérification : `pnpm test <fichier>` (Vitest), `cd worker && uv run pytest
  <fichier> -v` (pytest), `pnpm typecheck`, `pnpm lint`, `pnpm build`, `cd worker && uv run
  ruff check . && uv run mypy src/`.
- Travail dans un git worktree dédié, branche `feat/e-post-mvp-cols-sommets` (déjà configuré
  au niveau exécution, cf. `superpowers:using-git-worktrees`).

---

### Task 1: Migration Supabase — colonne `type` sur `cols`

**Files:**
- Create: `supabase/migrations/20260713090000_cols_type_peak.sql`

**Interfaces:**
- Produces: colonne `public.cols.type` (`text`, `not null`, `default 'col'`, `check (type in
  ('col', 'peak'))`), consommée par le worker (Task 2, upsert) et lue côté frontend (Task 5,
  `select(...)`).

- [ ] **Step 1: Écrire la migration**

```sql
-- Distingue les cols routiers (mountain_pass OSM) des sommets/crêts (natural=peak OSM)
-- dans le référentiel partagé `cols`. Les lignes existantes (toutes issues de
-- mountain_pass=yes) prennent la valeur par défaut 'col'.
alter table public.cols
  add column type text not null default 'col'
    check (type in ('col', 'peak'));

comment on column public.cols.type is
  'Catégorie du point OSM : col (mountain_pass=yes) ou sommet (natural=peak).';
```

- [ ] **Step 2: Vérifier localement la migration**

Run: `cd /home/tellebma/DEV/garmin_training && supabase db reset` (ou, si un environnement
Supabase local tourne déjà, `supabase migration up`).
Expected: la migration s'applique sans erreur, `select type from public.cols limit 1;` (si des
lignes existent) retourne `'col'`.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260713090000_cols_type_peak.sql
git commit -m "feat(db): ajoute la colonne type (col/peak) à la table cols"
```

---

### Task 2: Worker — requête Overpass combinée + classification + filtre altitude

**Files:**
- Modify: `worker/src/garmin_sync/coach/overpass.py`
- Test: `worker/tests/coach/test_overpass.py`

**Interfaces:**
- Consumes: rien de nouveau (module autonome, dépend seulement de `httpx` et
  `garmin_sync.supabase_client.get_admin_client`, déjà importés).
- Produces: `refresh_nearby_cols(user_id: str, home_lat: float, home_lon: float) -> None`
  (signature inchangée) upserte désormais des lignes portant un champ `"type": "col" | "peak"`
  en plus des champs existants (`osm_id`, `name`, `latitude`, `longitude`, `elevation_m`,
  `fetched_at`). Consommé par Task 5 (lecture `cols.type` côté Next.js) — aucun lien direct de
  code, seulement via la table Supabase.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `worker/tests/coach/test_overpass.py` :

```python
def test_build_query_includes_both_overpass_tags() -> None:
    query = mod._build_query(45.0, 6.0)
    assert "mountain_pass=yes" in query
    assert "natural=peak" in query


def test_refresh_classifies_peak_and_filters_by_elevation(monkeypatch: Any) -> None:
    db = _FakeDb(
        {"cols_cache_updated_at": None, "cols_cache_home_lat": None, "cols_cache_home_lon": None}
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.json.return_value = {
        "elements": [
            {
                "type": "node",
                "id": 901,
                "lat": 45.82,
                "lon": 4.52,
                "tags": {"natural": "peak", "name": "Crêt d'Arjoux", "ele": "815"},
            },
            {
                "type": "node",
                "id": 902,
                "lat": 45.83,
                "lon": 4.53,
                "tags": {"natural": "peak", "name": "Petite Butte", "ele": "300"},
            },
            {
                "type": "node",
                "id": 903,
                "lat": 45.84,
                "lon": 4.54,
                "tags": {"natural": "peak", "name": "Sommet Sans Altitude"},
            },
        ]
    }
    monkeypatch.setattr(mod, "httpx", httpx_mock)

    mod.refresh_nearby_cols("user-1", 45.0, 6.0)

    assert db.cols_query.upserted is not None
    assert len(db.cols_query.upserted) == 1
    row = db.cols_query.upserted[0]
    assert row["osm_id"] == 901
    assert row["type"] == "peak"
    assert row["name"] == "Crêt d'Arjoux"
    assert row["elevation_m"] == 815


def test_refresh_prioritizes_col_type_when_both_tags_present(monkeypatch: Any) -> None:
    db = _FakeDb(
        {"cols_cache_updated_at": None, "cols_cache_home_lat": None, "cols_cache_home_lon": None}
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.json.return_value = {
        "elements": [
            {
                "type": "node",
                "id": 777,
                "lat": 45.0,
                "lon": 6.0,
                # ele volontairement < 500 pour vérifier qu'aucun filtre d'altitude
                # ne s'applique quand le nœud est classé 'col'.
                "tags": {"mountain_pass": "yes", "natural": "peak", "ele": "300", "name": "Col-Sommet"},
            },
        ]
    }
    monkeypatch.setattr(mod, "httpx", httpx_mock)

    mod.refresh_nearby_cols("user-1", 45.0, 6.0)

    assert db.cols_query.upserted is not None
    assert len(db.cols_query.upserted) == 1
    assert db.cols_query.upserted[0]["type"] == "col"


def test_refresh_default_name_for_unnamed_peak(monkeypatch: Any) -> None:
    db = _FakeDb(
        {"cols_cache_updated_at": None, "cols_cache_home_lat": None, "cols_cache_home_lon": None}
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.json.return_value = {
        "elements": [
            {
                "type": "node",
                "id": 555,
                "lat": 45.0,
                "lon": 6.0,
                "tags": {"natural": "peak", "ele": "900"},
            },
        ]
    }
    monkeypatch.setattr(mod, "httpx", httpx_mock)

    mod.refresh_nearby_cols("user-1", 45.0, 6.0)

    assert db.cols_query.upserted is not None
    assert "Sommet (OSM #555)" in db.cols_query.upserted[0]["name"]
```

Modifier aussi l'assertion existante dans `test_refresh_fetches_and_upserts_when_cache_is_stale`
pour couvrir la régression du type par défaut (ajouter après la ligne
`assert named["elevation_m"] == 1850`) :

```python
    assert named["type"] == "col"
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `cd worker && uv run pytest tests/coach/test_overpass.py -v`
Expected: FAIL sur les 4 nouveaux tests (`_build_query` ne contient pas `natural=peak`,
`KeyError: 'type'` sur les lignes upsertées).

- [ ] **Step 3: Implémenter — requête combinée**

Dans `worker/src/garmin_sync/coach/overpass.py`, remplacer `_build_query` :

```python
def _build_query(home_lat: float, home_lon: float) -> str:
    return (
        "[out:json][timeout:25];"
        "("
        f"node[mountain_pass=yes](around:{_RADIUS_M},{home_lat},{home_lon});"
        f"node[natural=peak](around:{_RADIUS_M},{home_lat},{home_lon});"
        ");"
        "out;"
    )
```

- [ ] **Step 4: Implémenter — classification + filtre altitude**

Ajouter la constante et la fonction de classification juste après `_CACHE_MOVE_THRESHOLD_M` :

```python
_MIN_PEAK_ELEVATION_M = 500


def _classify(tags: dict[str, Any]) -> str | None:
    if tags.get("mountain_pass") == "yes":
        return "col"
    if tags.get("natural") == "peak":
        return "peak"
    return None
```

Remplacer la construction de `rows` dans `refresh_nearby_cols` (actuellement une
list-comprehension) par :

```python
    rows: list[dict[str, Any]] = []
    for element in elements:
        if element.get("type") != "node" or "lat" not in element or "lon" not in element:
            continue
        tags = element.get("tags", {})
        col_type = _classify(tags)
        if col_type is None:
            continue
        elevation_m = _parse_elevation(tags.get("ele"))
        if col_type == "peak" and (elevation_m is None or elevation_m < _MIN_PEAK_ELEVATION_M):
            continue
        default_name = "Col" if col_type == "col" else "Sommet"
        rows.append(
            {
                "osm_id": element["id"],
                "name": (tags.get("name") or f"{default_name} (OSM #{element['id']})")[
                    :_MAX_NAME_LENGTH
                ],
                "latitude": element["lat"],
                "longitude": element["lon"],
                "elevation_m": elevation_m,
                "type": col_type,
                "fetched_at": _now().isoformat(),
            }
        )
```

- [ ] **Step 5: Lancer les tests pour vérifier qu'ils passent**

Run: `cd worker && uv run pytest tests/coach/test_overpass.py -v`
Expected: PASS sur les 4 nouveaux tests + tous les tests existants (10 tests au total dans ce
fichier).

- [ ] **Step 6: Lint + types**

Run: `cd worker && uv run ruff check src/garmin_sync/coach/overpass.py tests/coach/test_overpass.py && uv run mypy src/garmin_sync/coach/overpass.py`
Expected: aucune erreur.

- [ ] **Step 7: Commit**

```bash
git add worker/src/garmin_sync/coach/overpass.py worker/tests/coach/test_overpass.py
git commit -m "feat(worker): étend Overpass aux sommets natural=peak avec filtre d'altitude"
```

---

### Task 3: Frontend — regroupement cols/sommets dans `lib/dashboard/cols.ts`

**Files:**
- Modify: `lib/dashboard/cols.ts`
- Test: `tests/unit/dashboard/cols.test.ts`

**Interfaces:**
- Consumes: rien de nouveau.
- Produces: `ColDto` gagne `type: ColType` (`ColType = 'col' | 'peak'`). `ColSummary` gagne
  `type: ColType`. `computeColsSummary(...)` retourne désormais `GroupedColsSummary` (`{ cols:
  ColSummary[]; peaks: ColSummary[] }`) au lieu de `ColSummary[]`. Consommé par Task 4
  (`ColsWidget` props `cols`/`peaks`) et Task 5 (`stats/page.tsx`).

- [ ] **Step 1: Écrire le test qui échoue**

Remplacer entièrement `tests/unit/dashboard/cols.test.ts` par :

```typescript
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
    type: 'col',
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
    expect(out.cols.map((c) => c.id)).toEqual(['near'])
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
    const colA = out.cols.find((c) => c.id === 'col-a')
    const colB = out.cols.find((c) => c.id === 'col-b')
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
    expect(out.cols.map((c) => c.id)).toEqual(['far-climbed', 'near-unclimbed', 'far-unclimbed'])
  })

  it('returns empty groups when there are no cols in range', () => {
    const out = computeColsSummary({
      homeLat: HOME_LAT,
      homeLon: HOME_LON,
      cols: [],
      crossings: [],
    })
    expect(out).toEqual({ cols: [], peaks: [] })
  })

  it('groups cols and peaks into separate, independently sorted lists', () => {
    const cols: ColDto[] = [
      mkCol({ id: 'col-a', latitude: 45.01, longitude: 6.01, type: 'col' }),
      mkCol({
        id: 'peak-a',
        latitude: 45.02,
        longitude: 6.02,
        type: 'peak',
        name: 'Crêt du Machin',
      }),
      mkCol({
        id: 'peak-b',
        latitude: 45.03,
        longitude: 6.03,
        type: 'peak',
        name: 'Crêt du Bidule',
      }),
    ]
    const crossings: ColCrossingRowDto[] = [
      { col_id: 'peak-b', crossed_at: '2026-06-01T08:00:00Z' },
    ]
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols, crossings })
    expect(out.cols.map((c) => c.id)).toEqual(['col-a'])
    expect(out.peaks.map((c) => c.id)).toEqual(['peak-b', 'peak-a'])
  })
})
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `pnpm test tests/unit/dashboard/cols.test.ts`
Expected: FAIL (erreurs de type `type` manquant sur `ColDto`, `out.cols` undefined car
`computeColsSummary` retourne encore un tableau plat).

- [ ] **Step 3: Implémenter**

Remplacer entièrement `lib/dashboard/cols.ts` par :

```typescript
const DEFAULT_RADIUS_KM = 50
const EARTH_RADIUS_KM = 6371

export type ColType = 'col' | 'peak'

export interface ColDto {
  id: string
  name: string
  latitude: number
  longitude: number
  elevation_m: number | null
  type: ColType
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
  type: ColType
}

export interface GroupedColsSummary {
  cols: ColSummary[]
  peaks: ColSummary[]
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
}): GroupedColsSummary {
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

  const summaries: (ColSummary & { _distanceKm: number })[] = cols
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
        type: col.type,
        _distanceKm: distanceKm,
      }
    })
    .filter((summary) => summary._distanceKm <= radiusKm)

  const sorted = summaries
    .toSorted((a, b) => b.crossingsCount - a.crossingsCount || a.distanceKm - b.distanceKm)
    .map(({ _distanceKm, ...summary }) => summary)

  return {
    cols: sorted.filter((summary) => summary.type === 'col'),
    peaks: sorted.filter((summary) => summary.type === 'peak'),
  }
}
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `pnpm test tests/unit/dashboard/cols.test.ts`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/dashboard/cols.ts tests/unit/dashboard/cols.test.ts
git commit -m "feat(dashboard): regroupe les résumés cols/sommets par type"
```

---

### Task 4: Frontend — deux sections dans `ColsWidget`

**Files:**
- Modify: `app/(app)/_components/cols-widget.tsx`
- Test: `tests/unit/components/cols-widget.test.tsx`

**Interfaces:**
- Consumes: `ColSummary` (avec `type`) et `GroupedColsSummary` de `lib/dashboard/cols.ts`
  (Task 3).
- Produces: `ColsWidget({ cols, peaks }: Readonly<{ cols: ColSummary[]; peaks: ColSummary[] }>)`
  — la prop `summaries` unique disparaît, remplacée par `cols`/`peaks`. Consommé par Task 5
  (`stats/page.tsx`).

- [ ] **Step 1: Écrire le test qui échoue**

Remplacer entièrement `tests/unit/components/cols-widget.test.tsx` par :

```tsx
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
    type: 'col',
    ...overrides,
  }
}

describe('ColsWidget', () => {
  it('renders one row per col with name, altitude, distance and count', () => {
    render(<ColsWidget cols={[mkSummary({})]} peaks={[]} />)
    expect(screen.getByText('Col du Truc')).not.toBeNull()
    expect(screen.getByText(/1850/)).not.toBeNull()
    expect(screen.getByText(/12/)).not.toBeNull()
    expect(screen.getByText(/4 fois/)).not.toBeNull()
  })

  it('shows singular wording for exactly one crossing', () => {
    render(<ColsWidget cols={[mkSummary({ crossingsCount: 1 })]} peaks={[]} />)
    expect(screen.getByText(/1 fois/)).not.toBeNull()
  })

  it('shows a combined empty state when there are no cols and no peaks', () => {
    render(<ColsWidget cols={[]} peaks={[]} />)
    expect(screen.getByText(/Aucun col ni sommet recensé/)).not.toBeNull()
    expect(
      screen.getByText(/Aucun col ni sommet dans un rayon de 50 km autour de chez toi/)
    ).not.toBeNull()
  })

  it('renders only the peaks section when there are no cols', () => {
    render(
      <ColsWidget cols={[]} peaks={[mkSummary({ id: 'peak-1', name: 'Crêt du Machin', type: 'peak' })]} />
    )
    expect(screen.getByText('Sommets')).not.toBeNull()
    expect(screen.queryByText('Cols')).toBeNull()
    expect(screen.getByText('Crêt du Machin')).not.toBeNull()
  })

  it('renders both sections when cols and peaks are present', () => {
    render(
      <ColsWidget
        cols={[mkSummary({ id: 'col-1', name: 'Col du Truc' })]}
        peaks={[mkSummary({ id: 'peak-1', name: 'Crêt du Machin', type: 'peak' })]}
      />
    )
    expect(screen.getByText('Cols')).not.toBeNull()
    expect(screen.getByText('Sommets')).not.toBeNull()
  })

  it('shows all rows unfolded when there are 10 or fewer', () => {
    const summaries = Array.from({ length: 10 }, (_, i) =>
      mkSummary({ id: `col-${String(i)}`, name: `Col ${String(i)}` })
    )
    render(<ColsWidget cols={summaries} peaks={[]} />)
    expect(screen.getAllByRole('row')).toHaveLength(11) // 10 data rows + header
    expect(screen.queryByText(/Afficher les/)).toBeNull()
  })

  it('truncates past 10 rows behind a details/summary toggle', () => {
    const summaries = Array.from({ length: 13 }, (_, i) =>
      mkSummary({ id: `col-${String(i)}`, name: `Col ${String(i)}` })
    )
    render(<ColsWidget cols={summaries} peaks={[]} />)
    expect(screen.getByText('Col 0')).not.toBeNull()
    expect(screen.getByText('Col 9')).not.toBeNull()
    expect(screen.getByText('Afficher les 3 autres')).not.toBeNull()
    expect(screen.getByText('Col 12')).not.toBeNull()
  })
})
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `pnpm test tests/unit/components/cols-widget.test.tsx`
Expected: FAIL (erreur de type — `ColsWidget` n'accepte pas encore les props `cols`/`peaks`).

- [ ] **Step 3: Implémenter**

Remplacer entièrement `app/(app)/_components/cols-widget.tsx` par :

```tsx
import { Mountain } from 'lucide-react'
import type { ColSummary } from '@/lib/dashboard/cols'
import { ChartCard } from './chart-card'
import { EmptyState } from './empty-state'

const VISIBLE_COUNT = 10

function crossingsLabel(count: number): string {
  return count === 1 ? '1 fois' : `${String(count)} fois`
}

function ColsTable({
  summaries,
  showHeader = true,
}: Readonly<{ summaries: ColSummary[]; showHeader?: boolean }>) {
  return (
    <table className="w-full text-sm">
      {showHeader && (
        <thead>
          <tr className="text-muted-foreground border-b text-left text-xs uppercase">
            <th className="py-2 font-medium">Nom</th>
            <th className="py-2 font-medium">Altitude</th>
            <th className="py-2 font-medium">Distance</th>
            <th className="py-2 text-right font-medium">Grimpé</th>
          </tr>
        </thead>
      )}
      <tbody className="divide-y">
        {summaries.map((summary) => (
          <tr key={summary.id}>
            <td className="py-2 font-medium">{summary.name}</td>
            <td className="text-muted-foreground py-2">
              {summary.elevationM === null ? '—' : `${String(summary.elevationM)} m`}
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
  )
}

function ColsSection({
  title,
  summaries,
}: Readonly<{ title: string; summaries: ColSummary[] }>) {
  if (summaries.length === 0) {
    return null
  }

  const visible = summaries.slice(0, VISIBLE_COUNT)
  const rest = summaries.slice(VISIBLE_COUNT)

  return (
    <div className="space-y-2">
      <h3 className="text-muted-foreground text-xs font-semibold uppercase">{title}</h3>
      <ColsTable summaries={visible} />
      {rest.length > 0 && (
        <details className="mt-2 text-sm">
          <summary className="text-muted-foreground cursor-pointer">
            Afficher les {rest.length} autres
          </summary>
          <div className="mt-2">
            <ColsTable summaries={rest} showHeader={false} />
          </div>
        </details>
      )}
    </div>
  )
}

export function ColsWidget({
  cols,
  peaks,
}: Readonly<{ cols: ColSummary[]; peaks: ColSummary[] }>) {
  if (cols.length === 0 && peaks.length === 0) {
    return (
      <ChartCard
        title="Mes cols & sommets"
        description="Cols et sommets dans un rayon de 50 km autour de chez toi"
      >
        <EmptyState
          icon={Mountain}
          title="Aucun col ni sommet recensé"
          description="Aucun col ni sommet dans un rayon de 50 km autour de chez toi."
        />
      </ChartCard>
    )
  }

  return (
    <ChartCard
      title="Mes cols & sommets"
      description="Cols et sommets dans un rayon de 50 km autour de chez toi"
    >
      <div className="space-y-6">
        <ColsSection title="Cols" summaries={cols} />
        <ColsSection title="Sommets" summaries={peaks} />
      </div>
    </ChartCard>
  )
}
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `pnpm test tests/unit/components/cols-widget.test.tsx`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add app/\(app\)/_components/cols-widget.tsx tests/unit/components/cols-widget.test.tsx
git commit -m "feat(dashboard): affiche cols et sommets en deux sections dans ColsWidget"
```

---

### Task 5: Frontend — câblage `stats/page.tsx` (ColsWidgetLoader)

**Files:**
- Modify: `app/(app)/stats/page.tsx:377-413`

**Interfaces:**
- Consumes: `computeColsSummary` retournant `GroupedColsSummary` (Task 3), `ColsWidget`
  attendant `{ cols, peaks }` (Task 4), `ColDto` avec `type` (Task 3).
- Produces: rien de nouveau exposé (composant terminal de la chaîne).

- [ ] **Step 1: Modifier la requête Supabase et le câblage**

Dans `app/(app)/stats/page.tsx`, remplacer la fonction `ColsWidgetLoader` (lignes 377-413) par :

```tsx
async function ColsWidgetLoader({ userId }: { readonly userId: string }) {
  const supabase = await createClient()
  const { data: profile } = await supabase
    .from('athlete_profiles')
    .select('lat, lon')
    .eq('user_id', userId)
    .maybeSingle()

  if (profile?.lat == null || profile.lon == null) {
    return (
      <ChartCard
        title="Mes cols & sommets"
        description="Cols et sommets dans un rayon de 50 km autour de chez toi"
      >
        <EmptyState
          icon={ActivityIcon}
          title="Domicile pas encore situé"
          description="Pas encore assez de données GPS pour situer chez toi."
        />
      </ChartCard>
    )
  }

  const [colsRes, crossingsRes] = await Promise.all([
    supabase.from('cols').select('id, name, latitude, longitude, elevation_m, type'),
    supabase.from('col_crossings').select('col_id, crossed_at').eq('user_id', userId),
  ])

  const cols: ColDto[] = colsRes.data ?? []
  const crossings: ColCrossingRowDto[] = crossingsRes.data ?? []

  const { cols: colSummaries, peaks: peakSummaries } = computeColsSummary({
    homeLat: Number(profile.lat),
    homeLon: Number(profile.lon),
    cols,
    crossings,
  })

  return <ColsWidget cols={colSummaries} peaks={peakSummaries} />
}
```

Le reste du fichier (imports, `<Suspense fallback={<ColsWidgetSkeleton />}>`) reste inchangé —
`ColDto` importé en ligne 24 porte déjà le nouveau champ `type` depuis Task 3.

- [ ] **Step 2: Vérifier les types**

Run: `pnpm typecheck`
Expected: aucune erreur (le `select` Supabase renvoie des colonnes non typées statiquement ;
`ColDto` impose la forme attendue au moment de l'assignation `const cols: ColDto[] =
colsRes.data ?? []`, cohérent avec le pattern déjà utilisé pour `elevation_m`).

- [ ] **Step 3: Vérifier le build**

Run: `pnpm build`
Expected: build réussi, aucune erreur ESLint/TypeScript bloquante.

- [ ] **Step 4: Commit**

```bash
git add app/\(app\)/stats/page.tsx
git commit -m "feat(stats): câble cols et sommets dans le widget /stats"
```

---

### Task 6: Documentation utilisateur et backlog

**Files:**
- Modify: `docs/nouveautes.md`
- Modify: `docs/superpowers/BACKLOG.md`

**Interfaces:**
- Consumes: rien (tâche documentaire, aucune dépendance de code).
- Produces: rien de consommé par du code.

- [ ] **Step 1: Déterminer la version cible pour l'entrée `nouveautes.md`**

Run: `git fetch --tags && git describe --tags --abbrev=0`
Cette tâche introduit un changement fonctionnel (`feat:`), donc semantic-release bump la
version **mineure** au prochain merge sur `main` — si le dernier tag est `v1.9.0`, la version
cible de l'entrée est `1.10.0`.

- [ ] **Step 2: Ajouter l'entrée dans `docs/nouveautes.md`**

Ajouter en tête de fichier (juste après le titre, au-dessus des entrées existantes) une
nouvelle section, en remplaçant `<version>` par la valeur trouvée à l'étape 1 et `<date>` par
la date du jour :

```markdown
## <version> — <date>

- Le widget « Mes cols » devient « Mes cols & sommets » : en plus des cols routiers, les
  sommets et crêtes à proximité de chez toi (ex. le Crêt d'Arjoux) apparaissent maintenant
  dans une section dédiée, avec le nombre de fois où tu les as gravis.
```

- [ ] **Step 3: Mettre à jour `docs/superpowers/BACKLOG.md`**

Dans la section ajoutée précédemment (`### P2 — Sommets (natural=peak) dans le widget cols`),
ajouter à la fin la mention du plan et, une fois la PR mergée, le numéro de PR — remplacer le
titre par :

```markdown
### P2 — Sommets (natural=peak) dans le widget cols — V1 livrée (PR #<numéro>)
```

et ajouter une ligne sous les puces existantes :

```markdown
- Plan : `docs/superpowers/plans/2026-07-12-cols-sommets-peaks.md`.
```

(Le numéro de PR n'est connu qu'après ouverture de la PR — renseigner cette étape juste avant
le merge, en cohérence avec la convention du projet pour les items « V1 livrée ».)

- [ ] **Step 4: Commit**

```bash
git add docs/nouveautes.md docs/superpowers/BACKLOG.md
git commit -m "docs: référence le plan sommets/cols et prépare l'entrée nouveautés"
```

---

### Task 7: Vérification finale

**Files:** aucun (validation transverse)

- [ ] **Step 1: Suite complète frontend**

Run: `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
Expected: tout passe, 0 erreur.

- [ ] **Step 2: Suite complète worker**

Run: `cd worker && uv run ruff check . && uv run mypy src/ && uv run pytest -v`
Expected: tout passe, les 50 tests worker (46 existants + 4 nouveaux) sont verts.

- [ ] **Step 3: Vérification manuelle (optionnelle si Supabase local disponible)**

Si un environnement Supabase local est démarré (`supabase start`), lancer `pnpm dev`, se
connecter avec un utilisateur ayant des activités GPS, et vérifier sur `/stats` que le widget
« Mes cols & sommets » affiche bien deux sections distinctes (ou une seule si l'autre est
vide), sans régression visuelle sur la table existante.

- [ ] **Step 4: Fin de branche**

Une fois toutes les tâches vertes, utiliser `superpowers:finishing-a-development-branch` pour
ouvrir la PR, puis mettre à jour l'item du Project GitHub (#4) de `Todo` vers `In Review` (lien
PR), et vers `Done` après merge — conformément à la convention décrite dans `CLAUDE.md`.
