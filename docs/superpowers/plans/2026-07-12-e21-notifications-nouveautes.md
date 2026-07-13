# E21 — Notifications de nouveautés (changelog interne) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un badge "nouveautés" (cloche) dans la nav, qui ouvre un panneau listant les
dernières nouveautés rédigées en français, alimenté par un fichier éditorial
`docs/nouveautes.md` distinct du `CHANGELOG.md` technique. L'état lu/non-lu est stocké par
utilisateur sur `athlete_profiles.last_seen_changelog_version`.

**Architecture:** Contenu → `docs/nouveautes.md` (markdown éditorial). Parsing → fonction pure
`lib/changelog/parse.ts` + wrapper de lecture disque `lib/changelog/read.ts`. État lu/non-lu →
colonne `athlete_profiles.last_seen_changelog_version` + server action
`app/actions/changelog.ts`. UI → composant client `components/nav/changelog-bell.tsx` (shadcn
`Sheet`), monté dans `app/(app)/layout.tsx` à côté de `SyncNowButton`.

**Tech Stack:** Next.js 15 App Router, Supabase (Postgres + RLS), TypeScript, shadcn/ui
(`sheet`), Vitest + Testing Library.

## Global Constraints

- `docs/nouveautes.md` est un contenu éditorial écrit à la main — 1-3 puces FR conviviales
  par version, orientées bénéfice utilisateur, pas de jargon technique.
- La colonne `last_seen_changelog_version` est nullable, sans backfill (cohérent avec le
  pattern des migrations `athlete_profiles` existantes, ex.
  `20260709000000_athlete_profiles_css.sql`).
- Comparaison de versions en chaîne exacte (pas de semver complexe) : les versions sont des
  tags déjà normalisés par semantic-release (`package.json` → `1.9.0`, etc.).
- Le panneau affiche au plus les 5 dernières versions de `docs/nouveautes.md`, pas
  l'historique complet.
- `CLAUDE.md` a déjà été mis à jour (commit `1db7cbf`) avec le rappel de tenir
  `docs/nouveautes.md` à jour à chaque feature visible — aucune action supplémentaire requise
  sur ce point dans ce plan.

---

### Task 1: Migration — colonne `last_seen_changelog_version`

**Files:**
- Create: `supabase/migrations/20260712100000_e21_changelog_last_seen.sql`

**Interfaces:**
- Produces : colonne `athlete_profiles.last_seen_changelog_version text` (nullable),
  consommée par la Task 5 (server action) et la Task 7 (layout).

- [ ] **Step 1: Écrire la migration**

```sql
-- supabase/migrations/20260712100000_e21_changelog_last_seen.sql
alter table public.athlete_profiles
  add column if not exists last_seen_changelog_version text;

comment on column public.athlete_profiles.last_seen_changelog_version is
  'Dernière version applicative (tag semantic-release) dont l''utilisateur a vu les
   nouveautés dans docs/nouveautes.md via le badge cloche (E21). NULL = jamais vu.';
```

- [ ] **Step 2: Vérifier la syntaxe SQL localement (si Supabase CLI configuré en local)**

Run: `supabase db lint` (si disponible en local) ou relecture manuelle — pas de test
automatisé pour une migration additive simple, cohérent avec les migrations
`athlete_profiles` précédentes du projet qui n'ont pas de test dédié.

Cette migration est auto-appliquée en CI sur `main` (E17) — pas d'application manuelle
requise en dev, sauf pour tester localement (`supabase db push` si un environnement Supabase
local est lié).

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260712100000_e21_changelog_last_seen.sql
git commit -m "feat(db): ajoute athlete_profiles.last_seen_changelog_version (E21)"
```

---

### Task 2: Contenu éditorial + parsing de `docs/nouveautes.md`

**Files:**
- Create: `docs/nouveautes.md`
- Create: `lib/changelog/parse.ts`
- Test: `tests/unit/changelog/parse.test.ts`

**Interfaces:**
- Consumes : rien (fonction pure).
- Produces : `ChangelogEntry { version: string; date: string; bullets: string[] }` et
  `parseChangelog(markdown: string): ChangelogEntry[]`, consommés par la Task 3.

- [ ] **Step 1: Écrire le contenu éditorial initial**

```markdown
docs/nouveautes.md
```

```
# Nouveautés

## 1.9.0 — 2026-07-11

- Connecte ton compte Strava : tes activités arrivent maintenant en temps réel, dès que tu
  termines une sortie.

## 1.8.0 — 2026-07-10

- Sur la fiche d'une activité, survole la carte GPS : le point correspondant s'illumine
  automatiquement sur les graphiques FC/allure (et inversement).
```

Contenu volontairement minimal au démarrage (2 versions récentes réelles, correspondant aux
PR #101 et #100) — chaque feature visible mergée ultérieurement ajoute sa propre entrée
(règle documentée dans `CLAUDE.md`, déjà en place).

- [ ] **Step 2: Écrire le test qui échoue**

Créer `tests/unit/changelog/parse.test.ts` :

```ts
import { describe, expect, it } from 'vitest'
import { parseChangelog } from '@/lib/changelog/parse'

describe('parseChangelog', () => {
  it('returns an empty array for empty markdown', () => {
    expect(parseChangelog('')).toEqual([])
  })

  it('parses a single section with bullets', () => {
    const md = `# Nouveautés\n\n## 1.9.0 — 2026-07-11\n\n- Première puce.\n- Deuxième puce.\n`
    expect(parseChangelog(md)).toEqual([
      { version: '1.9.0', date: '2026-07-11', bullets: ['Première puce.', 'Deuxième puce.'] },
    ])
  })

  it('parses multiple sections and preserves file order', () => {
    const md = `# Nouveautés\n\n## 1.9.0 — 2026-07-11\n\n- A.\n\n## 1.8.0 — 2026-07-10\n\n- B.\n`
    expect(parseChangelog(md).map((e) => e.version)).toEqual(['1.9.0', '1.8.0'])
  })

  it('returns an empty bullets array for a section with no bullets', () => {
    const md = `## 1.7.0 — 2026-07-09\n`
    expect(parseChangelog(md)).toEqual([{ version: '1.7.0', date: '2026-07-09', bullets: [] }])
  })

  it('ignores a malformed section title without the " — " separator', () => {
    const md = `## broken title\n\n- ignored bullet\n\n## 1.6.0 — 2026-07-09\n\n- kept.\n`
    expect(parseChangelog(md)).toEqual([
      { version: '1.6.0', date: '2026-07-09', bullets: ['kept.'] },
    ])
  })
})
```

- [ ] **Step 3: Lancer le test pour vérifier qu'il échoue**

Run: `pnpm vitest run tests/unit/changelog/parse.test.ts`
Expected: FAIL — le module `@/lib/changelog/parse` n'existe pas.

- [ ] **Step 4: Implémenter `parseChangelog`**

```ts
// lib/changelog/parse.ts
export interface ChangelogEntry {
  version: string
  date: string
  bullets: string[]
}

export function parseChangelog(markdown: string): ChangelogEntry[] {
  const sections = markdown.split(/^## /m).slice(1)
  const entries: ChangelogEntry[] = []

  for (const section of sections) {
    const lines = section.split('\n')
    const title = lines[0]?.trim() ?? ''
    const separatorIndex = title.indexOf(' — ')
    if (separatorIndex === -1) continue

    const version = title.slice(0, separatorIndex).trim()
    const date = title.slice(separatorIndex + 3).trim()
    const bullets = lines
      .slice(1)
      .filter((line) => line.trim().startsWith('- '))
      .map((line) => line.trim().slice(2).trim())

    entries.push({ version, date, bullets })
  }

  return entries
}
```

- [ ] **Step 5: Lancer le test pour vérifier qu'il passe**

Run: `pnpm vitest run tests/unit/changelog/parse.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add docs/nouveautes.md lib/changelog/parse.ts tests/unit/changelog/parse.test.ts
git commit -m "feat(changelog): ajoute docs/nouveautes.md et son parseur"
```

---

### Task 3: Lecture disque — `loadChangelog`

**Files:**
- Create: `lib/changelog/read.ts`
- Test: `tests/unit/changelog/read.test.ts`

**Interfaces:**
- Consumes : `parseChangelog` (`@/lib/changelog/parse`, Task 2).
- Produces : `loadChangelog(): Promise<ChangelogEntry[]>`, consommé par la Task 7.

- [ ] **Step 1: Écrire le test qui échoue**

Ce test lit le vrai fichier `docs/nouveautes.md` créé en Task 2 (pas de mock de `fs`) — il
vérifie l'intégration réelle parsing + disque plutôt que de dupliquer les cas déjà couverts
par `parse.test.ts`.

```ts
// tests/unit/changelog/read.test.ts
import { describe, expect, it } from 'vitest'
import { loadChangelog } from '@/lib/changelog/read'

describe('loadChangelog', () => {
  it('reads and parses docs/nouveautes.md from the repo root', async () => {
    const entries = await loadChangelog()
    expect(entries.length).toBeGreaterThanOrEqual(2)
    expect(entries[0]).toMatchObject({ version: '1.9.0', date: '2026-07-11' })
    expect(entries[0]?.bullets.length).toBeGreaterThan(0)
  })
})
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pnpm vitest run tests/unit/changelog/read.test.ts`
Expected: FAIL — le module `@/lib/changelog/read` n'existe pas.

- [ ] **Step 3: Implémenter `loadChangelog`**

```ts
// lib/changelog/read.ts
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { parseChangelog } from './parse'
import type { ChangelogEntry } from './parse'

const CHANGELOG_PATH = path.join(process.cwd(), 'docs', 'nouveautes.md')

export async function loadChangelog(): Promise<ChangelogEntry[]> {
  const markdown = await readFile(CHANGELOG_PATH, 'utf-8').catch(() => '')
  return parseChangelog(markdown)
}
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pnpm vitest run tests/unit/changelog/read.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lib/changelog/read.ts tests/unit/changelog/read.test.ts
git commit -m "feat(changelog): ajoute loadChangelog (lecture disque de nouveautes.md)"
```

---

### Task 4: Server action `markChangelogSeen`

**Files:**
- Create: `app/actions/changelog.ts`
- Test: `tests/unit/actions/changelog.test.ts`

**Interfaces:**
- Consumes : `createClient` (`@/lib/supabase/server`).
- Produces : `markChangelogSeen(version: string): Promise<{ success: boolean }>`, consommé
  par la Task 6 (`ChangelogBell`).

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/unit/actions/changelog.test.ts`, calqué sur
`tests/unit/actions/activity-feedback.test.ts` :

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSession = vi.fn()
const eq = vi.fn()
// Represents the resolved `{ data, error }` the Supabase chain yields once `.eq(...)`
// (the last call in the chain) is invoked — distinct from `profileQuery.update`, the
// query-builder method itself, which is asserted on separately below.
const updateResult = vi.fn()

const profileQuery = {
  update: vi.fn(),
  eq,
}
profileQuery.update.mockReturnValue(profileQuery)
profileQuery.eq.mockImplementation(() => updateResult())

vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({
    auth: { getSession },
    from: () => profileQuery,
  }),
}))

describe('markChangelogSeen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getSession.mockResolvedValue({ data: { session: { user: { id: 'user-1' } } } })
    updateResult.mockResolvedValue({ error: null })
    profileQuery.update.mockReturnValue(profileQuery)
  })

  it('rejects an unauthenticated request', async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } })
    const { markChangelogSeen } = await import('@/app/actions/changelog')

    await expect(markChangelogSeen('1.9.0')).resolves.toEqual({ success: false })
    expect(profileQuery.update).not.toHaveBeenCalled()
  })

  it('updates last_seen_changelog_version for the current user', async () => {
    const { markChangelogSeen } = await import('@/app/actions/changelog')

    await expect(markChangelogSeen('1.9.0')).resolves.toEqual({ success: true })
    expect(profileQuery.update).toHaveBeenCalledWith({ last_seen_changelog_version: '1.9.0' })
  })

  it('returns success: false on a database error', async () => {
    updateResult.mockResolvedValueOnce({ error: { message: 'db unavailable' } })
    const { markChangelogSeen } = await import('@/app/actions/changelog')

    await expect(markChangelogSeen('1.9.0')).resolves.toEqual({ success: false })
  })
})
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pnpm vitest run tests/unit/actions/changelog.test.ts`
Expected: FAIL — le module `@/app/actions/changelog` n'existe pas.

- [ ] **Step 3: Implémenter la server action**

```ts
// app/actions/changelog.ts
'use server'

import { createClient } from '@/lib/supabase/server'

export async function markChangelogSeen(version: string): Promise<{ success: boolean }> {
  const supabase = await createClient()
  const { data: sessionData } = await supabase.auth.getSession()
  const userId = sessionData.session?.user.id
  if (!userId) return { success: false }

  const { error } = await supabase
    .from('athlete_profiles')
    .update({ last_seen_changelog_version: version })
    .eq('user_id', userId)

  return { success: !error }
}
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pnpm vitest run tests/unit/actions/changelog.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/actions/changelog.ts tests/unit/actions/changelog.test.ts
git commit -m "feat(changelog): ajoute la server action markChangelogSeen"
```

---

### Task 5: Installer le composant shadcn `sheet`

**Files:**
- Create: `components/ui/sheet.tsx` (généré par la CLI shadcn)
- Modify: `package.json` (ajout de `@radix-ui/react-dialog` en dépendance, ajouté
  automatiquement par la CLI)

**Interfaces:**
- Produces : `Sheet`, `SheetContent`, `SheetHeader`, `SheetTitle`, `SheetDescription`,
  `SheetTrigger` (exports standards shadcn/ui), consommés par la Task 6.

Le projet a `components.json` déjà configuré (style `default`, alias `@/components/ui`) mais
n'a **aucun** composant overlay de type panneau installé (seul `alert-dialog` existe, pour les
confirmations destructives) — `@radix-ui/react-dialog` (dépendance du composant `sheet`)
n'est pas présent dans `package.json`.

- [ ] **Step 1: Installer le composant**

Run: `pnpm dlx shadcn@latest add sheet`
Expected: crée `components/ui/sheet.tsx`, ajoute `@radix-ui/react-dialog` (et éventuellement
`@radix-ui/react-visually-hidden` selon la version de la CLI) dans les dépendances de
`package.json`/`pnpm-lock.yaml`.

- [ ] **Step 2: Vérifier que le build n'est pas cassé**

Run: `pnpm typecheck && pnpm build`
Expected: PASS — le composant généré n'est pas encore utilisé nulle part, doit compiler tel
quel.

- [ ] **Step 3: Commit**

```bash
git add components/ui/sheet.tsx package.json pnpm-lock.yaml
git commit -m "chore(ui): installe le composant shadcn sheet"
```

---

### Task 6: Composant `ChangelogBell`

**Files:**
- Create: `components/nav/changelog-bell.tsx`
- Test: `tests/unit/components/nav/changelog-bell.test.tsx`

**Interfaces:**
- Consumes : `markChangelogSeen` (`@/app/actions/changelog`, Task 4), `ChangelogEntry`
  (`@/lib/changelog/parse`, Task 2), `Sheet`/`SheetContent`/`SheetHeader`/`SheetTitle`/
  `SheetDescription`/`SheetTrigger` (`@/components/ui/sheet`, Task 5), `Bell` (`lucide-react`).
- Produces : `ChangelogBell({ entries: ChangelogEntry[]; latestVersion: string | null;
  initialLastSeenVersion: string | null })`, consommé par la Task 7.

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/unit/components/nav/changelog-bell.test.tsx` :

```tsx
// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi, beforeEach } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChangelogBell } from '@/components/nav/changelog-bell'

const markChangelogSeen = vi.fn()

vi.mock('@/app/actions/changelog', () => ({
  markChangelogSeen: (...args: unknown[]) => markChangelogSeen(...args) as unknown,
}))

const entries = [
  { version: '1.9.0', date: '2026-07-11', bullets: ['Strava en temps réel.'] },
  { version: '1.8.0', date: '2026-07-10', bullets: ['Survol carte/graphiques corrélé.'] },
]

afterEach(cleanup)

// jsdom n'implémente pas l'API Pointer Events utilisée par Radix Dialog (base du
// composant Sheet) pour la gestion du focus/dismiss — sans ce polyfill, un clic
// simulé via `userEvent` sur le trigger lève `hasPointerCapture is not a function`.
// Premier composant Radix testé dans ce projet (`alert-dialog` n'a encore aucun test) :
// pas de précédent existant à suivre, ce polyfill est le correctif standard documenté
// par la communauté Radix pour jsdom.
beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.setPointerCapture ??= () => undefined
  Element.prototype.releasePointerCapture ??= () => undefined
  Element.prototype.scrollIntoView ??= () => undefined
})

describe('ChangelogBell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    markChangelogSeen.mockResolvedValue({ success: true })
  })

  it('shows an unread badge when the latest version has not been seen', () => {
    render(
      <ChangelogBell entries={entries} latestVersion="1.9.0" initialLastSeenVersion="1.8.0" />
    )
    expect(screen.getByTestId('changelog-unread-dot')).toBeTruthy()
  })

  it('does not show a badge when the latest version has already been seen', () => {
    render(
      <ChangelogBell entries={entries} latestVersion="1.9.0" initialLastSeenVersion="1.9.0" />
    )
    expect(screen.queryByTestId('changelog-unread-dot')).toBeNull()
  })

  it('does not show a badge when there is no changelog entry', () => {
    render(<ChangelogBell entries={[]} latestVersion={null} initialLastSeenVersion={null} />)
    expect(screen.queryByTestId('changelog-unread-dot')).toBeNull()
  })

  it('opens the panel, lists entries, marks as seen and clears the badge', async () => {
    const user = userEvent.setup()
    render(
      <ChangelogBell entries={entries} latestVersion="1.9.0" initialLastSeenVersion="1.8.0" />
    )

    await user.click(screen.getByRole('button', { name: /nouveautés/i }))

    expect(await screen.findByText('Strava en temps réel.')).toBeTruthy()
    expect(screen.getByText('Survol carte/graphiques corrélé.')).toBeTruthy()
    expect(markChangelogSeen).toHaveBeenCalledWith('1.9.0')
    expect(screen.queryByTestId('changelog-unread-dot')).toBeNull()
  })
})
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `pnpm vitest run tests/unit/components/nav/changelog-bell.test.tsx`
Expected: FAIL — le module `@/components/nav/changelog-bell` n'existe pas.

- [ ] **Step 3: Implémenter le composant**

```tsx
// components/nav/changelog-bell.tsx
'use client'

import { useState } from 'react'
import { Bell } from 'lucide-react'
import { markChangelogSeen } from '@/app/actions/changelog'
import type { ChangelogEntry } from '@/lib/changelog/parse'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'

const MAX_VISIBLE_ENTRIES = 5

interface ChangelogBellProps {
  entries: ChangelogEntry[]
  latestVersion: string | null
  initialLastSeenVersion: string | null
}

export function ChangelogBell({
  entries,
  latestVersion,
  initialLastSeenVersion,
}: Readonly<ChangelogBellProps>) {
  const [lastSeenVersion, setLastSeenVersion] = useState(initialLastSeenVersion)
  const hasUnread = latestVersion !== null && latestVersion !== lastSeenVersion
  const visibleEntries = entries.slice(0, MAX_VISIBLE_ENTRIES)

  function onOpenChange(open: boolean) {
    if (open && latestVersion && latestVersion !== lastSeenVersion) {
      setLastSeenVersion(latestVersion)
      void markChangelogSeen(latestVersion)
    }
  }

  return (
    <Sheet onOpenChange={onOpenChange}>
      <SheetTrigger asChild>
        <button
          type="button"
          aria-label="Nouveautés"
          className="relative rounded-md border p-2 text-sm"
        >
          <Bell size={16} aria-hidden="true" />
          {hasUnread && (
            <span
              data-testid="changelog-unread-dot"
              className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-red-500"
            />
          )}
        </button>
      </SheetTrigger>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Nouveautés</SheetTitle>
          <SheetDescription>Les dernières améliorations de l&rsquo;app.</SheetDescription>
        </SheetHeader>
        <div className="mt-4 space-y-6 px-4">
          {visibleEntries.map((entry) => (
            <div key={entry.version}>
              <p className="text-sm font-semibold">
                {entry.version} <span className="text-muted-foreground font-normal">— {entry.date}</span>
              </p>
              <ul className="text-muted-foreground mt-2 list-disc space-y-1 pl-4 text-sm">
                {entry.bullets.map((bullet) => (
                  <li key={bullet}>{bullet}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  )
}
```

Note d'implémentation : si le composant `Sheet` généré par la CLI shadcn (Task 5) expose une
API différente sur un point précis (ex. nom de prop pour la fermeture, structure interne de
`SheetTrigger`), lire `components/ui/sheet.tsx` généré avant d'ajuster — l'API ci-dessus est
l'API standard shadcn/ui (`Sheet`/`SheetTrigger`/`SheetContent` avec `onOpenChange` sur
`Sheet`), stable depuis plusieurs versions de la librairie.

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `pnpm vitest run tests/unit/components/nav/changelog-bell.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Lancer les quality gates frontend**

Run: `pnpm lint && pnpm typecheck && pnpm test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add components/nav/changelog-bell.tsx tests/unit/components/nav/changelog-bell.test.tsx
git commit -m "feat(nav): ajoute le badge et le panneau de nouveautés (ChangelogBell)"
```

---

### Task 7: Intégration dans `app/(app)/layout.tsx`

**Files:**
- Modify: `app/(app)/layout.tsx`

**Interfaces:**
- Consumes : `loadChangelog` (`@/lib/changelog/read`, Task 3), `ChangelogBell`
  (`@/components/nav/changelog-bell`, Task 6), `getCurrentUser`
  (`@/lib/supabase/current-user`, déjà utilisé dans ce fichier).
- Produces : rien (point d'intégration final).

Le fichier actuel :

```tsx
export default async function AppLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const user = await getCurrentUser()

  if (!user) {
    redirect('/login')
  }

  const supabase = await createClient()
  const [adminResult, maintenanceResult] = await Promise.all([
    supabase.rpc('is_admin_caller'),
    supabase.rpc('is_feature_flag_active', { p_key: 'maintenance_mode' }),
  ])
  const isAdmin = adminResult.data as boolean | null
  const maintenanceActive = maintenanceResult.data as boolean | null

  if (maintenanceActive && !isAdmin) {
    return <MaintenancePage />
  }

  return (
    <div className="flex min-h-screen">
      <SideNav isAdmin={Boolean(isAdmin)} />
      <main className="flex-1 pb-20 md:pb-0 md:pl-64">
        <div className="container mx-auto max-w-6xl px-4 py-6">
          <div className="mb-4 flex justify-end">
            <SyncNowButton />
          </div>
          {children}
        </div>
      </main>
      <BottomNav />
    </div>
  )
}
```

- [ ] **Step 1: Charger le changelog et l'état lu/non-lu, en parallèle du reste**

```tsx
import { redirect } from 'next/navigation'
import { BottomNav } from '@/components/nav/bottom-nav'
import { SideNav } from '@/components/nav/side-nav'
import { ChangelogBell } from '@/components/nav/changelog-bell'
import { createClient } from '@/lib/supabase/server'
import { getCurrentUser } from '@/lib/supabase/current-user'
import { loadChangelog } from '@/lib/changelog/read'
import { SyncNowButton } from '@/app/(app)/_components/sync-now-button'
import { MaintenancePage } from '@/app/(app)/_components/maintenance-page'

export default async function AppLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const user = await getCurrentUser()

  if (!user) {
    redirect('/login')
  }

  const supabase = await createClient()
  const [adminResult, maintenanceResult, changelogEntries, profileResult] = await Promise.all([
    supabase.rpc('is_admin_caller'),
    supabase.rpc('is_feature_flag_active', { p_key: 'maintenance_mode' }),
    loadChangelog(),
    supabase
      .from('athlete_profiles')
      .select('last_seen_changelog_version')
      .eq('user_id', user.id)
      .maybeSingle(),
  ])
  const isAdmin = adminResult.data as boolean | null
  const maintenanceActive = maintenanceResult.data as boolean | null
  const latestVersion = changelogEntries[0]?.version ?? null
  const lastSeenVersion = (profileResult.data?.last_seen_changelog_version ?? null) as
    | string
    | null

  if (maintenanceActive && !isAdmin) {
    return <MaintenancePage />
  }

  return (
    <div className="flex min-h-screen">
      <SideNav isAdmin={Boolean(isAdmin)} />
      <main className="flex-1 pb-20 md:pb-0 md:pl-64">
        <div className="container mx-auto max-w-6xl px-4 py-6">
          <div className="mb-4 flex items-center justify-between">
            <ChangelogBell
              entries={changelogEntries}
              latestVersion={latestVersion}
              initialLastSeenVersion={lastSeenVersion}
            />
            <SyncNowButton />
          </div>
          {children}
        </div>
      </main>
      <BottomNav />
    </div>
  )
}
```

- [ ] **Step 2: Vérification manuelle en navigateur**

Run: `pnpm dev`

1. Se connecter avec un compte dont `athlete_profiles.last_seen_changelog_version` est
   `null` (ou différent de `1.9.0`) : vérifier que le point rouge apparaît sur la cloche, sur
   `/today` comme sur les autres pages (layout partagé).
2. Cliquer sur la cloche : vérifier que le panneau s'ouvre avec les entrées de
   `docs/nouveautes.md`, et que le point rouge disparaît immédiatement.
3. Recharger la page : vérifier que le point rouge ne réapparaît pas (l'update Supabase a
   bien persisté `last_seen_changelog_version = '1.9.0'` — vérifiable aussi directement en
   base).
4. Vérifier sur mobile (DevTools responsive) que la cloche reste accessible et lisible à côté
   du bouton de synchronisation.

- [ ] **Step 3: Lancer les quality gates frontend**

Run: `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add "app/(app)/layout.tsx"
git commit -m "feat(nav): monte ChangelogBell dans le layout applicatif"
```

## Critères d'acceptation (rappel du spec)

1. Un utilisateur qui n'a jamais vu les nouveautés voit un badge sur la cloche.
2. Cliquer sur la cloche ouvre un panneau listant les dernières entrées de `nouveautes.md` en
   français, et fait disparaître le badge.
3. Après avoir vu les nouveautés, `athlete_profiles.last_seen_changelog_version` est mis à
   jour en base — le badge ne réapparaît pas tant qu'aucune nouvelle version n'est ajoutée à
   `nouveautes.md`.
4. `CLAUDE.md` documente déjà le rappel de mise à jour de `docs/nouveautes.md` (fait en amont
   de ce plan, commit `1db7cbf`).
5. `pnpm lint && pnpm typecheck && pnpm test && pnpm build` passent ; migration appliquée en
   CI (E17) sans intervention manuelle.
