# Race Profile v2 — Design

**Date** : 2026-05-19
**Statut** : Validated (brainstorm + 2-section design review with owner)
**EPIC** : Race Profile v2 — évolution du modèle `race_goals` pour supporter tout type de course avec dénivelé et multi-segments
**Dépendances entrantes** : E3 (Profile & Onboarding) ✅
**Dépendances sortantes** : E4 (planning Banister) consommera `legs[].distance_km`, `legs[].elevation_gain_m`, `legs[].discipline` pour calculer la TSS cible par sport
**Effort estimé** : 1 jour

---

## 1. Objectif

Remplacer le modèle actuel `race_goals` (champ enum `race_distance` mono-discipline) par un modèle riche qui capture :

- **Tout type de course** : triathlon, duathlon, aquathlon, course pied (route ou trail), vélo seul, natation seule, ou autre custom.
- **Le profil géométrique complet** : distance + dénivelé positif **par segment**, pas seulement la distance globale.
- **La séquence des segments** : pour les disciplines multi-leg (triathlon = swim → bike → run).

**Cas concret de l'owner** :
- Triathlon de la Madeleine : 1.4 / 53 / 8 km avec D+ 0 / 2200 / 200 m → modèle riche capture le profil "court mais vallonné" qui change drastiquement le coaching.
- Trail 25 km / 1000 D+ vs course route 25 km / 300 D+ : même distance, charge d'entraînement très différente. Le modèle doit refléter ça pour que E4 (Banister) calcule la bonne TSS course.

## 2. Critères d'acceptation

- L'user peut choisir une discipline parent parmi `triathlon | duathlon | aquathlon | run | bike | swim | autre`.
- Le formulaire auto-génère les segments selon les règles fixes (triathlon → 3 legs swim/bike/run dans cet ordre, etc.).
- Pour `autre`, l'user peut ajouter/retirer librement entre 1 et 10 segments.
- Chaque segment capture : distance (km, > 0) + dénivelé positif (m, ≥ 0) + discipline (`swim | bike | run`).
- Les totaux (`total_distance_km`, `total_elevation_gain_m`) sont calculés automatiquement à partir des legs et stockés en DB pour query rapide.
- La distinction trail vs route est **portée par `elevation_gain_m`** (pas un champ catégoriel séparé) — cohérent avec FFA/ITRA/Strava et avec les besoins continus de E4.
- Migration breaking — la table `race_goals` est actuellement vide en prod (aucune race insérée depuis le merge E3), donc pas de migration de données nécessaire.

## 3. Choix structurants (issus du brainstorm)

| Sujet | Choix retenu | Alternatives écartées |
|---|---|---|
| Stockage segments | `legs jsonb` dans `race_goals` | Table `race_legs` normalisée |
| Temps cible | Global uniquement | Global + par segment ; pas de temps |
| Trail vs route | Distingué par `elevation_gain_m` (champ continu) | Enum séparé `trail` |
| Totaux | Stockés en colonnes matérialisées + recalcul Server Action | Calcul on-the-fly via SQL aggregate |
| `autre` (custom) | 1-10 legs libres avec disciplines `swim/bike/run` | Discipline `xxx` libre — YAGNI |

YAGNI (volontairement hors scope, à revoir post-MVP) :

- Temps cible par segment (utile pour pacing fin — E4 ou post-MVP)
- Coureur cible / qualification (Boston, IM Kona) — pas pertinent MVP
- Terrain (asphalte / chemin / sable / neige) — `elevation_gain_m` couvre 90% du besoin
- Météo prévisionnelle pré-course — couvert par E8 (parcours géolocalisés)
- Discipline custom non-swim/bike/run (ex: ski, kayak) — `autre` + commentaire dans `name` suffit MVP

## 4. Data model

### 4.1 Migration `20260519100000_race_profile_v2.sql`

```sql
-- Drop ancien check (enum mono-discipline)
alter table public.race_goals drop constraint if exists race_goals_race_distance_check;

-- Rename colonne en parent discipline
alter table public.race_goals rename column race_distance to discipline;

-- Nouveau check sur disciplines parent
alter table public.race_goals
  add constraint race_goals_discipline_check
  check (discipline in ('triathlon','duathlon','aquathlon','run','bike','swim','autre'));

-- Colonnes nouvelles pour le profil géométrique
alter table public.race_goals
  add column if not exists total_distance_km numeric(7,2)
    check (total_distance_km is null or (total_distance_km > 0 and total_distance_km <= 1000)),
  add column if not exists total_elevation_gain_m integer
    check (total_elevation_gain_m is null or (total_elevation_gain_m >= 0 and total_elevation_gain_m <= 20000)),
  add column if not exists legs jsonb not null default '[]'::jsonb;

comment on column public.race_goals.discipline is
  'Type de course parent : triathlon, duathlon, aquathlon, run, bike, swim, autre.';
comment on column public.race_goals.total_distance_km is
  'Distance totale en km (somme des legs, mise en cache pour query rapide).';
comment on column public.race_goals.total_elevation_gain_m is
  'Dénivelé positif total en mètres (somme des legs, mise en cache).';
comment on column public.race_goals.legs is
  'Détail des segments : [{order:int, discipline:swim|bike|run, distance_km:number, elevation_gain_m:int}].';
```

### 4.2 Structure `legs` jsonb

```typescript
type Leg = {
  order: number              // 1-indexed, séquentiel
  discipline: 'swim' | 'bike' | 'run'
  distance_km: number        // > 0, ≤ 1000
  elevation_gain_m: number   // ≥ 0, ≤ 20000
}
```

### 4.3 Règles invariantes par discipline parent

| Parent | Nb legs | Séquence imposée |
|---|---|---|
| `triathlon` | exactement 3 | swim → bike → run |
| `duathlon` | exactement 3 | run → bike → run |
| `aquathlon` | exactement 2 | swim → run |
| `run` | exactement 1 | run (couvre route + trail, distingués par `elevation_gain_m`) |
| `bike` | exactement 1 | bike |
| `swim` | exactement 1 | swim |
| `autre` | 1 à 10 | libre |

### 4.4 Totaux matérialisés

`total_distance_km` et `total_elevation_gain_m` sont **dérivés** de `legs` mais stockés en colonnes pour permettre tri/filtre rapide (ex: "prochaine course avec plus de 1000 m D+"). Recalcul côté Server Action à chaque upsert via le helper TS `computeTotals(legs)`.

Choix d'implémentation : pas de trigger Postgres (recalcul côté app suffit, plus simple à tester, cohérent avec le pattern existant — sports_strengths jsonb dans athlete_profiles).

### 4.5 Exemples concrets

**Triathlon Madeleine (cas de l'owner)** :
```json
{
  "discipline": "triathlon",
  "name": "Triathlon de la Madeleine",
  "location": "La Madeleine, FR",
  "race_date": "2026-09-12",
  "target_time_seconds": 19800,
  "total_distance_km": 62.4,
  "total_elevation_gain_m": 2400,
  "legs": [
    {"order": 1, "discipline": "swim", "distance_km": 1.4, "elevation_gain_m": 0},
    {"order": 2, "discipline": "bike", "distance_km": 53,  "elevation_gain_m": 2200},
    {"order": 3, "discipline": "run",  "distance_km": 8,   "elevation_gain_m": 200}
  ]
}
```

**Trail 25 km / 1000 D+** :
```json
{
  "discipline": "run",
  "race_date": "...",
  "total_distance_km": 25,
  "total_elevation_gain_m": 1000,
  "legs": [
    {"order": 1, "discipline": "run", "distance_km": 25, "elevation_gain_m": 1000}
  ]
}
```

**Course route 25 km / 300 D+** :
```json
{
  "discipline": "run",
  "race_date": "...",
  "total_distance_km": 25,
  "total_elevation_gain_m": 300,
  "legs": [
    {"order": 1, "discipline": "run", "distance_km": 25, "elevation_gain_m": 300}
  ]
}
```

Même `discipline = run`, profil très différent → E4 calculera des TSS très différentes.

## 5. Validation Zod (`lib/onboarding/schemas.ts` — refactor)

```typescript
export const PARENT_DISCIPLINES = ['triathlon','duathlon','aquathlon','run','bike','swim','autre'] as const
export const LEG_DISCIPLINES = ['swim','bike','run'] as const

const legSchema = z.object({
  order: z.number().int().min(1).max(10),
  discipline: z.enum(LEG_DISCIPLINES),
  distance_km: z.number().positive().max(1000),
  elevation_gain_m: z.number().int().min(0).max(20000),
})

type ParentRule = { count: number | [number, number]; sequence?: readonly (typeof LEG_DISCIPLINES[number])[] }

export const LEG_RULES: Record<typeof PARENT_DISCIPLINES[number], ParentRule> = {
  triathlon:  { count: 3, sequence: ['swim','bike','run'] },
  duathlon:   { count: 3, sequence: ['run','bike','run'] },
  aquathlon:  { count: 2, sequence: ['swim','run'] },
  run:        { count: 1, sequence: ['run'] },
  bike:       { count: 1, sequence: ['bike'] },
  swim:       { count: 1, sequence: ['swim'] },
  autre:      { count: [1, 10] },
}

export const raceSchema = z.object({
  race_date: dateIsoString.refine((d) => new Date(d) > new Date(), 'La date doit être future'),
  discipline: z.enum(PARENT_DISCIPLINES),
  name: z.string().trim().max(160).optional(),
  location: z.string().trim().max(160).optional(),
  target_time_seconds: z.number().int().min(600).max(86400).optional(),
  legs: z.array(legSchema).min(1).max(10),
}).superRefine((data, ctx) => {
  const rule = LEG_RULES[data.discipline]
  if (typeof rule.count === 'number' && data.legs.length !== rule.count) {
    ctx.addIssue({ code: 'custom', path: ['legs'], message: `${data.discipline} demande exactement ${rule.count} segment(s)` })
  }
  if (Array.isArray(rule.count)) {
    const [min, max] = rule.count
    if (data.legs.length < min || data.legs.length > max) {
      ctx.addIssue({ code: 'custom', path: ['legs'], message: `Entre ${min} et ${max} segments` })
    }
  }
  if (rule.sequence) {
    rule.sequence.forEach((expectedDisc, i) => {
      if (data.legs[i]?.discipline !== expectedDisc) {
        ctx.addIssue({ code: 'custom', path: ['legs', i, 'discipline'], message: `Le segment ${i+1} doit être ${expectedDisc}` })
      }
    })
  }
  data.legs.forEach((leg, i) => {
    if (leg.order !== i + 1) {
      ctx.addIssue({ code: 'custom', path: ['legs', i, 'order'], message: `Order doit être ${i+1}` })
    }
  })
})

export function computeTotals(legs: z.infer<typeof legSchema>[]): { total_distance_km: number; total_elevation_gain_m: number } {
  return {
    total_distance_km: Math.round(legs.reduce((s, l) => s + l.distance_km, 0) * 100) / 100,
    total_elevation_gain_m: legs.reduce((s, l) => s + l.elevation_gain_m, 0),
  }
}
```

## 6. UI

### 6.1 `step-race-form.tsx` (wizard onboarding étape 2)

**Comportement** :
- Champ `discipline` (select) — au change, les `legs` sont auto-générés selon `LEG_RULES.sequence` avec `distance_km = 0, elevation_gain_m = 0` (l'user remplit).
- Pour `autre` : 2 boutons `[+ Ajouter un segment]` et `[- Retirer]` à chaque ligne ; le user peut choisir le discipline de chaque leg (`swim | bike | run`).
- Pour les autres parents : le discipline de chaque leg est figé (read-only ou affiché en label avec icône).
- Bandeau "Total" sous les legs : `Total : 62.4 km · 2400 m D+` recalculé en live à chaque keystroke.
- Le bouton "Suivant" est désactivé tant que le `safeParse(raceSchema)` échoue côté client.

**Maquette UX** :

```
Course cible

Date          : [2026-09-12]
Type          : [Triathlon         ▼]
Nom (option)  : [Triathlon Madeleine]
Lieu (option) : [La Madeleine, FR]
Temps cible   : [05:30:00]  (hh:mm:ss)

────────────────────────────────────────
Segments (3 requis pour Triathlon)

 1. 🏊 Natation
   Distance : [1.4] km   D+ : [0]    m

 2. 🚴 Vélo
   Distance : [53]  km   D+ : [2200] m

 3. 🏃 Course
   Distance : [8]   km   D+ : [200]  m

Total : 62.4 km · 2400 m D+

         [ Suivant ]
```

Pour `autre`, ajouter un select de discipline par leg + boutons add/remove.

### 6.2 `race-edit-form.tsx` (`/profile` section Course)

**Mode `view`** (par défaut) :
```
🏃 Triathlon Madeleine · 2026-09-12
   🏊 1.4 km · 0 m  →  🚴 53 km · 2200 m  →  🏃 8 km · 200 m
   Total : 62.4 km · 2400 m D+  ·  Cible : 05:30:00
                                          [Modifier]
```

**Mode `edit`** : même structure que le wizard form, avec boutons `[Enregistrer]` `[Annuler]`.

## 7. Server Action update

`app/(app)/onboarding/actions.ts:saveStepRace` :

```typescript
const { total_distance_km, total_elevation_gain_m } = computeTotals(parsed.data.legs)
const payload = {
  user_id: userIdOrErr,
  race_date: parsed.data.race_date,
  discipline: parsed.data.discipline,
  name: parsed.data.name ?? null,
  location: parsed.data.location ?? null,
  target_time_seconds: parsed.data.target_time_seconds ?? null,
  legs: parsed.data.legs,
  total_distance_km,
  total_elevation_gain_m,
  is_primary: true,
}
// upsert (insert si pas de primary existant, sinon update) — pattern inchangé de E3
```

## 8. Tests

| Couche | Outil | Cas couverts |
|---|---|---|
| **Zod legs** | Vitest | distance ≤ 0 → fail ; distance > 1000 → fail ; D+ < 0 → fail ; D+ > 20000 → fail |
| **Zod parent rules** | Vitest | triathlon avec 2 legs → fail ; triathlon avec sequence [bike,swim,run] → fail ; run avec leg `bike` → fail ; autre avec 4 legs mixtes → OK ; autre avec 11 legs → fail |
| **Zod orders** | Vitest | orders non-séquentiels → fail (ex: [1,3,4]) |
| **`computeTotals`** | Vitest | Triathlon Madeleine → (62.4, 2400) ; trail 25/1000 ; somme arrondie à 2 décimales |
| **Server Action `saveStepRace`** | Vitest + mocks | upsert calcule bien les totals avant write ; insert primary si absent ; update si existant |
| **UI manuel post-merge** | — | Wizard step 2 : sélectionner triathlon → 3 cards swim/bike/run apparaissent ; tester `autre` : add/remove leg fonctionne ; total live OK ; Suivant bloqué si distance vide |
| **Migration DB** | Supabase MCP | colonnes `discipline / total_* / legs` créées ; check `discipline_check` actif ; check sur bornes `total_distance_km` actif |

## 9. Découpage en sous-livrables (input du plan)

1. **Migration DB** — `20260519100000_race_profile_v2.sql` : drop check race_distance, rename `race_distance → discipline`, alter check, add `total_distance_km` / `total_elevation_gain_m` / `legs`. Vérif via Supabase MCP.
2. **Zod schemas refactor** — `LEG_RULES`, `legSchema`, `raceSchema` (superRefine), `computeTotals` helper + tests Vitest (~12 tests).
3. **Server Action `saveStepRace`** — recalcul totals avant upsert + tests Vitest avec mocks.
4. **UI `step-race-form.tsx`** — refactor : select discipline → auto-génère legs, inputs distance/D+ par leg, totals live, support `autre` (add/remove leg + select discipline par leg).
5. **UI `race-edit-form.tsx`** — même structure que le wizard form, mode view affichant les legs en chevron compact.
6. **Quality gates + push + PR**.

Ordre conseillé : 1 → 2 → 3 → 4 → 5 → 6.

## 10. Points de vigilance

- **Breaking migration** : la table `race_goals` est actuellement vide en prod (vérifié par owner — pas de races insérées depuis le merge E3). On rename `race_distance → discipline` sans backfill nécessaire. Si une race était insérée entre maintenant et le merge de cet EPIC, elle se ferait écraser par la rename — donc à mergeur dans une fenêtre sans utilisation.
- **`autre` discipline parent** : volontairement limité aux disciplines de leg `swim/bike/run` même pour `autre`. Si l'user veut un swimrun (suite swim/run/swim/run/...), c'est faisable via `autre` + 4-6 legs alternés. Si un sport hors swim/bike/run (ski, kayak, etc.) → mettre dans `name` text libre, `discipline = autre`, le leg en `run` par défaut.
- **Cache des totals** : si l'user modifie un leg via une route directe SQL (ex: Studio), les `total_*` deviennent obsolètes. Acceptable en MVP — la seule surface d'écriture est la Server Action `saveStepRace` qui recalcule à chaque fois.
- **Migration vs E-Auth EPIC** : cette EPIC est indépendante de E-Auth. Si on merge E-Auth d'abord puis Race Profile, ou l'inverse, l'ordre n'a pas d'importance.
- **E4 (Banister) dépendance** : E4 consommera `legs[].discipline + distance_km + elevation_gain_m` pour calculer la TSS cible par sport. Le modèle proposé ici est exactement ce dont E4 aura besoin.

---

**Fin du spec.**

Une fois ce spec validé par le user, on passe à `superpowers:writing-plans`.
