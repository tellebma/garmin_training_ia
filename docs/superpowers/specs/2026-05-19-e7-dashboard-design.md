# E7 — Dashboard Frontend — Design

**Date** : 2026-05-19
**Statut** : Validated (brainstorm + 3-section design review with owner)
**EPIC** : E7 — Dashboard frontend
**Dépendances entrantes** : E2 (Garmin sync : activities, daily_metrics, sleep, hrv, body_composition) ✅, E3 (athlete_profiles + race_goals) ✅, E4 (training_plans + planned_sessions + Banister TSS) ✅
**Dépendances sortantes** : E5 (LLM session detail) viendra remplir `planned_sessions.notes` qui sera affiché sur `/today`. E6 (briefing quotidien) viendra enrichir `/today` avec recommendations adaptatives.
**Effort estimé** : 6.5 jours

---

## 1. Objectif

Livrer une UI complète mobile-first pour consulter le plan d'entraînement, l'état de forme (Banister CTL/ATL/TSB), les métriques Garmin et l'historique. 5 pages reliées par une navigation responsive (BottomNav mobile, SideNav desktop).

L'EPIC NE contient PAS la génération du détail des séances (E5) ni les briefings adaptatifs (E6). Le bouton "Voir détails" sur la séance du jour est un placeholder ouvert sur une future page session detail.

## 2. Critères d'acceptation

- 5 pages accessibles via la nav : `/today`, `/plan`, `/stats`, `/history`, `/profile` (existante)
- Mobile-first : aucun scroll horizontal sur viewport iPhone 12 (390×844)
- Desktop responsive (md+) : SideNav sticky + contenu max-w-7xl
- Charts via Recharts (déjà installé via shadcn add chart)
- **Pas d'emoji** dans l'UI — uniquement Lucide React icons (déjà installé), cohérent avec Strava / TrainingPeaks / Garmin Connect
- Dark mode par défaut (déjà actif sur le projet)
- Empty states sur chaque section (data manquante, sync pas encore tourné, etc.)
- Lighthouse Performance ≥ 85 sur les pages principales
- Loading states (skeleton) pour Server Components à fetch multiples

## 3. Choix structurants (issus du brainstorm)

| Sujet | Choix retenu | Alternatives écartées |
|---|---|---|
| Scope | 5 pages dès V1 (/today + /plan + /stats + /history) | 1 page enrichie seulement ; 2 pages /today + /plan |
| Chart library | Recharts (standard React, ~24M dl/mois) | Tremor (opinionated) ; shadcn/ui charts (wrapper) |
| Iconographie | Lucide React (déjà installé) | Emoji ; Heroicons |
| Banister 90j source | Nouvelle table `daily_banister_state` matérialisée par le cron | Calcul à la volée à chaque page load (90 itérations Python via worker) ; réimpl TS du modèle |
| Cache Next.js | revalidate=0 sur /today + /plan ; revalidate=300 sur /stats + /history | Tout en revalidate=0 ; tout en static |
| Navigation | BottomNav mobile + SideNav desktop | Hamburger menu seul ; tabs en haut |

YAGNI (hors scope V1) :
- Détail d'une activity (clic sur ligne /history → page `/history/[id]`) — post-MVP
- Drag-to-replan dans /plan — post-MVP
- Filtres avancés /history (durée min, distance, FC zone) — post-MVP MVP a filtres sport + période
- Comparaisons "moi vs amis" — post-MVP
- Export PDF / CSV — post-MVP
- Toggle dark/light mode manuel — dark only V1
- Notifications push — couvert par E9
- Personnalisation widgets (drag-drop sections /today) — post-MVP

## 4. Data model

### 4.1 Nouvelle table `daily_banister_state`

Calculée par le cron Garmin sync (05:00 UTC) après l'upsert des nouvelles activities. Idempotent : upsert sur (user_id, date).

```sql
create table if not exists public.daily_banister_state (
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  ctl numeric(6,2) not null check (ctl >= 0),
  atl numeric(6,2) not null check (atl >= 0),
  tsb numeric(6,2) not null,
  daily_tss numeric(6,2) check (daily_tss is null or daily_tss >= 0),
  computed_at timestamptz not null default now(),
  primary key (user_id, date)
);

create index if not exists daily_banister_user_date_idx
  on public.daily_banister_state (user_id, date desc);

alter table public.daily_banister_state enable row level security;

drop policy if exists "users read own banister" on public.daily_banister_state;
create policy "users read own banister" on public.daily_banister_state for select
  using (auth.uid() = user_id);
-- Pas de policy INSERT/UPDATE/DELETE : seul le service-role (cron worker) écrit.

comment on table public.daily_banister_state is
  'Banister CTL/ATL/TSB matérialisé par jour. Recalculé par le cron sync Garmin daily.';
```

### 4.2 Module worker `coach/state.py` (nouveau)

```python
"""Materialize daily Banister state (CTL/ATL/TSB) for fast frontend reads.

Recompute by walking the last 180 days of TSS from activities and upserting
daily_banister_state. Called at the end of run_sync_for_user after activities
have been inserted.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, cast

from garmin_sync.coach.banister import (
    compute_banister_history,
    estimate_initial_ctl_from_profile,
)
from garmin_sync.coach.tss import compute_tss
from garmin_sync.supabase_client import get_admin_client


def recompute_daily_state(user_id: str, days_back: int = 180) -> dict[str, int]:
    """Recompute CTL/ATL/TSB for the last `days_back` days and upsert.

    Returns: {"rows_upserted": int}
    """
    db = get_admin_client()
    today = date.today()
    start = today - timedelta(days=days_back)

    # Load profile for FTP/FCmax (TSS calc needs them)
    profile_resp = (
        db.table('athlete_profiles')
        .select('hours_per_week, ftp_watts, fc_max_bpm')
        .eq('user_id', user_id)
        .single()
        .execute()
    )
    profile = cast('dict[str, Any]', profile_resp.data or {})

    # Load activities in window
    activities_resp = (
        db.table('activities')
        .select('start_time, sport, duration_s, power_avg, hr_avg')
        .eq('user_id', user_id)
        .gte('start_time', start.isoformat())
        .execute()
    )
    activities = cast('list[dict[str, Any]]', activities_resp.data or [])

    # Aggregate per day
    tss_by_date: dict[date, float] = {}
    for a in activities:
        tss = compute_tss(
            duration_s=a.get('duration_s', 0),
            sport=a.get('sport', ''),
            power_avg=a.get('power_avg'),
            hr_avg=a.get('hr_avg'),
            ftp_watts=profile.get('ftp_watts'),
            fc_max_bpm=profile.get('fc_max_bpm'),
        )
        if tss is None:
            continue
        start_time_raw = a['start_time'].replace('Z', '+00:00')
        d = datetime.fromisoformat(start_time_raw).date()
        tss_by_date[d] = tss_by_date.get(d, 0.0) + tss

    # Cold-start initial CTL if <14 days of activities
    if len(tss_by_date) < 14:
        init_ctl = estimate_initial_ctl_from_profile(profile.get('hours_per_week'))
        init_atl = init_ctl
    else:
        init_ctl = 0.0
        init_atl = 0.0

    states = compute_banister_history(
        tss_by_date=tss_by_date, start=start, end=today,
        initial_ctl=init_ctl, initial_atl=init_atl,
    )

    # Upsert rows
    rows = []
    current = start
    for state in states:
        rows.append({
            'user_id': user_id,
            'date': current.isoformat(),
            'ctl': round(state.ctl, 2),
            'atl': round(state.atl, 2),
            'tsb': round(state.tsb, 2),
            'daily_tss': tss_by_date.get(current),
        })
        current += timedelta(days=1)

    if rows:
        db.table('daily_banister_state').upsert(rows, on_conflict='user_id,date').execute()

    return {'rows_upserted': len(rows)}
```

### 4.3 Hook dans `cron.py:run_sync_for_user`

À la fin de la fonction (après le sync activities + daily_metrics + ...), appel à `recompute_daily_state(user_id)` enveloppé dans un try/except (un échec ne bloque pas le sync).

## 5. Architecture frontend

### 5.1 Arborescence

```
app/(app)/
├── layout.tsx                            # MOD : intègre BottomNav + SideNav responsive
├── today/page.tsx                        # MOD : page complète au lieu du placeholder
├── plan/page.tsx                         # NEW
├── stats/page.tsx                        # NEW
├── history/page.tsx                      # NEW
├── profile/                              # déjà fait (E3)
├── loading.tsx                           # NEW global fallback skeleton
├── today/loading.tsx                     # NEW skeleton 5 sections
├── plan/loading.tsx                      # NEW
├── stats/loading.tsx                     # NEW
├── history/loading.tsx                   # NEW
└── _components/
    ├── chart-card.tsx                    # NEW : shadcn-styled Card + Recharts container
    ├── metric-tile.tsx                   # NEW : tile compacte avec icône + valeur + delta
    ├── session-card.tsx                  # NEW : affichage compact d'une planned_session
    ├── activity-row.tsx                  # NEW : ligne d'activity (history + dernière sur /today)
    ├── empty-state.tsx                   # NEW : composant réutilisable pour les vides
    ├── phase-badge.tsx                   # NEW : badge coloré selon phase
    ├── sport-icon.tsx                    # NEW : mapping sport → Lucide icon
    └── charts/
        ├── banister-chart.tsx            # NEW : LineChart CTL/ATL/TSB 90j
        ├── weekly-volume-chart.tsx       # NEW : BarChart stacked sport 12 sem
        ├── hrv-trend-chart.tsx           # NEW : LineChart HRV 30j
        └── sleep-trend-chart.tsx         # NEW : BarChart sleep score 30j

components/nav/
├── bottom-nav.tsx                        # NEW : nav mobile 5 onglets fixed
└── side-nav.tsx                          # NEW : nav desktop sticky left
```

### 5.2 Mapping sports → icônes Lucide

```typescript
// app/(app)/_components/sport-icon.tsx
import { Waves, Bike, Footprints, RotateCw, MinusCircle, Activity, Trophy } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

type Sport = 'swim' | 'bike' | 'run' | 'brick' | 'rest' | 'race'
type SessionType = 'endurance' | 'threshold' | 'intervals' | 'long' | 'recovery' | 'race' | 'rest'

export const SPORT_ICON: Record<Sport, LucideIcon> = {
  swim: Waves,
  bike: Bike,
  run: Footprints,
  brick: RotateCw,
  rest: MinusCircle,
  race: Trophy,
}

export const SPORT_LABEL: Record<Sport, string> = {
  swim: 'Natation',
  bike: 'Vélo',
  run: 'Course',
  brick: 'Brick',
  rest: 'Repos',
  race: 'Course (jour J)',
}

export const SESSION_TYPE_LABEL: Record<SessionType, string> = {
  endurance: 'Endurance',
  threshold: 'Seuil',
  intervals: 'Intervalles',
  long: 'Sortie longue',
  recovery: 'Récupération',
  race: 'Course',
  rest: 'Repos',
}

// Phase badge color (foreground via Tailwind classes)
export const PHASE_BADGE_CLASS: Record<string, string> = {
  base: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  build: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  peak: 'bg-red-500/10 text-red-600 dark:text-red-400',
  taper: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  race: 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
}
```

### 5.3 Navigation responsive

`app/(app)/layout.tsx` :

```tsx
import { BottomNav } from '@/components/nav/bottom-nav'
import { SideNav } from '@/components/nav/side-nav'
// ... existing auth/onboarding redirects ...

return (
  <div className="md:flex">
    <SideNav className="hidden md:flex" />
    <main className="flex-1 px-4 pb-20 pt-6 md:max-w-5xl md:px-8 md:pb-8">
      {children}
    </main>
    <BottomNav className="md:hidden" />
  </div>
)
```

`components/nav/bottom-nav.tsx` : 5 `<Link>` `<Home>` + label, `fixed bottom-0 inset-x-0 border-t bg-background z-40`. `usePathname()` pour highlight l'item actif.

`components/nav/side-nav.tsx` : same liens, `sticky top-0 h-screen w-56 border-r`. Logo en haut + 5 nav items + user avatar+menu en bas.

### 5.4 Data flow par page

**`/today`** (Server Component, revalidate=0) :
```typescript
const [{ data: session }, { data: bodyMetrics }, { data: banister }, { data: lastActivity }, { data: race }] =
  await Promise.all([
    supabase.from('planned_sessions').select('*').eq('user_id', uid).eq('date', today).maybeSingle(),
    supabase.from('daily_metrics').select('*, sleep:sleep!inner(*), hrv:hrv!inner(*), body:body_composition!inner(*)')
            .eq('user_id', uid).eq('date', today).maybeSingle(),
    supabase.from('daily_banister_state').select('ctl, atl, tsb, date').eq('user_id', uid)
            .gte('date', ninetyDaysAgo).order('date').limit(90),
    supabase.from('activities').select('*').eq('user_id', uid).order('start_time', { ascending: false }).limit(1).maybeSingle(),
    supabase.from('race_goals').select('race_date, name, discipline').eq('user_id', uid).eq('is_primary', true).maybeSingle(),
  ])
```

**`/plan`** (Server Component, revalidate=0) :
- Récupère `training_plans` active + `planned_sessions` du plan où `date BETWEEN week_start AND week_end`
- Query param `?week=N` pour navigation (default = semaine actuelle calculée depuis week_offset)

**`/stats`** (Server Component, revalidate=300) :
- `daily_banister_state` 90j (même que /today)
- `activities` last 84 days, agrégées par semaine ISO et par sport côté server (helper TS)
- `hrv` last 30 days
- `sleep` last 30 days

**`/history`** (Server Component, revalidate=300) :
- `activities` paginated : `?offset=0&limit=20&sport=<all|swim|bike|run>&period=<7|30|90|all>`
- Bouton "Charger plus" = `<Link href="?offset=20">` (Next.js navigation native, pas de state client)

## 6. Charts (Recharts components)

### 6.1 `<BanisterChart>` — CTL/ATL/TSB

```tsx
// app/(app)/_components/charts/banister-chart.tsx
'use client'
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'

interface Point { date: string; ctl: number; atl: number; tsb: number }

export function BanisterChart({ data }: { data: Point[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10 }} />
        <Tooltip />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="ctl" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={false} name="CTL (fitness)" />
        <Line type="monotone" dataKey="atl" stroke="hsl(var(--chart-2))" strokeWidth={2} dot={false} name="ATL (fatigue)" />
        <Line type="monotone" dataKey="tsb" stroke="hsl(var(--chart-3))" strokeWidth={2} dot={false} name="TSB (forme)" />
      </LineChart>
    </ResponsiveContainer>
  )
}
```

### 6.2 `<WeeklyVolumeChart>` — Bars stacked sport 12 sem

Données pré-agrégées côté Server Component : `[{ week: '2026-W15', swim: 90, bike: 220, run: 150 }, ...]`. Stacked BarChart, 3 séries (swim/bike/run) avec couleurs `chart-1/2/3`.

### 6.3 `<HrvTrendChart>` — HRV 30j

LineChart simple : 1 série `last_night_avg` + zone de référence "moyenne ±5ms" en fond translucide.

### 6.4 `<SleepTrendChart>` — Sleep score 30j

BarChart vertical : 1 série `score` par jour (0-100), ligne horizontale référence à 80 (target). Couleur conditionnelle : red < 60, amber 60-79, emerald ≥ 80.

### 6.5 Couleurs charts

Variables CSS injectées dans `app/globals.css` (à ajouter via le helper shadcn add chart) :

```css
:root {
  --chart-1: 220 70% 50%;  /* blue (CTL / swim) */
  --chart-2: 30 80% 55%;   /* orange (ATL / bike) */
  --chart-3: 140 60% 50%;  /* green (TSB / run) */
  --chart-4: 280 60% 50%;  /* purple */
  --chart-5: 340 70% 55%;  /* magenta */
}
.dark {
  /* mêmes hues, légèrement plus claires si besoin */
}
```

## 7. Layouts des 5 pages

Voir maquettes ASCII des sections 2.1 à 2.5 du brainstorming (sans emoji dans la version finale — toutes les icônes seront des composants Lucide React, taille uniforme `size={20}` ou Tailwind `w-5 h-5`, alignées sur `text-muted-foreground` ou `text-primary`).

Récap :
- **`/today`** : Header (date + phase badge) + Séance du jour Card + 3 MetricTile en grille + BanisterChart + Dernière activity row
- **`/plan`** : Header (nom course + J-N) + nav semaine mobile ◄► + 7 SessionCard (1 par jour de la semaine) + footer total durée/TSS
- **`/stats`** : 4 ChartCard empilés (Banister, WeeklyVolume, HrvTrend, SleepTrend)
- **`/history`** : Filtres (Select sport + Select période) + liste paginate ActivityRow + bouton "Charger plus"

## 8. Empty states

Chaque section a un fallback. Composant `<EmptyState icon={Lucide} title="..." description="...">` réutilisé.

| Page | Section | Empty state |
|---|---|---|
| /today | Séance du jour | "Pas de séance prévue aujourd'hui (jour de repos)" — si planned_sessions.session_type = 'rest' |
| /today | Séance du jour | "Ton plan n'est pas encore généré. Régénération dimanche soir 22h UTC." — si aucun training_plan active |
| /today | Métriques matin | "Données du jour pas encore synchronisées. Sync auto demain 05:00 UTC." — si daily_metrics du jour vide |
| /today | Banister chart | "Pas encore d'historique. Reviens dans 1-2 semaines." — si daily_banister_state < 14 rows |
| /today | Dernière activity | "Aucune activity synchronisée. Connecte Garmin et attends le prochain sync." |
| /plan | Liste sessions | "Plan en cours de génération..." — si training_plan active sans planned_sessions (rare) |
| /stats | Banister | "Pas d'historique" idem /today |
| /stats | Volume hebdo | "Pas encore d'activities" |
| /stats | HRV | "HRV pas dispo (montre Garmin ne supporte pas)" — si hrv table vide |
| /stats | Sleep | "Sleep pas dispo" |
| /history | Liste vide | "Aucune activity dans cette période. Élargis le filtre ou attends le prochain sync." |

## 9. Tests

| Couche | Outil | Cas couverts |
|---|---|---|
| **Worker `coach/state.py`** | pytest | (1) recompute_daily_state cold-start sans activities → ctl=initial_estimate, (2) avec 30j d'activités TSS=50 chaque jour → ctl converge, (3) idempotent (upsert), (4) handles missing profile gracefully |
| **Migration DB** | Supabase MCP verify | table créée + RLS active + 1 policy SELECT + index user_date |
| **Frontend helpers** | Vitest | (1) computeWeeklyVolume(activities, 12) regroupe par ISO week + sport, (2) formatTSS/formatDuration affichent format propre (60 TSS, 1h25, etc.), (3) phase color mapping correct |
| **Server Components data fetch** | Vitest avec mocks Supabase | (1) /today fait Promise.all des 5 queries, (2) /plan calcule week_offset depuis ?week query, (3) /history applique filters sport + period + offset |
| **Composants charts** | Vitest snapshot | Render BanisterChart avec mock data 90j → snapshot stable ; WeeklyVolumeChart avec 12 semaines |
| **Navigation responsive** | Playwright | (1) viewport 390x844 : BottomNav visible, SideNav caché, taps naviguent ; (2) viewport 1280x800 : SideNav visible, BottomNav caché ; (3) item actif highlight cohérent |
| **Empty states** | Vitest | Chaque cas listé section 8 affiche le bon message |
| **Pas d'emoji** | grep CI | `grep -r "[\U0001F300-\U0001F9FF]" app/ components/ | wc -l` = 0 (sauf docs/email-templates) |
| **Lighthouse** | CI lighthouse-action | Performance ≥ 85 sur /today, /plan, /stats |

## 10. Découpage en sous-livrables

1. **Migration DB + worker state** : `daily_banister_state` table + `coach/state.py:recompute_daily_state` + hook dans `cron.py:run_sync_for_user` + 4 tests pytest
2. **Setup charts shadcn** : `pnpm dlx shadcn add chart` + CSS variables `--chart-1` à `--chart-5` dans `globals.css`
3. **Composants partagés** : `sport-icon.tsx`, `phase-badge.tsx`, `metric-tile.tsx`, `chart-card.tsx`, `empty-state.tsx`, `session-card.tsx`, `activity-row.tsx` (7 composants, ~50 LOC chacun)
4. **4 charts Recharts** : `banister-chart.tsx`, `weekly-volume-chart.tsx`, `hrv-trend-chart.tsx`, `sleep-trend-chart.tsx`
5. **Navigation responsive** : `bottom-nav.tsx` + `side-nav.tsx` + layout `(app)/layout.tsx` update + loading.tsx global
6. **`/today` page complète** : 5 sections + loading.tsx + empty states
7. **`/plan` page** : navigation semaine mobile + grille 4 sem desktop + loading.tsx + empty states
8. **`/stats` page** : 4 charts empilés + loading.tsx + empty states (réutilise charts step 4)
9. **`/history` page** : liste paginée avec filtres + loading.tsx + empty states
10. **Smoke E2E Playwright** : viewport mobile + desktop, navigation entre les 5 pages

Ordre conseillé : 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10.

## 11. Points de vigilance

- **Recharts SSR** : composants chart sont `'use client'` car Recharts utilise `window`. Le Server Component parent fetch les données puis passe au Client Component via props sérialisables (Date.toISOString() côté server).
- **Charts dark/light** : couleurs via CSS variables `hsl(var(--chart-1))`. Tailwind dark mode déjà en place côté projet, juste vérifier la lisibilité sur les 5 charts.
- **Bundle size** : Recharts ~120 KB gzipped. Acceptable pour MVP. Si Lighthouse fail, on peut faire dynamic import par chart.
- **Données sparse** : tous les empty states listés section 8 — bien tester quand `daily_banister_state` < 14 rows (cold start) et quand l'user n'a pas connecté Garmin (pas dans le scope MVP courant mais à prévoir).
- **Performance /today** : 5 queries en parallèle via Promise.all → typiquement <500ms total. Cache désactivé (revalidate=0) car données changent à chaque sync.
- **Mobile-first impératif** : tester systématiquement sur viewport 390x844 avant chaque commit. Pas de scroll horizontal. Pas de touch target < 44x44px.
- **Pas d'emoji** : règle stricte. Si une icône manque dans Lucide, choisir le plus proche sémantiquement plutôt qu'un emoji. CI grep check pour empêcher la régression.
- **Pas d'audit cyber formel** : surface attack réduite (Server Components avec RLS owner-only, pas d'user input dynamique sauf filters /history qui sont des enum). Skip audit Red/Blue.

## 12. Effort estimé détaillé

| Sous-livrable | Effort |
|---|---|
| 1. Migration + worker state | 0.5j |
| 2. Setup charts shadcn | 0.25j |
| 3. Composants partagés | 0.75j |
| 4. 4 charts Recharts | 1j |
| 5. Navigation responsive | 0.5j |
| 6. /today page | 1j |
| 7. /plan page | 1j |
| 8. /stats page | 0.5j |
| 9. /history page | 0.5j |
| 10. Smoke E2E Playwright | 0.5j |
| **Total** | **6.5j** ✓ |

---

**Fin du spec.**

Une fois ce spec validé par l'user, on passe à `superpowers:writing-plans` pour le plan d'implémentation détaillé.
