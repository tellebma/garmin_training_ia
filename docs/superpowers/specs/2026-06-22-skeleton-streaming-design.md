# Skeleton & rendu progressif — Design

> Améliorations des états de chargement de l'app. Objectif prioritaire owner :
> afficher chaque information dès qu'elle est disponible plutôt que d'attendre que
> toutes les données soient prêtes, pour améliorer la perception de vitesse.

## Contexte

Aujourd'hui chaque page server-component fait un `Promise.all` (voire un appel
séquentiel) et **attend l'ensemble** avant de rendre. Le `loading.tsx` de la route
reste affiché jusqu'à ce que toute la page soit résolue.

Goulots mesurés :

- **`/profile`** rend la page seulement **après** l'appel worker
  `POST /coach/discipline-levels` (timeout **15 s**). Tout le profil est bloqué par
  cet appel.
- **`/today`** attend `getDailyBriefing()` (appel worker) + 9 requêtes Supabase
  groupées dans un `Promise.all`.
- **`/stats`** attend 6 requêtes Supabase groupées (pas d'appel worker ; la
  « Lecture coach » est calculée localement depuis les agrégats).
- **`/history/[id]`** attend l'activité puis 6 requêtes (dont `activity_samples`,
  potentiellement volumineux).

État des skeletons existants :

- 4 `loading.tsx` (`today`, `plan`, `stats`, `history`) écrits à la main avec des
  `div className="bg-muted/50 animate-pulse"` dupliquées.
- Aucun composant `Skeleton` partagé.
- Routes sans `loading.tsx` : `profile`, `history/[id]`, `profile/garmin`,
  `onboarding`.
- Seul `stats/loading.tsx` porte un `aria-label` ; pas de gestion
  `prefers-reduced-motion`.

## Objectif

1. Afficher chaque section dès que sa donnée est prête (rendu progressif /
   streaming), au lieu d'un blocage page entière.
2. Factoriser une primitive `Skeleton` partagée et des skeletons fidèles au layout.
3. Couvrir les routes sans état de chargement.
4. Polir l'accessibilité (`role="status"`, `aria-label`, `prefers-reduced-motion`).

## Architecture

Modèle **shell + streaming Suspense**, natif Next 15 App Router. Chaque page rend
immédiatement un shell statique (titres, navigation, filtres) et enveloppe ses
sections data-dépendantes dans `<Suspense fallback={<SectionSkeleton/>}>`, chaque
section étant un **composant serveur async** qui exécute son propre fetch. Le HTML
est streamé : un bloc se peint dès que sa donnée arrive, indépendamment des autres.

Condition nécessaire : la page ne doit plus `await` les données lentes avant de
retourner son JSX. Seuls les appels rapides et obligatoires restent au sommet
(`requireOnboarded()`, lecture des `searchParams`/`params`).

### Unités

**1. Primitive partagée — `components/ui/skeleton.tsx`**

Composant de style shadcn :

```tsx
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

Remplace toutes les `div bg-muted/animate-pulse` dupliquées. Le passthrough
`className` permet de fixer dimensions et arrondis par usage.

**2. Skeletons par section** — `app/(app)/_components/skeletons/`

Un composant par bloc réel, fidèle aux dimensions/structure du composant rendu
(réduction du layout shift). Liste prévue :

- `briefing-card-skeleton.tsx`
- `discipline-levels-skeleton.tsx`
- `cockpit-skeleton.tsx`
- `activity-detail-skeleton.tsx`
- `session-of-day-skeleton.tsx`
- `banister-chart-skeleton.tsx`
- `session-list-skeleton.tsx` (semaine `/plan`)
- `activity-list-skeleton.tsx` (`/history`)

Chaque skeleton est un composant pur (pas de fetch), réutilisable comme fallback
`<Suspense>` **et** dans les `loading.tsx`.

**3. Wrapper de chargement accessible** — `app/(app)/_components/skeletons/loading-region.tsx`

Petit wrapper :

```tsx
export function LoadingRegion({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div role="status" aria-label={label} aria-busy>
      {children}
    </div>
  )
}
```

Utilisé pour englober les fallbacks Suspense et le contenu des `loading.tsx`.

**4. Découpage streaming par page**

- **`/profile`** : extraire le chargement de `DisciplineLevelsSection` (appel worker
  15 s) dans un composant serveur async `DisciplineLevelsLoader`, enveloppé d'un
  `<Suspense fallback={<DisciplineLevelsSkeleton/>}>`. Le reste du profil
  (formulaires perso/perf/race/dispo) s'affiche immédiatement.
- **`/today`** : `BriefingCard` (appel `getDailyBriefing`) dans un `BriefingLoader`
  + Suspense dédié. Le shell + `SyncTimingsCard` + metric tiles s'affichent tout de
  suite. La séance du jour et le chart Banister (Supabase) ont chacun leur boundary.
- **`/stats`** : shell (titre + filtres de période) immédiat ; le corps du cockpit
  (6 requêtes + agrégats + lecture coach locale) dans un `CockpitLoader` + Suspense.
- **`/history/[id]`** : en-tête activité (1ère requête rapide) immédiat ; l'analyse
  coach + les graphes samples (`activity_samples`) dans un `ActivityDetailLoader` +
  Suspense.

**5. `loading.tsx`**

- Reconstruire les 4 existants (`today`, `plan`, `stats`, `history`) à partir des
  nouveaux skeletons + `Skeleton` primitive + `LoadingRegion`.
- Ajouter les manquants : `profile`, `history/[id]`, `profile/garmin`.
- Hors périmètre : `onboarding` (wizard piloté côté client, pas de bénéfice).

**6. A11y / polish**

- `Skeleton` : `motion-reduce:animate-none` (respect `prefers-reduced-motion`),
  `aria-hidden`.
- `loading.tsx` et fallbacks Suspense englobés dans `LoadingRegion`
  (`role="status"`, `aria-label`, `aria-busy`).

## Préservation du comportement

- Conserver `export const revalidate = 0` sur chaque page.
- Conserver le **fail-soft** des appels worker : un échec ne casse pas la page (le
  loader rend un état vide gracieux, comme aujourd'hui dans `/profile` et `/today`).
- Conserver les `Promise.all` **à l'intérieur** de chaque section (parallélisme
  intra-bloc). Le gain de perception vient de l'indépendance **entre** boundaries.
- Aucune modification de la logique métier, des requêtes SQL, ni du worker.

## Tests

- Vitest + Testing Library (jsdom), dans `tests/unit/**` :
  - `Skeleton` primitive : rend la classe `motion-reduce:animate-none` et
    `aria-hidden`.
  - Chaque composant skeleton de section : rend sa structure attendue.
  - `LoadingRegion` : expose `role="status"` et `aria-label`.
- Les loaders async (composants serveur faisant du fetch) ne sont pas unit-testés
  en isolation (limite de RTL sur les server components async) ; ils sont couverts
  par `pnpm typecheck` + `pnpm build` et une vérification manuelle du streaming.
- Non-régression : suites existantes vertes + `pnpm lint && pnpm typecheck &&
  pnpm build`.

## Découpage en plan (phasé)

Chaque phase est testable et committable seule :

1. Fondation : `Skeleton` primitive + `LoadingRegion` + a11y + tests.
2. Skeletons de section (composants purs) + tests.
3. `/profile` streaming (le gain le plus fort).
4. `/today` streaming.
5. `/stats` streaming.
6. `/history/[id]` streaming.
7. `loading.tsx` : reconstruire les 4 existants + ajouter les manquants.

## Hors périmètre

- Pas de migration de fetch vers le client (SWR/React Query) : on reste en
  server components.
- Pas de changement des requêtes Supabase ni du worker.
- `onboarding` : pas de `loading.tsx` (wizard client).

## Critère d'acceptation

- `/profile` affiche les formulaires sans attendre l'appel worker 15 s ; l'encart
  niveaux par discipline apparaît ensuite via son skeleton.
- `/today`, `/stats`, `/history/[id]` affichent leur shell immédiatement et
  streament leurs sections lentes derrière des skeletons fidèles.
- Une seule primitive `Skeleton` ; plus de `div bg-muted/animate-pulse` ad hoc.
- Toutes les routes pertinentes ont un `loading.tsx`.
- Les états de chargement exposent `role="status"` et respectent
  `prefers-reduced-motion`.
