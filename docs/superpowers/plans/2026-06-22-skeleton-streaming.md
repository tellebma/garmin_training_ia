# Skeleton & rendu progressif — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher chaque section de page dès que sa donnée est prête (streaming Suspense) avec des skeletons fidèles factorisés, couvrir les routes sans état de chargement, et polir l'accessibilité.

**Architecture:** Modèle shell + streaming Suspense (Next 15 App Router). Une primitive `Skeleton` partagée + un wrapper `LoadingRegion` accessible. Chaque page rend son shell immédiatement et enveloppe ses sections lentes dans `<Suspense fallback={<SectionSkeleton/>}>`, chaque section étant un composant serveur async qui fait son propre fetch.

**Tech Stack:** Next.js 15 (App Router, RSC, Suspense), TypeScript strict, Tailwind 4, Vitest + Testing Library (jsdom).

## Global Constraints

- Frontend : pas d'emoji dans l'UI (icônes Lucide). Tests Vitest dans `tests/unit/**/*.test.tsx` avec en-tête `// @vitest-environment jsdom`. Commandes depuis la racine repo.
- Conserver `export const revalidate = 0` sur chaque page modifiée.
- Conserver le fail-soft des appels worker (un échec rend un état vide, ne casse pas la page).
- Conserver les `Promise.all` à l'intérieur de chaque section (parallélisme intra-bloc).
- Aucune modification de logique métier, de requête SQL, ni du worker.
- Conventional Commits stricts ; body lines ≤ 100 chars.
- Quality gates par tâche front : `pnpm test -- <pattern>`, puis `pnpm lint && pnpm typecheck`. Build complet (`pnpm build`) vérifié en fin de plan.

---

### Task 1: Fondation — primitive `Skeleton` + `LoadingRegion`

**Files:**
- Create: `components/ui/skeleton.tsx`
- Create: `app/(app)/_components/skeletons/loading-region.tsx`
- Test: `tests/unit/components/skeleton.test.tsx`

**Interfaces:**
- Produces:
  - `Skeleton(props: React.ComponentProps<'div'>) -> JSX` — div animé, `aria-hidden`, classe `motion-reduce:animate-none`, passthrough `className`.
  - `LoadingRegion({ label: string, children: React.ReactNode }) -> JSX` — wrapper `role="status"`, `aria-label={label}`, `aria-busy`.

- [ ] **Step 1: Write the failing test**

```tsx
// tests/unit/components/skeleton.test.tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '@/app/(app)/_components/skeletons/loading-region'

afterEach(() => {
  cleanup()
})

describe('Skeleton', () => {
  it('renders a decorative animated block that respects reduced motion', () => {
    const { container } = render(<Skeleton className="h-8 w-24" data-testid="sk" />)
    const el = container.querySelector('[data-testid="sk"]') as HTMLElement
    expect(el).toBeTruthy()
    expect(el.getAttribute('aria-hidden')).toBe('true')
    expect(el.className).toContain('animate-pulse')
    expect(el.className).toContain('motion-reduce:animate-none')
    expect(el.className).toContain('h-8')
    expect(el.className).toContain('w-24')
  })
})

describe('LoadingRegion', () => {
  it('exposes an accessible status region with a label', () => {
    render(
      <LoadingRegion label="Chargement du profil">
        <Skeleton className="h-4 w-10" />
      </LoadingRegion>
    )
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toBe('Chargement du profil')
    expect(region.getAttribute('aria-busy')).toBe('true')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- skeleton`
Expected: FAIL — modules `@/components/ui/skeleton` et `loading-region` introuvables.

- [ ] **Step 3: Implement the `Skeleton` primitive**

```tsx
// components/ui/skeleton.tsx
import { cn } from '@/lib/utils'

function Skeleton({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      aria-hidden
      className={cn('bg-muted/50 animate-pulse rounded-md motion-reduce:animate-none', className)}
      {...props}
    />
  )
}

export { Skeleton }
```

- [ ] **Step 4: Implement `LoadingRegion`**

```tsx
// app/(app)/_components/skeletons/loading-region.tsx
export function LoadingRegion({
  label,
  children,
}: {
  readonly label: string
  readonly children: React.ReactNode
}) {
  return (
    <div role="status" aria-label={label} aria-busy>
      {children}
    </div>
  )
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm test -- skeleton`
Expected: PASS.

- [ ] **Step 6: Quality gates**

Run: `pnpm lint && pnpm typecheck`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add components/ui/skeleton.tsx "app/(app)/_components/skeletons/loading-region.tsx" tests/unit/components/skeleton.test.tsx
git commit -m "feat(ui): add shared Skeleton primitive and accessible LoadingRegion"
```

---

### Task 2: `/profile` streaming (l'appel worker 15 s ne bloque plus la page)

**Files:**
- Create: `app/(app)/profile/_components/discipline-levels-skeleton.tsx`
- Create: `app/(app)/profile/_components/discipline-levels-loader.tsx`
- Create: `app/(app)/profile/loading.tsx`
- Modify: `app/(app)/profile/page.tsx` (supprimer le fetch worker bloquant ~lignes 105-119 et le `import { workerPost }`, remplacer `<DisciplineLevelsSection ... />` ~ligne 217 par un `<Suspense>`)
- Test: `tests/unit/profile/discipline-levels-skeleton.test.tsx`

**Interfaces:**
- Consumes: `Skeleton` (Task 1), `DisciplineLevelsSection` (existant), `workerPost` (`@/lib/worker`), `createClient` (`@/lib/supabase/server`).
- Produces:
  - `DisciplineLevelsSkeleton() -> JSX`
  - `DisciplineLevelsLoader() -> Promise<JSX>` (async server component, fait l'appel worker en fail-soft et rend `DisciplineLevelsSection`).

- [ ] **Step 1: Write the failing test**

```tsx
// tests/unit/profile/discipline-levels-skeleton.test.tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { DisciplineLevelsSkeleton } from '@/app/(app)/profile/_components/discipline-levels-skeleton'

afterEach(() => {
  cleanup()
})

describe('DisciplineLevelsSkeleton', () => {
  it('renders a titled status region with placeholder rows', () => {
    render(<DisciplineLevelsSkeleton />)
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toContain('Niveau par discipline')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- discipline-levels-skeleton`
Expected: FAIL — module introuvable.

- [ ] **Step 3: Implement the skeleton**

```tsx
// app/(app)/profile/_components/discipline-levels-skeleton.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../../_components/skeletons/loading-region'

export function DisciplineLevelsSkeleton() {
  return (
    <LoadingRegion label="Chargement du niveau par discipline">
      <section className="space-y-3 rounded-lg border p-6">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-4 w-72" />
        <ul className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <li key={i} className="flex items-start justify-between gap-3 border-t pt-2">
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-3 w-full max-w-md" />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </LoadingRegion>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- discipline-levels-skeleton`
Expected: PASS.

- [ ] **Step 5: Implement the async loader**

Déplace la logique de fetch worker (actuellement `app/(app)/profile/page.tsx` lignes 105-119) dans un composant serveur async dédié :

```tsx
// app/(app)/profile/_components/discipline-levels-loader.tsx
import { createClient } from '@/lib/supabase/server'
import { workerPost } from '@/lib/worker'
import { DisciplineLevelsSection } from './discipline-levels-section'

export async function DisciplineLevelsLoader() {
  let disciplineLevels: Record<string, unknown> = {}
  try {
    const supabase = await createClient()
    const {
      data: { session },
    } = await supabase.auth.getSession()
    if (session?.access_token) {
      const res = await workerPost<{ disciplines?: Record<string, unknown> }>(
        '/coach/discipline-levels',
        {},
        session.access_token,
        15_000
      )
      disciplineLevels = res.disciplines ?? {}
    }
  } catch {
    disciplineLevels = {}
  }
  return <DisciplineLevelsSection disciplines={disciplineLevels as never} />
}
```

- [ ] **Step 6: Refactor `profile/page.tsx` to stream the section**

Dans `app/(app)/profile/page.tsx` :

1. Ajouter en tête `import { Suspense } from 'react'`.
2. Supprimer l'import `import { workerPost } from '@/lib/worker'` (ligne 11) — il part dans le loader.
3. Ajouter les imports du loader + skeleton :

```tsx
import { DisciplineLevelsLoader } from './_components/discipline-levels-loader'
import { DisciplineLevelsSkeleton } from './_components/discipline-levels-skeleton'
```

4. Supprimer entièrement le bloc « Fetch discipline levels from worker (fail soft) » (lignes 105-119, du commentaire jusqu'au `}` fermant le `catch`).
5. Remplacer la ligne `<DisciplineLevelsSection disciplines={disciplineLevels as never} />` (~ligne 217) par :

```tsx
      <Suspense fallback={<DisciplineLevelsSkeleton />}>
        <DisciplineLevelsLoader />
      </Suspense>
```

6. Supprimer l'import désormais inutilisé `import { DisciplineLevelsSection } from './_components/discipline-levels-section'` (ligne 10) — il n'est plus référencé que par le loader.

- [ ] **Step 7: Add `profile/loading.tsx`**

```tsx
// app/(app)/profile/loading.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../_components/skeletons/loading-region'

export default function ProfileLoading() {
  return (
    <LoadingRegion label="Chargement du profil">
      <div className="space-y-6">
        <Skeleton className="h-8 w-40" />
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-full rounded-lg" />
        ))}
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 8: Quality gates**

Run: `pnpm test -- discipline-levels && pnpm lint && pnpm typecheck`
Expected: PASS (dont la non-régression du test existant `discipline-levels-section`).

- [ ] **Step 9: Commit**

```bash
git add "app/(app)/profile/_components/discipline-levels-skeleton.tsx" "app/(app)/profile/_components/discipline-levels-loader.tsx" "app/(app)/profile/loading.tsx" "app/(app)/profile/page.tsx" tests/unit/profile/discipline-levels-skeleton.test.tsx
git commit -m "feat(profile): stream discipline levels section behind a skeleton"
```

---

### Task 3: `/today` streaming (briefing + sections data)

**Files:**
- Create: `app/(app)/_components/skeletons/briefing-card-skeleton.tsx`
- Modify: `app/(app)/today/page.tsx`
- Modify: `app/(app)/today/loading.tsx` (reconstruire avec la primitive)
- Test: `tests/unit/components/briefing-card-skeleton.test.tsx`

**Interfaces:**
- Consumes: `Skeleton`, `LoadingRegion` (Task 1).
- Produces: `BriefingCardSkeleton() -> JSX`.

> Note d'exécution : `app/(app)/today/page.tsx` charge tout via un seul `Promise.all` (briefing + 9 requêtes Supabase). Le gain principal est de **sortir le briefing du chemin bloquant**. Approche retenue, conservatrice et sûre : garder le `Promise.all` Supabase pour le corps de page, mais déplacer **uniquement** le `BriefingCard` derrière un `<Suspense>` alimenté par un loader async qui appelle `getDailyBriefing()`. On retire `briefingPromise`/`briefingResult` du `Promise.all`. Le shell (header, `GarminStatusBanner`, `SyncTimingsCard`) reste rendu par la page.

- [ ] **Step 1: Write the failing test**

```tsx
// tests/unit/components/briefing-card-skeleton.test.tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { BriefingCardSkeleton } from '@/app/(app)/_components/skeletons/briefing-card-skeleton'

afterEach(() => {
  cleanup()
})

describe('BriefingCardSkeleton', () => {
  it('renders an accessible loading region for the daily briefing', () => {
    render(<BriefingCardSkeleton />)
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toContain('briefing')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- briefing-card-skeleton`
Expected: FAIL — module introuvable.

- [ ] **Step 3: Implement the skeleton**

```tsx
// app/(app)/_components/skeletons/briefing-card-skeleton.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from './loading-region'

export function BriefingCardSkeleton() {
  return (
    <LoadingRegion label="Chargement du briefing du jour">
      <section className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-5 w-24 rounded-full" />
        </div>
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-20 w-full rounded-md" />
      </section>
    </LoadingRegion>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- briefing-card-skeleton`
Expected: PASS.

- [ ] **Step 5: Extract a briefing loader and stream it in `today/page.tsx`**

Dans `app/(app)/today/page.tsx` :

1. Ajouter `import { Suspense } from 'react'` et
   `import { BriefingCardSkeleton } from '../_components/skeletons/briefing-card-skeleton'`.
2. Retirer `briefingPromise` du `Promise.all` et la déstructuration `briefingResult`
   (ne plus inclure `briefingPromise` dans le tableau ni `briefingResult` dans la
   destructuration). Supprimer la ligne
   `const briefing = briefingResult?.success ? briefingResult.briefing : null`.
3. Définir, dans le même fichier (au-dessus de `TodayPage` ou en bas), un composant
   serveur async local qui charge et rend le briefing en fail-soft :

```tsx
async function BriefingLoader() {
  const result = await getDailyBriefing().catch(() => null)
  const briefing = result?.success ? result.briefing : null
  if (!briefing) return null
  return <BriefingCard briefing={briefing} />
}
```

4. Remplacer la ligne `{briefing && <BriefingCard briefing={briefing} />}` par :

```tsx
      <Suspense fallback={<BriefingCardSkeleton />}>
        <BriefingLoader />
      </Suspense>
```

5. Supprimer la ligne désormais inutile
   `const briefingPromise = getDailyBriefing().catch(() => null)` (le loader appelle
   `getDailyBriefing` directement).

- [ ] **Step 6: Rebuild `today/loading.tsx` from the primitive**

```tsx
// app/(app)/today/loading.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../_components/skeletons/loading-region'

export default function TodayLoading() {
  return (
    <LoadingRegion label="Chargement de la page du jour">
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-36 w-full rounded-lg" />
        <div className="grid grid-cols-3 gap-2">
          <Skeleton className="h-24 rounded-lg" />
          <Skeleton className="h-24 rounded-lg" />
          <Skeleton className="h-24 rounded-lg" />
        </div>
        <Skeleton className="h-64 w-full rounded-lg" />
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 7: Quality gates**

Run: `pnpm test -- briefing-card-skeleton && pnpm lint && pnpm typecheck`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add "app/(app)/_components/skeletons/briefing-card-skeleton.tsx" "app/(app)/today/page.tsx" "app/(app)/today/loading.tsx" tests/unit/components/briefing-card-skeleton.test.tsx
git commit -m "feat(today): stream the daily briefing behind a skeleton"
```

---

### Task 4: `/stats` streaming (corps du cockpit)

**Files:**
- Create: `app/(app)/_components/skeletons/cockpit-skeleton.tsx`
- Modify: `app/(app)/stats/page.tsx`
- Modify: `app/(app)/stats/loading.tsx` (reconstruire avec la primitive)
- Test: `tests/unit/components/cockpit-skeleton.test.tsx`

**Interfaces:**
- Consumes: `Skeleton`, `LoadingRegion` (Task 1).
- Produces: `CockpitSkeleton() -> JSX`.

> Note d'exécution : lire d'abord `app/(app)/stats/page.tsx` en entier. La page fait
> un `Promise.all` de 6 requêtes Supabase puis calcule un objet `cockpit` local. Le
> shell = en-tête (label + titre) + barre de filtres de période. Extraire **tout ce
> qui dépend de `cockpit`** (KPIs, lecture coach, graphes, détail hebdo) dans un
> composant serveur async `CockpitBody` recevant les `searchParams` résolus
> (période, discipline) et faisant lui-même le `Promise.all` + le calcul `cockpit`.
> La page rend le shell puis `<Suspense fallback={<CockpitSkeleton/>}><CockpitBody .../></Suspense>`.
> Conserver `revalidate = 0` et la signature de filtrage existante.

- [ ] **Step 1: Write the failing test**

```tsx
// tests/unit/components/cockpit-skeleton.test.tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { CockpitSkeleton } from '@/app/(app)/_components/skeletons/cockpit-skeleton'

afterEach(() => {
  cleanup()
})

describe('CockpitSkeleton', () => {
  it('renders an accessible loading region for the cockpit', () => {
    render(<CockpitSkeleton />)
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toContain('cockpit')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- cockpit-skeleton`
Expected: FAIL — module introuvable.

- [ ] **Step 3: Implement the skeleton**

```tsx
// app/(app)/_components/skeletons/cockpit-skeleton.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from './loading-region'

export function CockpitSkeleton() {
  return (
    <LoadingRegion label="Chargement du cockpit">
      <div className="space-y-8">
        <Skeleton className="h-24 w-full rounded-md" />
        <div className="grid border-y sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="space-y-3 p-4">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-7 w-24" />
            </div>
          ))}
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-72 w-full rounded-md" />
          <Skeleton className="h-72 w-full rounded-md" />
        </div>
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- cockpit-skeleton`
Expected: PASS.

- [ ] **Step 5: Extract `CockpitBody` and stream it**

Dans `app/(app)/stats/page.tsx` (après lecture complète) :

1. Ajouter `import { Suspense } from 'react'` et
   `import { CockpitSkeleton } from '../_components/skeletons/cockpit-skeleton'`.
2. Créer un composant serveur async local `CockpitBody` qui reçoit en props les
   valeurs de filtre déjà résolues (ex. `{ userId, period, discipline }`), exécute le
   `Promise.all` des 6 requêtes Supabase et le calcul de l'objet `cockpit`, puis rend
   tout l'actuel corps dépendant de `cockpit` (KPIs, lecture coach, graphes, détail).
3. Dans `StatsPage`, ne garder au sommet que `requireOnboarded()` + lecture des
   `searchParams` (période/discipline). Rendre le shell (en-tête + filtres) puis :

```tsx
      <Suspense fallback={<CockpitSkeleton />}>
        <CockpitBody userId={userId} period={period} discipline={discipline} />
      </Suspense>
```

(adapter les noms de props aux variables réellement utilisées dans le fichier).

- [ ] **Step 6: Rebuild `stats/loading.tsx` from the primitive**

```tsx
// app/(app)/stats/loading.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../_components/skeletons/loading-region'

export default function StatsLoading() {
  return (
    <LoadingRegion label="Chargement du cockpit">
      <div className="space-y-8">
        <div className="flex items-end justify-between">
          <div className="space-y-2">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-8 w-64" />
          </div>
          <Skeleton className="h-9 w-44 rounded-md" />
        </div>
        <Skeleton className="h-24 w-full rounded-md" />
        <div className="grid border-y sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="space-y-3 p-4">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-7 w-24" />
            </div>
          ))}
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-72 w-full rounded-md" />
          <Skeleton className="h-72 w-full rounded-md" />
        </div>
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 7: Quality gates**

Run: `pnpm test -- cockpit-skeleton && pnpm lint && pnpm typecheck`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add "app/(app)/_components/skeletons/cockpit-skeleton.tsx" "app/(app)/stats/page.tsx" "app/(app)/stats/loading.tsx" tests/unit/components/cockpit-skeleton.test.tsx
git commit -m "feat(stats): stream the cockpit body behind a skeleton"
```

---

### Task 5: `/history/[id]` streaming (analyse + samples)

**Files:**
- Create: `app/(app)/_components/skeletons/activity-detail-skeleton.tsx`
- Create: `app/(app)/history/[id]/loading.tsx`
- Modify: `app/(app)/history/[id]/page.tsx`
- Test: `tests/unit/components/activity-detail-skeleton.test.tsx`

**Interfaces:**
- Consumes: `Skeleton`, `LoadingRegion` (Task 1).
- Produces: `ActivityDetailSkeleton() -> JSX`.

> Note d'exécution : lire d'abord `app/(app)/history/[id]/page.tsx` en entier. La page
> fait une 1ère requête `activities` (rapide) puis un `Promise.all` de 6 requêtes (dont
> `activity_samples`, lourd) et un calcul d'analyse local. Le shell = en-tête activité
> (titre/date issus de la 1ère requête). Extraire **tout ce qui dépend du `Promise.all`
> et de l'analyse** (lecture coach, comparaisons, graphes samples) dans un composant
> serveur async `ActivityDetailBody` recevant `{ userId, activity }` (l'activité déjà
> chargée). La page rend le shell puis
> `<Suspense fallback={<ActivityDetailSkeleton/>}><ActivityDetailBody .../></Suspense>`.
> Conserver le `notFound()` si l'activité n'existe pas, au niveau de la page (avant le
> Suspense).

- [ ] **Step 1: Write the failing test**

```tsx
// tests/unit/components/activity-detail-skeleton.test.tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ActivityDetailSkeleton } from '@/app/(app)/_components/skeletons/activity-detail-skeleton'

afterEach(() => {
  cleanup()
})

describe('ActivityDetailSkeleton', () => {
  it('renders an accessible loading region for the activity analysis', () => {
    render(<ActivityDetailSkeleton />)
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toContain('activité')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- activity-detail-skeleton`
Expected: FAIL — module introuvable.

- [ ] **Step 3: Implement the skeleton**

```tsx
// app/(app)/_components/skeletons/activity-detail-skeleton.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from './loading-region'

export function ActivityDetailSkeleton() {
  return (
    <LoadingRegion label="Chargement de l'analyse d'activité">
      <div className="space-y-6">
        <Skeleton className="h-24 w-full rounded-lg" />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-72 w-full rounded-lg" />
        <Skeleton className="h-72 w-full rounded-lg" />
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- activity-detail-skeleton`
Expected: PASS.

- [ ] **Step 5: Extract `ActivityDetailBody` and stream it**

Dans `app/(app)/history/[id]/page.tsx` (après lecture complète) :

1. Ajouter `import { Suspense } from 'react'` et
   `import { ActivityDetailSkeleton } from '../../_components/skeletons/activity-detail-skeleton'`.
2. Garder au sommet : `requireOnboarded()`, lecture de `params.id`, 1ère requête
   `activities`, et le `notFound()` si absent.
3. Créer un composant serveur async local `ActivityDetailBody` recevant l'activité
   chargée (et `userId`) ; y déplacer le `Promise.all` des 6 requêtes, le calcul
   d'analyse (`buildActivityCoachAnalysis`, `summarizeActivitySamples`) et tout le JSX
   d'analyse/graphes.
4. Rendre l'en-tête (titre/date/sport de l'activité) directement dans la page, puis :

```tsx
      <Suspense fallback={<ActivityDetailSkeleton />}>
        <ActivityDetailBody userId={userId} activity={activity} />
      </Suspense>
```

(adapter les noms de props/variables au fichier réel).

- [ ] **Step 6: Add `history/[id]/loading.tsx`**

```tsx
// app/(app)/history/[id]/loading.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../../_components/skeletons/loading-region'

export default function ActivityDetailLoading() {
  return (
    <LoadingRegion label="Chargement de l'activité">
      <div className="space-y-6">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-72 w-full rounded-lg" />
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 7: Quality gates**

Run: `pnpm test -- activity-detail-skeleton && pnpm lint && pnpm typecheck`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add "app/(app)/_components/skeletons/activity-detail-skeleton.tsx" "app/(app)/history/[id]/loading.tsx" "app/(app)/history/[id]/page.tsx" tests/unit/components/activity-detail-skeleton.test.tsx
git commit -m "feat(history): stream activity analysis behind a skeleton"
```

---

### Task 6: Reconstruire les `loading.tsx` restants + couverture `/profile/garmin`

**Files:**
- Modify: `app/(app)/plan/loading.tsx`
- Modify: `app/(app)/history/loading.tsx`
- Create: `app/(app)/profile/garmin/loading.tsx`

**Interfaces:**
- Consumes: `Skeleton`, `LoadingRegion` (Task 1).

> Pas de nouveau composant testable isolément ici (uniquement des `loading.tsx`, exclus
> de la couverture Vitest). La validation passe par `pnpm lint && pnpm typecheck` puis le
> `pnpm build` final.

- [ ] **Step 1: Rebuild `plan/loading.tsx`**

```tsx
// app/(app)/plan/loading.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../_components/skeletons/loading-region'

export default function PlanLoading() {
  return (
    <LoadingRegion label="Chargement du plan">
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-10 w-full" />
        <div className="space-y-2">
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg" />
          ))}
        </div>
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 2: Rebuild `history/loading.tsx`**

```tsx
// app/(app)/history/loading.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../_components/skeletons/loading-region'

export default function HistoryLoading() {
  return (
    <LoadingRegion label="Chargement de l'historique">
      <div className="space-y-6">
        <Skeleton className="h-8 w-32" />
        <div className="flex gap-2">
          <Skeleton className="h-9 w-32" />
          <Skeleton className="h-9 w-32" />
        </div>
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded" />
          ))}
        </div>
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 3: Add `profile/garmin/loading.tsx`**

```tsx
// app/(app)/profile/garmin/loading.tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../../_components/skeletons/loading-region'

export default function GarminLoading() {
  return (
    <LoadingRegion label="Chargement de la connexion Garmin">
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full rounded-lg" />
        <Skeleton className="h-10 w-40 rounded-md" />
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 4: Quality gates**

Run: `pnpm lint && pnpm typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add "app/(app)/plan/loading.tsx" "app/(app)/history/loading.tsx" "app/(app)/profile/garmin/loading.tsx"
git commit -m "feat(ui): rebuild loading states from shared Skeleton and cover Garmin route"
```

---

### Task 7: Vérification finale (build + suite complète)

**Files:** aucun (vérification).

- [ ] **Step 1: Run the full frontend test suite**

Run: `pnpm test`
Expected: PASS (toutes les suites, dont les nouveaux skeletons et la non-régression `briefing-card`/`discipline-levels-section`).

- [ ] **Step 2: Run the production build (streaming-sensitive)**

Run: `rm -rf .next && pnpm build`
Expected: build OK, aucune erreur de type ni de RSC (les composants serveur async dans Suspense doivent compiler).

- [ ] **Step 3: Manual streaming check (optionnel mais recommandé)**

Lancer `pnpm dev`, ouvrir `/profile` : le shell + formulaires s'affichent immédiatement,
l'encart « Niveau par discipline » apparaît après son skeleton sans bloquer la page.
Vérifier de même `/today`, `/stats`, `/history/[id]`.

---

## Self-Review (done by author)

- **Spec coverage:**
  - Primitive `Skeleton` partagée → Task 1. ✓
  - `LoadingRegion` accessible (`role="status"`, `aria-busy`, `aria-label`) → Task 1. ✓
  - `prefers-reduced-motion` (`motion-reduce:animate-none`) → Task 1 (primitive). ✓
  - Streaming `/profile` (appel worker 15 s) → Task 2. ✓
  - Streaming `/today` (briefing) → Task 3. ✓
  - Streaming `/stats` (cockpit) → Task 4. ✓
  - Streaming `/history/[id]` (analyse + samples) → Task 5. ✓
  - `loading.tsx` reconstruits (today, stats en Tasks 3/4 ; plan, history en Task 6) + manquants (profile Task 2, history/[id] Task 5, profile/garmin Task 6). ✓
  - `onboarding` exclu (conforme spec). ✓
  - Skeletons fidèles au layout → chaque skeleton reprend la structure du composant réel (Tasks 2-6). ✓
  - Préservation `revalidate = 0`, fail-soft, `Promise.all` intra-bloc → notes d'exécution Tasks 2-5. ✓
- **Placeholder scan:** pas de TBD/TODO. Les « notes d'exécution » des Tasks 3/4/5 décrivent l'extraction avec le code du Suspense et du loader/pattern ; elles invitent à lire le fichier complet avant édition car ces pages sont volumineuses, ce qui est une consigne précise, pas un placeholder. Les `loading.tsx` (exclus de coverage) sont validés par lint/typecheck/build, pas par test unitaire — explicité.
- **Type consistency:** `Skeleton` = `React.ComponentProps<'div'>` cohérent (Task 1) et consommé via `className` partout. `LoadingRegion({ label, children })` cohérent entre définition (Task 1) et usages (Tasks 2-6). Loaders async retournent du JSX rendu dans `<Suspense>`. Imports relatifs vérifiés selon la profondeur des dossiers (`../_components/skeletons/...` depuis `app/(app)/<page>/`, `../../_components/...` depuis `app/(app)/<page>/<sub>/`).
- **Ordre / indépendance:** Task 1 est prérequis de toutes les autres (primitives). Tasks 2-6 indépendantes entre elles (pages distinctes). Task 7 = vérif finale globale.
