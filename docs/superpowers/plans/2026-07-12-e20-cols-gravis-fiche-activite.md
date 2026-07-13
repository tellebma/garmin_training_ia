# E20 — Cols gravis sur la fiche activité Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sur `/history/[id]`, afficher une section "Cols gravis" (nom + altitude) listant les
cols effectivement franchis pendant cette activité précise, en s'appuyant sur la table
`col_crossings` déjà alimentée par le worker (`garmin_activity_id` déjà présent en DB).

**Architecture:** Une fonction pure de mapping (`toActivityColCrossings`) dans
`lib/dashboard/cols.ts`, un skeleton dédié, et un composant serveur async isolé
(`ActivityColsGravis`) monté dans son propre `<Suspense>` au même niveau que
`ActivityDetailBody` — pas ajouté au `Promise.all` bloquant existant de cette dernière (règle
validée avec l'owner sur la feature "Mes cols", voir spec).

**Tech Stack:** Next.js 15 App Router (Server Components), Supabase JS, TypeScript, Vitest +
Testing Library.

## Global Constraints

- Ne pas réutiliser `computeColsSummary` (agrégat géographique global, pas scopé à une
  activité) — nouvelle fonction dédiée dans le même fichier `lib/dashboard/cols.ts`.
- Le widget ne doit **pas** être ajouté au `Promise.all` de `ActivityDetailBody`
  (`app/(app)/history/[id]/page.tsx:149-195`) : il doit démarrer son fetch en parallèle via
  sa propre frontière `<Suspense>`, montée à côté de `ActivityDetailBody`.
- Si aucun col n'a été franchi, le composant ne rend **rien** (`null`) — pas d'état vide
  visible.
- Pas de badge sur la liste `/history` — uniquement la fiche détail.

---

### Task 1: Fonction pure `toActivityColCrossings`

**Files:**
- Modify: `lib/dashboard/cols.ts` (ajout, ne pas toucher à `computeColsSummary`/`haversineKm`)
- Test: `tests/unit/dashboard/cols.test.ts` (fichier existant, ajout de cas)

**Interfaces:**
- Consumes : rien (fonction pure, pas de dépendance externe).
- Produces : `ActivityColCrossingDto { colId: string; name: string; elevationM: number | null; crossedAt: string }`
  et `toActivityColCrossings(rows) => ActivityColCrossingDto[]`, consommés par la Task 3.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `tests/unit/dashboard/cols.test.ts` :

```ts
import { toActivityColCrossings } from '@/lib/dashboard/cols'
import type { ActivityColCrossingDto } from '@/lib/dashboard/cols'

describe('toActivityColCrossings', () => {
  it('returns an empty array for no rows', () => {
    expect(toActivityColCrossings([])).toEqual([])
  })

  it('maps and sorts rows chronologically by crossed_at', () => {
    const rows = [
      {
        col_id: 'col-b',
        crossed_at: '2026-06-01T10:00:00Z',
        cols: { name: 'Col B', elevation_m: 1200 },
      },
      {
        col_id: 'col-a',
        crossed_at: '2026-06-01T08:00:00Z',
        cols: { name: 'Col A', elevation_m: 1800 },
      },
    ]
    const out = toActivityColCrossings(rows)
    expect(out).toEqual<ActivityColCrossingDto[]>([
      { colId: 'col-a', name: 'Col A', elevationM: 1800, crossedAt: '2026-06-01T08:00:00Z' },
      { colId: 'col-b', name: 'Col B', elevationM: 1200, crossedAt: '2026-06-01T10:00:00Z' },
    ])
  })

  it('preserves a null elevation_m as null', () => {
    const rows = [
      {
        col_id: 'col-c',
        crossed_at: '2026-06-01T08:00:00Z',
        cols: { name: 'Col C', elevation_m: null },
      },
    ]
    expect(toActivityColCrossings(rows)[0]?.elevationM).toBeNull()
  })
})
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pnpm vitest run tests/unit/dashboard/cols.test.ts`
Expected: FAIL — `toActivityColCrossings` n'existe pas (erreur d'import/undefined).

- [ ] **Step 3: Implémenter la fonction**

Ajouter à la fin de `lib/dashboard/cols.ts` :

```ts
export interface ActivityColCrossingRowDto {
  col_id: string
  crossed_at: string
  cols: { name: string; elevation_m: number | null }
}

export interface ActivityColCrossingDto {
  colId: string
  name: string
  elevationM: number | null
  crossedAt: string
}

export function toActivityColCrossings(
  rows: ActivityColCrossingRowDto[]
): ActivityColCrossingDto[] {
  return rows
    .map((r) => ({
      colId: r.col_id,
      name: r.cols.name,
      elevationM: r.cols.elevation_m,
      crossedAt: r.crossed_at,
    }))
    .toSorted((a, b) => a.crossedAt.localeCompare(b.crossedAt))
}
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pnpm vitest run tests/unit/dashboard/cols.test.ts`
Expected: PASS (tous les tests du fichier, anciens et nouveaux)

- [ ] **Step 5: Commit**

```bash
git add lib/dashboard/cols.ts tests/unit/dashboard/cols.test.ts
git commit -m "feat(cols): ajoute toActivityColCrossings pour scoper les cols à une activité"
```

---

### Task 2: Skeleton `ColsGravisSkeleton`

**Files:**
- Create: `app/(app)/_components/skeletons/cols-gravis-skeleton.tsx`

**Interfaces:**
- Consumes : `Skeleton` (`@/components/ui/skeleton`), `LoadingRegion`
  (`./loading-region`, export existant `{ label: string; children: React.ReactNode }`).
- Produces : `ColsGravisSkeleton` (composant sans props), consommé par la Task 3.

- [ ] **Step 1: Créer le skeleton**

```tsx
// app/(app)/_components/skeletons/cols-gravis-skeleton.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from './loading-region'

export function ColsGravisSkeleton() {
  return (
    <LoadingRegion label="Chargement des cols gravis">
      <div className="space-y-2">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-10 w-full rounded-md" />
        <Skeleton className="h-10 w-full rounded-md" />
      </div>
    </LoadingRegion>
  )
}
```

Pas de test dédié : composant purement statique, calqué à l'identique sur
`activity-detail-skeleton.tsx` (non testé lui non plus).

- [ ] **Step 2: Vérifier le typecheck**

Run: `pnpm typecheck`
Expected: PASS (aucune erreur, fichier isolé sans consommateur pour l'instant).

- [ ] **Step 3: Commit**

```bash
git add "app/(app)/_components/skeletons/cols-gravis-skeleton.tsx"
git commit -m "feat(history): ajoute le skeleton de la section cols gravis"
```

---

### Task 3: Composant `ActivityColsGravis` et intégration dans la fiche activité

**Files:**
- Create: `app/(app)/_components/activity-cols-gravis.tsx`
- Test: `tests/unit/components/activity-cols-gravis.test.tsx`
- Modify: `app/(app)/history/[id]/page.tsx` (imports + JSX de `ActivityDetailPage`, lignes
  1-30 et 106-134)

**Interfaces:**
- Consumes : `toActivityColCrossings`, `ActivityColCrossingDto`
  (`@/lib/dashboard/cols`, Task 1), `ChartCard` (`./chart-card`, props
  `{ title: string; description?: string; children: React.ReactNode }`), `createClient`
  (`@/lib/supabase/server`), `ColsGravisSkeleton` (`./skeletons/cols-gravis-skeleton`, Task 2).
- Produces : `ActivityColsGravis({ userId: string; garminActivityId: number })`, monté
  directement dans `app/(app)/history/[id]/page.tsx` (pas consommé par d'autres tâches).

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/unit/components/activity-cols-gravis.test.tsx` :

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const order = vi.fn()
const eq = vi.fn()
const select = vi.fn()

function buildQuery(finalValue: { data: unknown; error: null }) {
  const q: Record<string, unknown> = {}
  q.select = select.mockReturnValue(q)
  q.eq = eq.mockReturnValue(q)
  q.order = order.mockResolvedValue(finalValue)
  return q
}

let queryResult: { data: unknown; error: null } = { data: [], error: null }

vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn(async () => ({
    from: vi.fn(() => buildQuery(queryResult)),
  })),
}))

describe('ActivityColsGravis', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryResult = { data: [], error: null }
  })

  it('renders nothing when no col was crossed', async () => {
    const { ActivityColsGravis } = await import('@/app/(app)/_components/activity-cols-gravis')
    const jsx = await ActivityColsGravis({ userId: 'user-1', garminActivityId: 123 })
    expect(jsx).toBeNull()
  })

  it('renders the crossed cols with name and elevation', async () => {
    queryResult = {
      data: [
        {
          col_id: 'col-a',
          crossed_at: '2026-06-01T08:00:00Z',
          cols: { name: 'Col du Galibier', elevation_m: 2642 },
        },
        {
          col_id: 'col-b',
          crossed_at: '2026-06-01T10:00:00Z',
          cols: { name: 'Col du Télégraphe', elevation_m: null },
        },
      ],
      error: null,
    }
    const { ActivityColsGravis } = await import('@/app/(app)/_components/activity-cols-gravis')
    const jsx = await ActivityColsGravis({ userId: 'user-1', garminActivityId: 123 })
    render(jsx)

    expect(screen.getByText('Cols gravis')).toBeTruthy()
    expect(screen.getByText('Col du Galibier')).toBeTruthy()
    expect(screen.getByText('2642 m')).toBeTruthy()
    expect(screen.getByText('Col du Télégraphe')).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy()
  })

  it('scopes the query to the given user and activity', async () => {
    const { ActivityColsGravis } = await import('@/app/(app)/_components/activity-cols-gravis')
    await ActivityColsGravis({ userId: 'user-42', garminActivityId: 999 })

    expect(eq).toHaveBeenCalledWith('user_id', 'user-42')
    expect(eq).toHaveBeenCalledWith('garmin_activity_id', 999)
  })
})
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pnpm vitest run tests/unit/components/activity-cols-gravis.test.tsx`
Expected: FAIL — le module `@/app/(app)/_components/activity-cols-gravis` n'existe pas.

- [ ] **Step 3: Implémenter le composant**

```tsx
// app/(app)/_components/activity-cols-gravis.tsx
import { createClient } from '@/lib/supabase/server'
import { toActivityColCrossings } from '@/lib/dashboard/cols'
import type { ActivityColCrossingRowDto } from '@/lib/dashboard/cols'
import { ChartCard } from './chart-card'

export async function ActivityColsGravis({
  userId,
  garminActivityId,
}: {
  readonly userId: string
  readonly garminActivityId: number
}) {
  const supabase = await createClient()
  const { data } = await supabase
    .from('col_crossings')
    .select('col_id, crossed_at, cols(name, elevation_m)')
    .eq('user_id', userId)
    .eq('garmin_activity_id', garminActivityId)
    .order('crossed_at', { ascending: true })

  const crossings = toActivityColCrossings((data ?? []) as ActivityColCrossingRowDto[])
  if (crossings.length === 0) return null

  return (
    <ChartCard title="Cols gravis" description="Cols franchis pendant cette activité">
      <ul className="divide-y">
        {crossings.map((c) => (
          <li key={c.colId} className="flex items-center justify-between py-2 text-sm">
            <span className="font-medium">{c.name}</span>
            <span className="text-muted-foreground">
              {c.elevationM === null ? '—' : `${String(c.elevationM)} m`}
            </span>
          </li>
        ))}
      </ul>
    </ChartCard>
  )
}
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pnpm vitest run tests/unit/components/activity-cols-gravis.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Monter le composant dans la fiche activité**

Dans `app/(app)/history/[id]/page.tsx`, ajouter les imports (à côté des imports de
composants existants, ligne 5-9) :

```tsx
import { ActivityColsGravis } from '../../_components/activity-cols-gravis'
import { ColsGravisSkeleton } from '../../_components/skeletons/cols-gravis-skeleton'
```

Modifier le retour JSX de `ActivityDetailPage` (lignes 106-134), qui contient actuellement :

```tsx
      <Suspense fallback={<ActivityDetailSkeleton />}>
        <ActivityDetailBody userId={userId} activity={activity} />
      </Suspense>
    </div>
  )
}
```

Remplacer par :

```tsx
      <Suspense fallback={<ActivityDetailSkeleton />}>
        <ActivityDetailBody userId={userId} activity={activity} />
      </Suspense>

      <Suspense fallback={<ColsGravisSkeleton />}>
        <ActivityColsGravis userId={userId} garminActivityId={activity.garmin_activity_id} />
      </Suspense>
    </div>
  )
}
```

`userId` et `activity.garmin_activity_id` sont déjà disponibles à cet endroit (`userId` vient
de `requireOnboarded()` ligne 88, `activity` de la requête `activities` lignes 92-103) — ne
pas les re-fetcher.

- [ ] **Step 6: Vérification manuelle en navigateur**

Run: `pnpm dev`

Sur une activité connue pour avoir franchi un col (vérifier en base via
`select * from col_crossings where garmin_activity_id = ...` si besoin, ou choisir une
activité vélo/course en montagne récente) :
1. Ouvrir `/history/<id>`.
2. Vérifier qu'une section "Cols gravis" apparaît avec le nom et l'altitude du/des col(s).
3. Ouvrir une activité sans franchissement (ex. natation) : vérifier qu'aucune section
   "Cols gravis" n'apparaît (ni carte vide, ni skeleton bloqué).
4. Observer que le reste de la fiche (analyse coach, graphiques) s'affiche sans attendre la
   section cols — le skeleton `ColsGravisSkeleton` peut apparaître brièvement indépendamment
   du reste.

- [ ] **Step 7: Lancer les quality gates frontend**

Run: `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
Expected: tout passe.

- [ ] **Step 8: Commit**

```bash
git add "app/(app)/_components/activity-cols-gravis.tsx" \
        "app/(app)/history/[id]/page.tsx" \
        tests/unit/components/activity-cols-gravis.test.tsx
git commit -m "feat(history): affiche les cols gravis sur la fiche activité"
```

## Critères d'acceptation (rappel du spec)

1. Sur `/history/[id]`, si l'activité a franchi ≥1 col, une section "Cols gravis" affiche le
   nom et l'altitude de chaque col, dans l'ordre chronologique de franchissement.
2. Si l'activité n'a franchi aucun col, aucune section n'est affichée.
3. Le fetch des cols gravis ne bloque pas l'affichage du reste de la fiche (Suspense isolé,
   pas ajouté au `Promise.all` de `ActivityDetailBody`).
4. `pnpm lint && pnpm typecheck && pnpm test && pnpm build` passent.
