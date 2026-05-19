# E4 — Moteur de planification Banister — Design

**Date** : 2026-05-19
**Statut** : Validated (brainstorm + 3-section design review with owner)
**EPIC** : E4 — Moteur de planification (algo Banister)
**Dépendances entrantes** : E2 (Garmin sync, table `activities`) ✅, E3 (Profile & Onboarding, table `athlete_profiles`) ✅, RaceProfile v2 (table `race_goals` avec legs + total_distance_km + total_elevation_gain_m) ✅
**Dépendances sortantes** : E5 (génération séances LLM) consommera `planned_sessions` pour générer le contenu détaillé des séances. E6 (briefing quotidien) lit `planned_sessions.date = today`. E7 (dashboard) affiche la vue semaine.
**Effort estimé** : 6.5 jours

---

## 1. Objectif

Générer automatiquement un plan d'entraînement triathlon (ou autre discipline supportée par RaceProfile v2) périodisé à partir du profil de l'athlète et de sa course cible, en utilisant le **modèle Banister** (CTL/ATL/TSB) pour calibrer la charge progressive.

Le plan généré est un **squelette structurel** : pour chaque jour entre aujourd'hui et la date de course, une `planned_session` est insérée avec sport, type d'effort (endurance/threshold/intervals/long/recovery), durée cible et TSS cible. Le **contenu détaillé** de chaque séance (intervalles précis, allure, coaching notes) sera généré ultérieurement par E5 (LLM Claude Sonnet).

## 2. Critères d'acceptation

- À partir d'un profil + race_goal actif, le moteur génère 8-12 semaines de plan en moins de 5 secondes.
- La charge hebdo (TSS cumulé) progresse de manière monotone avec une semaine de deload (-30%) tous les 4ème semaine.
- La phase taper réduit le volume de 40-50% sur les 10 derniers jours avant la course.
- Le sport déclaré "faible" (`sports_strengths` score 1-2) reçoit un volume hebdo augmenté de ~20%, le sport "fort" (4-5) diminué de ~10%.
- Pas 2 séances "hard" (`threshold`, `intervals`) consécutives sur des jours adjacents.
- Le plan respecte `available_days` (de `athlete_profiles`).
- Génération initiale automatique à la fin de l'onboarding E3 (Server Action `finalizeOnboarding`).
- Régénération automatique chaque dimanche 22h UTC via cron systemd UNRAID (recalcul CTL/ATL avec activities récentes).

## 3. Choix structurants (issus du brainstorm)

| Sujet | Choix retenu | Alternatives écartées |
|---|---|---|
| Niveau d'algo | Full Banister CTL/ATL/TSB dès V1 | Rule-based seulement ; rule-based + flag Banister flippable plus tard |
| Trigger génération | Auto au finalize E3 + cron weekly | Bouton manuel seulement |
| Granularité output | Daily (1 row par jour) | Weekly summary |
| Calcul TSS | Power-based pour cycling avec watts, hrTSS sinon, fallback duration-only | Tous hrTSS ; estimation grossière par sport |
| Stockage | 2 tables (`training_plans` + `planned_sessions`) | 1 table dénormalisée ; 3 tables avec `planned_weeks` |
| UI | Hors scope E4 (E6 briefing + E7 dashboard) | Inclure vue plan dans cette EPIC |

YAGNI (hors scope E4, à revoir post-MVP) :

- Audit log des régénérations
- Multi-plan (plusieurs race_goals simultanés)
- Estimation power-based précise (NP via moyenne quadratique 30s) — on utilise `power_avg` approx, suffisant MVP
- Force-recovery quand TSB devient trop négatif au runtime (à voir avec adaptive plan post-MVP)
- Personnalisation des constantes Banister (τ1=42, τ2=7 hardcodés)
- Bouton "Régénérer mon plan" manuel sur /profile — peut être ajouté facilement post-MVP

## 4. Data model

### 4.1 Migration `20260520000000_e4_training_plans.sql`

```sql
-- =========================================
-- Table: training_plans
-- 1 plan ACTIF par user par race_goal (unique partial index)
-- =========================================
create table if not exists public.training_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  race_goal_id uuid not null references public.race_goals(id) on delete cascade,
  generated_at timestamptz not null default now(),
  start_date date not null,
  end_date date not null,
  weeks_count integer not null check (weeks_count between 1 and 52),
  ctl_initial numeric(6,2) check (ctl_initial is null or ctl_initial >= 0),
  atl_initial numeric(6,2) check (atl_initial is null or atl_initial >= 0),
  tsb_initial numeric(6,2),
  status text not null default 'active' check (status in ('active','archived')),
  params jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index training_plans_active_per_user_per_race
  on public.training_plans (user_id, race_goal_id) where status = 'active';
create index training_plans_user_status_idx
  on public.training_plans (user_id, status);

alter table public.training_plans enable row level security;

create policy "users read own plans"   on public.training_plans for select
  using (auth.uid() = user_id);
create policy "users insert own plans" on public.training_plans for insert
  with check (auth.uid() = user_id);
create policy "users update own plans" on public.training_plans for update
  using (auth.uid() = user_id);
create policy "users delete own plans" on public.training_plans for delete
  using (auth.uid() = user_id);

-- =========================================
-- Table: planned_sessions
-- 1 row par jour du plan
-- =========================================
create table if not exists public.planned_sessions (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.training_plans(id) on delete cascade,
  user_id uuid not null,
  date date not null,
  sport text not null check (sport in ('swim','bike','run','brick','rest')),
  session_type text not null check (session_type in (
    'endurance','threshold','intervals','long','recovery','race','rest'
  )),
  target_duration_s integer check (target_duration_s is null or (target_duration_s >= 0 and target_duration_s <= 36000)),
  target_tss numeric(5,2) check (target_tss is null or target_tss >= 0),
  phase text not null check (phase in ('base','build','peak','taper','race')),
  week_offset integer not null check (week_offset >= 0),
  notes text,
  created_at timestamptz not null default now()
);

create index planned_sessions_user_date_idx
  on public.planned_sessions (user_id, date);
create index planned_sessions_plan_idx
  on public.planned_sessions (plan_id);

alter table public.planned_sessions enable row level security;

create policy "users read own sessions"   on public.planned_sessions for select
  using (auth.uid() = user_id);
create policy "users insert own sessions" on public.planned_sessions for insert
  with check (auth.uid() = user_id);
create policy "users update own sessions" on public.planned_sessions for update
  using (auth.uid() = user_id);
create policy "users delete own sessions" on public.planned_sessions for delete
  using (auth.uid() = user_id);

comment on table public.training_plans is
  'Plans périodisés générés par le moteur Banister. 1 active par (user, race).';
comment on table public.planned_sessions is
  'Sessions structurelles (sport, type, durée, TSS). Contenu détaillé E5 (LLM).';
comment on column public.planned_sessions.notes is
  'Notes libres remplies par E5 (génération LLM). Vide à la génération E4.';
```

## 5. Architecture worker

### 5.1 Arborescence

```
worker/src/garmin_sync/
├── coach/                          # NEW MODULE
│   ├── __init__.py
│   ├── tss.py                      # compute_tss(activity, ftp, fcmax) -> float | None
│   ├── banister.py                 # compute_banister_history + estimate_initial_ctl_from_profile
│   ├── phases.py                   # compute_phases(start, race_date) -> [(week_offset, phase)]
│   ├── planner.py                  # generate_plan(user_id) — orchestrateur
│   ├── backfill_tss.py             # Script one-shot pour calculer TSS sur activities existantes
│   └── cron.py                     # Entry point cron weekly (régénère pour tous users actifs)
├── main.py                         # MOD : nouveau endpoint POST /coach/generate-plan
├── transformers/
│   └── activities.py               # MOD : compute_tss appelé dans le transform
```

### 5.2 Endpoint FastAPI

```python
# Dans main.py, après les endpoints garmin/*

@app.post("/coach/generate-plan")
def coach_generate_plan(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.coach.planner import generate_plan
        return generate_plan(user_id)
    except Exception as e:
        error_id = _new_error_id()
        log.exception("[%s] coach_generate_plan crashed for user=%s", error_id, user_id)
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }
```

### 5.3 Flow génération initiale (depuis E3)

```
[Server Action finalizeOnboarding — après set onboarding_completed_at en DB]
  ↓
[await fetch worker /coach/generate-plan]   ← workerPost avec user JWT
  ↓
[Worker FastAPI POST /coach/generate-plan]
  1. _require_user_jwt → user_id
  2. Load athlete_profile + active race_goal (is_primary=true)
  3. Load activities depuis (today - 180j) → calculate TSS each → tss_by_date dict
  4. Compute initial CTL/ATL via banister.compute_banister_history (avec cold-start si historique vide)
  5. phases.compute_phases(today, race_date) → list of (week_offset, phase)
  6. planner.generate_sessions(profile, race, phases, ctl_today) → list of planned_sessions
  7. SQL transaction :
     - update training_plans set status='archived' where user_id=X and race_goal_id=Y and status='active'
     - insert training_plans (id=new_plan_id, ctl_initial, atl_initial, ...) -> ON CONFLICT do nothing
     - delete planned_sessions where plan_id in (archived old)  -- cleanup
     - bulk insert planned_sessions[] with plan_id=new_plan_id
  8. Return { status: 'ok', plan_id, weeks_count, sessions_count, ctl_initial }
```

### 5.4 Flow cron weekly

```
[systemd timer dimanche 22:00 UTC sur UNRAID]
  ↓
[docker exec garmin-sync python -m garmin_sync.coach.cron]
  1. db.from('athlete_profiles').select('user_id').join(race_goals, where is_primary and race_date > now)
  2. Pour chaque user_id : appeler generate_plan(user_id) (même fonction que le endpoint, mais ici via service-role pas user JWT)
  3. Log : N users updated, M plans archivés, P sessions générées
```

Le module `coach/cron.py` réutilise `generate_plan(user_id)` du module `planner.py` — pas de duplication.

## 6. Algorithme Banister + calcul TSS

### 6.1 Calcul TSS (`coach/tss.py`)

Stratégie 2-tier :

```python
def compute_tss(
    *,
    duration_s: int,
    sport: str,
    power_avg: int | None,
    hr_avg: int | None,
    ftp_watts: int | None,
    fc_max_bpm: int | None,
) -> float | None:
    """Compute training stress score for one activity.

    Tier 1 (most precise) : cycling with power-meter + FTP known
        TSS = (duration_s × IF² × 100) / 3600   where IF = power_avg / FTP

    Tier 2 (hrTSS) : any sport with HR + FCmax known
        hrTSS = (duration_h) × IF² × 100   where IF = hr_avg / LTHR, LTHR ≈ 0.90 × FCmax

    Tier 3 (fallback) : duration only
        estTSS = duration_h × 50   (50 TSS/h endurance avg)
    """
    duration_h = duration_s / 3600
    if duration_h <= 0:
        return None

    # Tier 1 — cycling with power
    if sport in ('cycling', 'indoor_cycling', 'mountain_biking') and power_avg and ftp_watts:
        intensity_factor = power_avg / ftp_watts
        return round(duration_h * intensity_factor**2 * 100, 2)

    # Tier 2 — hrTSS
    if hr_avg and fc_max_bpm:
        lthr = fc_max_bpm * 0.90
        intensity_factor = hr_avg / lthr
        return round(duration_h * intensity_factor**2 * 100, 2)

    # Tier 3 — fallback
    return round(duration_h * 50, 2)
```

**Backfill** : un script `backfill_tss.py` itère toutes les activities avec `tss IS NULL`, calcule, update batch. Idempotent. Lancé manuellement après déploiement E4.

**Ongoing** : `transformers/activities.py:transform_activity` appelle `compute_tss` pendant le sync Garmin (le transformer prend désormais `ftp_watts` et `fc_max_bpm` en argument, à fetch dans `sync.py`).

### 6.2 Modèle Banister (`coach/banister.py`)

```python
from datetime import date, timedelta
from dataclasses import dataclass

CTL_TAU = 42  # days — fitness time constant
ATL_TAU = 7   # days — fatigue time constant

@dataclass
class BanisterState:
    ctl: float
    atl: float
    tsb: float   # tsb = ctl - atl

def compute_banister_history(
    tss_by_date: dict[date, float],
    start: date,
    end: date,
    initial_ctl: float = 0.0,
    initial_atl: float = 0.0,
) -> list[BanisterState]:
    """Iterate day-by-day from start to end inclusive. Days with no TSS = 0."""
    states: list[BanisterState] = []
    ctl, atl = initial_ctl, initial_atl
    current = start
    while current <= end:
        tss = tss_by_date.get(current, 0.0)
        ctl += (tss - ctl) / CTL_TAU
        atl += (tss - atl) / ATL_TAU
        states.append(BanisterState(ctl=ctl, atl=atl, tsb=ctl - atl))
        current += timedelta(days=1)
    return states

def estimate_initial_ctl_from_profile(hours_per_week: int | None) -> float:
    """Cold-start estimate when no historical TSS available (fresh user)."""
    if not hours_per_week or hours_per_week <= 0:
        return 0.0
    weekly_tss = hours_per_week * 50  # ~50 TSS/h endurance avg
    return round(weekly_tss / 7, 2)   # daily-equivalent baseline
```

Pour la cold-start : si `len(tss_by_date) < 14` (moins de 2 semaines d'activités), on utilise `estimate_initial_ctl_from_profile(hours_per_week)` comme `initial_ctl` et même valeur pour `initial_atl`. Sinon, démarrer à `0, 0` et laisser le calcul exponentiel converger sur les 180 jours d'historique.

### 6.3 Phases (`coach/phases.py`)

Backward planning depuis race_date :

| Phase | Ratio % | Durée typique (12 sem.) |
|---|---|---|
| `base` | 50-60% | 6-7 sem. |
| `build` | 25-30% | 3-4 sem. |
| `peak` | 10-15% | 1-2 sem. |
| `taper` | 1-2 dernières semaines | 10-14 jours |

```python
def compute_phases(start_date: date, race_date: date) -> list[tuple[int, str]]:
    """Return [(week_offset, phase), ...] from start (week 0) to race week."""
    total_weeks = max(1, (race_date - start_date).days // 7)
    taper_weeks = 1 if total_weeks < 8 else 2
    peak_weeks = max(1, total_weeks // 8) if total_weeks >= 6 else 0
    build_weeks = max(2, total_weeks // 4) if total_weeks >= 6 else max(1, total_weeks // 3)
    base_weeks = max(0, total_weeks - taper_weeks - peak_weeks - build_weeks)

    phases: list[tuple[int, str]] = []
    for w in range(total_weeks):
        if w < base_weeks:
            phase = 'base'
        elif w < base_weeks + build_weeks:
            phase = 'build'
        elif w < total_weeks - taper_weeks:
            phase = 'peak'
        else:
            phase = 'taper'
        phases.append((w, phase))
    return phases
```

### 6.4 Génération sessions (`coach/planner.py`)

Pour chaque semaine du plan :

1. **TSS cible hebdo** :
   - Base : `weekly_tss_target = ctl_today × 7 × ramp_rate`
   - `ramp_rate` : 1.05 (semaines normales), 0.7 (4ème semaine = deload), 1.0 (peak), 0.55 (taper)
2. **Répartir entre sports** selon `sports_strengths` :
   - Pour chaque sport `s` dans la discipline (depuis race_goal.legs[].discipline) :
     - `base_share = 1.0 / nb_disciplines_in_race`
     - Modifier : score 1-2 → `+20%` ; score 4-5 → `-10%`
     - Normaliser pour que somme = 100%
   - Multiplier par `weekly_tss_target` → TSS cible par sport pour la semaine
3. **Pour chaque sport, sélectionner N séances selon la phase** :
   - **Base** : `endurance` + `long` + `recovery`
   - **Build** : `endurance` + `threshold` + `long`
   - **Peak** : `intervals` + `endurance` + `long`
   - **Taper** : `endurance` (court) + `race` (short, à -2j de la course)
4. **Placer sur `available_days`** avec règles :
   - Pas 2 séances `hard` (threshold/intervals) consécutives
   - Long → dimanche par défaut (si dimanche dans available_days)
   - Recovery → lundi/jeudi (lendemain de jour hard)
   - **Race day** = `race_goal.race_date` avec `session_type='race'`, `sport` = discipline du 1er leg (`race_goal.legs[0].discipline` → 'swim' pour triathlon, 'run' pour trail, 'bike' pour vélo, etc.). Pas de target_duration_s/target_tss (la course elle-même est l'effort, indéterminé).
   - Jours non-available → `session_type='rest'`, `sport='rest'`, `target_duration_s=0`, `target_tss=0`

Output : liste de `dict` représentant chaque `planned_sessions` row.

## 7. Tests

| Module | Cas couverts |
|---|---|
| **`tss.compute_tss`** | (1) cycling avec power+FTP → pwTSS formule correcte, (2) HR seul → hrTSS correct, (3) duration only fallback (50 TSS/h), (4) duration <= 0 → None, (5) ratio LTHR/FCmax = 0.90 vérifié |
| **`banister.compute_banister_history`** | (1) 0 TSS sur 42j → CTL et ATL décroissent exponentiellement vers 0, (2) TSS=100 chaque jour pendant 200j → CTL converge vers 100, (3) start=end → 1 state, (4) initial_ctl/atl honorés, (5) gaps in tss_by_date traités comme 0 |
| **`banister.estimate_initial_ctl_from_profile`** | hours=8 → ~57 ; None → 0 ; hours=30 → cap raisonnable |
| **`phases.compute_phases`** | (1) 12 sem. → 6-7 base + 3 build + 1 peak + 2 taper, (2) 8 sem. → moins de base, (3) 4 sem. → minimum 1 taper, (4) 1 sem. → 1 taper only |
| **`planner.generate_plan`** | (1) sports_strengths low swim → +20% volume swim, (2) chaque 4ème sem. = deload (TSS hebdo ≈ 70% normal), (3) taper réduit 40-50% volume, (4) pas 2 hard consécutifs, (5) respect available_days, (6) total weeks_count = (race_date - today) // 7, (7) cold-start avec 0 activities OK, (8) sessions count = total_weeks × ~5-6 par semaine |
| **Migration DB** | tables créées + RLS active + unique partial index `active_per_user_per_race` empêche 2 plans actifs même race |
| **Endpoint `POST /coach/generate-plan`** | (1) JWT requis, (2) sans race_goal → status `no_race_goal`, (3) happy path → status ok + plan_id, (4) régénération archive l'ancien |
| **Backfill TSS** | activities avec tss=null sont updated ; activities avec tss déjà set sont skipped (idempotent) |

## 8. Découpage en sous-livrables

1. **Migration DB** — 2 tables + RLS + indexes via `mcp__supabase__apply_migration`
2. **`coach/tss.py`** + 5 tests
3. **`coach/banister.py`** + 6 tests
4. **`coach/phases.py`** + 5 tests
5. **`coach/planner.py`** + 8 tests (consomme 2, 3, 4)
6. **Worker integration** :
   - Update `transformers/activities.py` : appel `compute_tss` (passer FTP/FCmax via signature)
   - Update `sync.py` : fetch FTP/FCmax depuis `athlete_profiles` avant transformer
   - Nouveau `coach/backfill_tss.py` (script standalone) + test
   - Nouveau endpoint `POST /coach/generate-plan` dans `main.py` + 4 tests
   - Nouveau `coach/cron.py` (entry point pour systemd) + 2 tests
   - Update Server Action `finalizeOnboarding` côté Next.js : après set `onboarding_completed_at`, appelle workerPost `/coach/generate-plan`
7. **Documentation cron** : `worker/deploy/README.md` documente le nouveau systemd timer pour le cron weekly. Setup manuel par l'owner sur UNRAID.
8. **PR + smoke test** : tests pytest verts + push + ouvrir PR + smoke test post-merge (finalize onboarding → vérifier que plan généré en DB)

Ordre conseillé : 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8.

## 9. Points de vigilance

- **Cold start** : si user vient de connecter Garmin, 0-30j d'activities. `estimate_initial_ctl_from_profile` donne une baseline conservatrice. Une fois le sync 90j Garmin terminé (cron daily 05:00 UTC), le cron weekly (dimanche 22:00 UTC) recalcule avec données réelles.
- **Cron weekly timing** : dimanche 22h UTC = avant le sync Garmin du lundi 05h UTC. Le cron weekly utilise donc les activities jusqu'au samedi inclus. Décalage constant, acceptable.
- **Race date passée** : cron weekly skip si `race_goal.race_date < now()`. Si l'user veut une nouvelle course, il en ajoute une via /profile et la met `is_primary=true`.
- **Multi-course** : 1 plan actif par `is_primary=true` race_goal. Le contrôle d'unicité est fait au niveau SQL (`training_plans_active_per_user_per_race`).
- **Modifications profil** : si user change FTP/sports_strengths/available_days, le plan reste figé jusqu'au prochain cron weekly OU régénération manuelle (post-MVP).
- **Performance** : 12 semaines × 7 jours = ~84 rows insérés en bulk. Supabase peut gérer en <200ms. Endpoint répond en <3s normalement.
- **Trigger fail-safe** : si `finalizeOnboarding` Server Action appelle `/coach/generate-plan` et que le worker échoue (timeout, 500), l'user voit quand même `/profile` (on ne bloque pas la redirection). Le cron weekly suivant régénérera. Toast d'erreur côté frontend pour info.
- **TSS recalc lors du backfill** : le script `backfill_tss.py` est idempotent (skip si `tss IS NOT NULL`). Si on veut tout recalculer (ex: après fix du transformer), lancer avec un flag `--force`.
- **Audit cyber** : surface attaque réduite (endpoint déjà JWT-auth, pas d'user input dynamique, pas de SQL string interpolation). Skip audit Red/Blue formel pour cette EPIC.

## 10. Effort estimé détaillé

| Sous-livrable | Effort |
|---|---|
| 1. Migration DB | 0.5j |
| 2. `tss.py` + tests | 0.5j |
| 3. `banister.py` + tests | 1j |
| 4. `phases.py` + tests | 0.5j |
| 5. `planner.py` + tests | 2j |
| 6. Worker integration (transformer + endpoint + cron + finalizeOnboarding hook) | 1.5j |
| 7. Documentation cron systemd | 0.5j |
| 8. PR + smoke test | 0.5j |
| **Total** | **7j** (≈ borne haute du spec global 5-7j, justifié par le scope explicite) |

---

**Fin du spec.**

Une fois validé par l'user, on passe à `superpowers:writing-plans` pour le plan d'implémentation détaillé.
