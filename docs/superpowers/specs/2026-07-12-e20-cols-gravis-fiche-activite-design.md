# E20 — Cols gravis sur la fiche activité

**Date** : 2026-07-12
**EPIC** : E20 — Historique enrichi
**Statut** : Spec validée (design approuvé)
**Priorité** : P2

## Contexte et objectif

Depuis E9 (2026-07-08), la table `col_crossings` (migration
`20260708000000_cols_and_crossings.sql`) enregistre les franchissements de cols détectés
par le worker, **avec un `garmin_activity_id`** — donc directement liables à une activité
précise, pas seulement à un agrégat global. Aujourd'hui, ces données ne sont exploitées que
sur `/stats` via `ColsWidget` (`app/(app)/_components/cols-widget.tsx`), qui affiche la
liste des cols dans un rayon de 50 km autour du domicile, tous crossings confondus.

Objectif : sur la fiche détail d'une activité (`/history/[id]`), afficher les cols
effectivement franchis **pendant cette activité précise** (nom + altitude), en réutilisant
le vocabulaire visuel de `ColsWidget` mais scopé à une seule activité — pas une nouvelle
vue "cols" globale.

Explicitement hors scope : pas de badge sur les lignes de la liste `/history` (uniquement la
fiche détail), pas de nouvelle page.

## Décision de design

### Requête et scope des données

Nouvelle requête, filtrée par `user_id` + `garmin_activity_id` (au lieu du filtre géographique
50 km de `computeColsSummary`) :

```sql
select col_id, crossed_at, min_distance_m, cols(name, elevation_m)
from col_crossings
where user_id = :userId and garmin_activity_id = :garminActivityId
order by crossed_at asc
```

Pas de réutilisation de `computeColsSummary` (`lib/dashboard/cols.ts`) : cette fonction calcule
une distance au domicile et agrège les compteurs de franchissement sur toute la fenêtre de
sync, ce qui n'a pas de sens pour une activité unique. On écrit une fonction pure dédiée,
plus simple, dans le même fichier `lib/dashboard/cols.ts` :

```ts
export interface ActivityColCrossingDto {
  colId: string
  name: string
  elevationM: number | null
  crossedAt: string
}

export function toActivityColCrossings(
  rows: { col_id: string; crossed_at: string; cols: { name: string; elevation_m: number | null } }[]
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

### Isolation du widget (contrainte validée avec l'owner sur la feature "Mes cols")

**Ce widget ne doit pas être ajouté au `Promise.all` bloquant existant** de
`ActivityDetailBody` (`app/(app)/history/[id]/page.tsx`). Comme pour `ColsWidget` sur
`/stats`, il doit être un composant serveur async isolé avec sa propre frontière
`<Suspense>`, monté au même niveau que `ActivityDetailBody` (pas en cascade après elle),
pour que son fetch démarre en parallèle sans ralentir le reste de la page.

```tsx
// app/(app)/history/[id]/page.tsx — dans ActivityDetailPage, à côté de ActivityDetailBody
<Suspense fallback={<ActivityDetailSkeleton />}>
  <ActivityDetailBody userId={userId} activity={activity} />
</Suspense>
<Suspense fallback={<ColsGravisSkeleton />}>
  <ActivityColsGravis userId={userId} garminActivityId={activity.garmin_activity_id} />
</Suspense>
```

Nouveau composant serveur `ActivityColsGravis` (nouveau fichier
`app/(app)/_components/activity-cols-gravis.tsx`) :

```tsx
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

  const crossings = toActivityColCrossings(data ?? [])
  if (crossings.length === 0) return null // rien affiché si aucun col franchi

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

`ColsGravisSkeleton` : nouveau skeleton minimal dans
`app/(app)/_components/skeletons/`, calqué sur les skeletons existants (ex.
`activity-detail-skeleton.tsx`) — une carte avec 1-2 lignes de placeholder.

### État vide

Si `crossings.length === 0`, le composant retourne `null` (rien n'est rendu, pas de carte
vide) — conforme à la décision validée : la majorité des activités (footing, natation, home
trainer...) n'ont pas de col, la section ne doit pas polluer visuellement la fiche.

## Gestion des erreurs

| Cas | Comportement |
|---|---|
| Aucun crossing pour cette activité | `ActivityColsGravis` retourne `null` (rien affiché). |
| Requête `col_crossings` échoue (`data` = `null`) | `data ?? []` → traité comme "aucun col", pas d'exception, pas de log spécifique requis (cohérent avec le reste de la page qui ne logge pas les erreurs de lecture Supabase RLS-protégées). |
| `col.elevation_m` est `null` (donnée OSM incomplète) | Affiché `—` (même convention que `ColsWidget`). |

## Plan de tests

**`lib/dashboard/cols.test.ts`** (fichier existant, ajout de cas)
- `toActivityColCrossings([])` → `[]`.
- `toActivityColCrossings` avec plusieurs lignes → tri par `crossedAt` croissant, mapping
  correct des champs imbriqués `cols.name`/`cols.elevation_m`.
- `elevation_m: null` préservé tel quel (pas de valeur par défaut inventée).

**Test composant/page (Vitest + mock Supabase, si le pattern existe déjà pour
`ActivityDetailBody`)**
- 0 crossing → `ActivityColsGravis` ne rend rien (pas de `ChartCard "Cols gravis"` dans le DOM).
- N crossings → carte rendue avec N lignes, nom + altitude formatés.

Pas de test worker (Python) — aucune donnée nouvelle à synchroniser, uniquement lecture d'une
table déjà alimentée.

## Hors scope (YAGNI)

- Pas de badge ni d'icône sur les lignes de la liste `/history`.
- Pas de réutilisation/modification de `ColsWidget` ou `computeColsSummary` (logique
  différente : agrégat géographique global vs. franchissements d'une activité précise).
- Pas d'affichage de `min_distance_m` (précision du matching GPS) — donnée technique interne,
  pas utile à l'utilisateur final.

## Critères d'acceptation

1. Sur `/history/[id]`, si l'activité a franchi ≥1 col, une section "Cols gravis" affiche le
   nom et l'altitude de chaque col, dans l'ordre chronologique de franchissement.
2. Si l'activité n'a franchi aucun col, aucune section n'est affichée (pas de carte vide).
3. Le fetch des cols gravis ne bloque pas l'affichage du reste de la fiche activité (Suspense
   isolé, chargement en parallèle, pas ajouté au `Promise.all` de `ActivityDetailBody`).
4. Tous les quality gates passent (lint, typecheck, tests, build, coverage).
