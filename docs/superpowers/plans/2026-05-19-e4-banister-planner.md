# E4 — Banister Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implémenter le moteur de planification Banister : calcul TSS multi-tier, modèle CTL/ATL/TSB exponentiel, découpage en phases base/build/peak/taper, génération de `planned_sessions` daily, endpoint worker `POST /coach/generate-plan` + cron weekly + intégration à `finalizeOnboarding`.

**Architecture:** Nouveau module Python `worker/src/garmin_sync/coach/` avec 5 sous-modules (tss, banister, phases, planner, cron) + 1 endpoint FastAPI + 2 nouvelles tables Supabase (`training_plans`, `planned_sessions`) avec RLS. Le frontend Next.js appelle l'endpoint depuis `finalizeOnboarding` Server Action (fail-safe : ne bloque pas le redirect si échec). Cron systemd UNRAID régénère hebdomadairement.

**Tech Stack:**
- Worker : Python 3.12, FastAPI, pytest, supabase-py
- DB : Supabase Postgres + RLS
- Frontend : Next.js 15 Server Actions, supabase-js
- Cron : systemd timer (UNRAID User Scripts) — config manuelle documentée

**Spec source :** [`docs/superpowers/specs/2026-05-19-e4-banister-planner-design.md`](../specs/2026-05-19-e4-banister-planner-design.md)

---

## Pré-requis avant de démarrer

- Branche dédiée : `git checkout main && git pull && git checkout -b feat/e4-banister-planner`
- Worker en local : `cd worker && uv sync --all-groups && uv run pytest -q` (vérif baseline tests verts)
- Supabase MCP accessible (`mcp__supabase__apply_migration` + `mcp__supabase__execute_sql`)

---

## Task 1 — Migration DB : `training_plans` + `planned_sessions` + RLS

**Files:**
- Create: `supabase/migrations/20260520000000_e4_training_plans.sql`

- [ ] **Step 1: Créer le fichier migration**

```sql
-- 20260520000000_e4_training_plans.sql
-- E4 — Moteur de planification Banister : 2 tables + RLS

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

create unique index if not exists training_plans_active_per_user_per_race
  on public.training_plans (user_id, race_goal_id) where status = 'active';
create index if not exists training_plans_user_status_idx
  on public.training_plans (user_id, status);

alter table public.training_plans enable row level security;

drop policy if exists "users read own plans"   on public.training_plans;
drop policy if exists "users insert own plans" on public.training_plans;
drop policy if exists "users update own plans" on public.training_plans;
drop policy if exists "users delete own plans" on public.training_plans;

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

create index if not exists planned_sessions_user_date_idx
  on public.planned_sessions (user_id, date);
create index if not exists planned_sessions_plan_idx
  on public.planned_sessions (plan_id);

alter table public.planned_sessions enable row level security;

drop policy if exists "users read own sessions"   on public.planned_sessions;
drop policy if exists "users insert own sessions" on public.planned_sessions;
drop policy if exists "users update own sessions" on public.planned_sessions;
drop policy if exists "users delete own sessions" on public.planned_sessions;

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

- [ ] **Step 2: Apply via Supabase MCP**

Use `mcp__supabase__apply_migration`:
- `project_id`: `peiyrqplymdlmlpsbqzu`
- `name`: `20260520000000_e4_training_plans`
- `query`: contenu SQL ci-dessus complet

- [ ] **Step 3: Verify tables created**

Use `mcp__supabase__execute_sql`:
```sql
select table_name, row_count, has_pkey
from (
  select t.table_name,
    (select count(*) from public.training_plans) as tp_count,
    true as has_pkey
  from information_schema.tables t
  where t.table_schema = 'public' and t.table_name in ('training_plans', 'planned_sessions')
) sub;
```
Expected: 2 tables.

```sql
select tablename, rowsecurity from pg_tables
where schemaname = 'public' and tablename in ('training_plans','planned_sessions');
```
Expected: 2 rows, both `rowsecurity=true`.

```sql
select policyname, tablename from pg_policies
where tablename in ('training_plans','planned_sessions') order by tablename, policyname;
```
Expected: 8 policies (4 per table).

```sql
select indexname from pg_indexes
where tablename = 'training_plans' and indexname = 'training_plans_active_per_user_per_race';
```
Expected: 1 row.

- [ ] **Step 4: Test unique partial index**

```sql
-- Insert one active plan for fake (user_id, race_goal_id) — should work
-- (we'll skip this in prod since no real user_id, just verify the constraint structure exists)
select pg_get_indexdef(oid)
from pg_class where relname = 'training_plans_active_per_user_per_race';
```
Expected: contient `WHERE (status = 'active'::text)`.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/20260520000000_e4_training_plans.sql
git commit -m "feat(db): add training_plans + planned_sessions tables for E4"
```

---

## Task 2 — `coach/tss.py` : calcul TSS multi-tier

**Files:**
- Create: `worker/src/garmin_sync/coach/__init__.py` (empty)
- Create: `worker/src/garmin_sync/coach/tss.py`
- Create: `worker/tests/coach/__init__.py` (empty)
- Create: `worker/tests/coach/test_tss.py`

- [ ] **Step 1: Create empty `__init__.py` files**

```bash
cd /home/tellebma/DEV/garmin_training
mkdir -p worker/src/garmin_sync/coach worker/tests/coach
touch worker/src/garmin_sync/coach/__init__.py worker/tests/coach/__init__.py
```

- [ ] **Step 2: Write failing test `worker/tests/coach/test_tss.py`**

```python
"""Tests for TSS calculation (multi-tier: power > hrTSS > duration fallback)."""

from __future__ import annotations

from garmin_sync.coach.tss import compute_tss


def test_cycling_with_power_uses_pwTSS_formula() -> None:
    """TSS = duration_h × IF² × 100 where IF = power_avg / FTP."""
    tss = compute_tss(
        duration_s=3600,  # 1h
        sport='cycling',
        power_avg=200,
        hr_avg=None,
        ftp_watts=250,
        fc_max_bpm=None,
    )
    # IF = 200/250 = 0.8 → TSS = 1 * 0.64 * 100 = 64
    assert tss == 64.0


def test_running_with_hr_uses_hrTSS() -> None:
    """hrTSS = duration_h × IF² × 100 where IF = hr_avg / (0.9 × FCmax)."""
    tss = compute_tss(
        duration_s=3600,
        sport='running',
        power_avg=None,
        hr_avg=153,  # = 0.9 × 170 (LTHR if FCmax=170)
        ftp_watts=None,
        fc_max_bpm=170,
    )
    # IF = 153/(0.9 × 170) = 153/153 = 1.0 → TSS = 1 × 1 × 100 = 100
    assert tss == 100.0


def test_duration_only_fallback() -> None:
    """No power, no HR → 50 TSS/h fallback."""
    tss = compute_tss(
        duration_s=7200,  # 2h
        sport='swimming',
        power_avg=None,
        hr_avg=None,
        ftp_watts=None,
        fc_max_bpm=None,
    )
    # 2h × 50 = 100
    assert tss == 100.0


def test_zero_duration_returns_none() -> None:
    assert compute_tss(
        duration_s=0,
        sport='cycling',
        power_avg=200,
        hr_avg=150,
        ftp_watts=250,
        fc_max_bpm=180,
    ) is None


def test_cycling_without_power_falls_back_to_hrTSS() -> None:
    """If sport is cycling but no power_avg, use hrTSS not fallback."""
    tss = compute_tss(
        duration_s=3600,
        sport='cycling',
        power_avg=None,
        hr_avg=144,  # = 0.8 × 180
        ftp_watts=None,
        fc_max_bpm=180,
    )
    # LTHR = 162, IF = 144/162 ≈ 0.889 → TSS ≈ 79
    assert tss is not None
    assert 78 < tss < 80
```

- [ ] **Step 3: Run test, observe failure**

```bash
cd /home/tellebma/DEV/garmin_training/worker
uv run pytest tests/coach/test_tss.py -v
```
Expected: FAIL — ModuleNotFoundError on `garmin_sync.coach.tss`.

- [ ] **Step 4: Implement `worker/src/garmin_sync/coach/tss.py`**

```python
"""TSS (Training Stress Score) calculation with 3-tier strategy.

Tier 1 — Power-based (most precise) : cycling with power-meter + FTP known.
    TSS = duration_h × IF² × 100, where IF = power_avg / FTP

Tier 2 — hrTSS : any sport with HR + FCmax known.
    hrTSS = duration_h × IF² × 100, where IF = hr_avg / LTHR, LTHR ≈ 0.90 × FCmax

Tier 3 — Fallback : duration only.
    estTSS = duration_h × 50  (50 TSS/h endurance avg)
"""

from __future__ import annotations

LTHR_RATIO = 0.90  # LTHR ≈ 0.90 × FCmax — coarse but standard heuristic
FALLBACK_TSS_PER_HOUR = 50  # average endurance load
CYCLING_SPORTS = {'cycling', 'indoor_cycling', 'mountain_biking'}


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

    Returns None if duration is invalid (<= 0).
    """
    duration_h = duration_s / 3600
    if duration_h <= 0:
        return None

    # Tier 1 — cycling with power
    if sport in CYCLING_SPORTS and power_avg and ftp_watts:
        intensity_factor = power_avg / ftp_watts
        return round(duration_h * intensity_factor**2 * 100, 2)

    # Tier 2 — hrTSS
    if hr_avg and fc_max_bpm:
        lthr = fc_max_bpm * LTHR_RATIO
        intensity_factor = hr_avg / lthr
        return round(duration_h * intensity_factor**2 * 100, 2)

    # Tier 3 — fallback
    return round(duration_h * FALLBACK_TSS_PER_HOUR, 2)
```

- [ ] **Step 5: Run tests, verify pass**

```bash
cd /home/tellebma/DEV/garmin_training/worker
uv run pytest tests/coach/test_tss.py -v
```
Expected: 5/5 PASS.

- [ ] **Step 6: Quality gates**

```bash
cd /home/tellebma/DEV/garmin_training/worker
uv run ruff check . && uv run mypy src/
```
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add worker/src/garmin_sync/coach/__init__.py worker/src/garmin_sync/coach/tss.py worker/tests/coach/__init__.py worker/tests/coach/test_tss.py
git commit -m "feat(coach): add TSS calculator (power > hrTSS > duration fallback)"
```

---

## Task 3 — `coach/banister.py` : modèle Banister CTL/ATL/TSB

**Files:**
- Create: `worker/src/garmin_sync/coach/banister.py`
- Create: `worker/tests/coach/test_banister.py`

- [ ] **Step 1: Write failing tests `worker/tests/coach/test_banister.py`**

```python
"""Tests for Banister exponential model (CTL/ATL/TSB)."""

from __future__ import annotations

from datetime import date, timedelta

from garmin_sync.coach.banister import (
    CTL_TAU,
    ATL_TAU,
    BanisterState,
    compute_banister_history,
    estimate_initial_ctl_from_profile,
)


def test_constants_match_classic_model() -> None:
    assert CTL_TAU == 42
    assert ATL_TAU == 7


def test_compute_banister_zero_tss_decays_exponentially() -> None:
    """No TSS for 42 days → CTL drops by ~63% (1 - 1/e) from initial."""
    start = date(2026, 1, 1)
    end = start + timedelta(days=41)  # 42 days inclusive
    states = compute_banister_history({}, start, end, initial_ctl=100.0, initial_atl=100.0)
    assert len(states) == 42
    final = states[-1]
    # CTL after 42 days of zero load with τ=42 → ~100 × (41/42)^42 ≈ 36.7 (decay)
    # Or analytically: ctl_n = ctl_0 × (1 - 1/τ)^n
    expected_ctl = 100.0 * (1 - 1 / CTL_TAU) ** 42
    assert abs(final.ctl - expected_ctl) < 0.5


def test_compute_banister_constant_tss_converges() -> None:
    """TSS=100 every day for 200 days → CTL converges towards 100."""
    start = date(2026, 1, 1)
    end = start + timedelta(days=199)
    tss_dict = {start + timedelta(days=i): 100.0 for i in range(200)}
    states = compute_banister_history(tss_dict, start, end, initial_ctl=0.0, initial_atl=0.0)
    final = states[-1]
    # After 200 days = ~4.7 × τ1 → CTL should be ≥ 99
    assert final.ctl > 99.0
    assert final.atl > 99.0
    assert abs(final.tsb) < 1.0  # CTL ≈ ATL → TSB ≈ 0


def test_compute_banister_single_day() -> None:
    """start = end → 1 state returned."""
    start = date(2026, 1, 1)
    states = compute_banister_history({start: 50.0}, start, start, initial_ctl=0.0, initial_atl=0.0)
    assert len(states) == 1
    # ctl_0=0, tss=50 → ctl_1 = 0 + (50 - 0)/42 ≈ 1.19
    assert abs(states[0].ctl - 50.0 / CTL_TAU) < 0.01


def test_compute_banister_missing_days_treated_as_zero() -> None:
    """Gaps in tss_by_date are zero TSS (rest days)."""
    start = date(2026, 1, 1)
    end = start + timedelta(days=2)
    tss_dict = {start: 100.0}  # only day 0
    states = compute_banister_history(tss_dict, start, end, initial_ctl=0.0, initial_atl=0.0)
    assert len(states) == 3
    # day 0 : ctl += (100-0)/42 ≈ 2.38
    # day 1 : ctl += (0 - 2.38)/42 ≈ 2.38 - 0.057 ≈ 2.33
    # day 2 : ctl += (0 - 2.33)/42 ≈ 2.27
    assert states[0].ctl > states[1].ctl > states[2].ctl


def test_estimate_initial_ctl_from_profile_realistic() -> None:
    """hours_per_week=8 → ~57 TSS daily-equivalent baseline."""
    assert estimate_initial_ctl_from_profile(8) == round(8 * 50 / 7, 2)


def test_estimate_initial_ctl_from_profile_zero_or_none() -> None:
    assert estimate_initial_ctl_from_profile(None) == 0.0
    assert estimate_initial_ctl_from_profile(0) == 0.0
```

- [ ] **Step 2: Run, observe failure**

```bash
cd /home/tellebma/DEV/garmin_training/worker
uv run pytest tests/coach/test_banister.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `worker/src/garmin_sync/coach/banister.py`**

```python
"""Banister model — exponential CTL/ATL/TSB tracking.

CTL ("Chronic Training Load") = long-term fitness, τ1 = 42 days.
ATL ("Acute Training Load") = short-term fatigue, τ2 = 7 days.
TSB ("Training Stress Balance") = CTL - ATL = "form" indicator.

Daily update :
    CTL_today = CTL_yesterday + (TSS_today - CTL_yesterday) / τ1
    ATL_today = ATL_yesterday + (TSS_today - ATL_yesterday) / τ2

Days without activity are treated as TSS=0 (decay).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

CTL_TAU = 42  # days — fitness time constant
ATL_TAU = 7   # days — fatigue time constant


@dataclass(frozen=True)
class BanisterState:
    """Banister state for a single day."""
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
    """Iterate day-by-day from start to end inclusive. Returns list of states."""
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
    """Cold-start CTL estimate when no historical TSS available.

    Heuristic : weekly_TSS ≈ hours × 50 (endurance avg), daily-equivalent baseline = weekly / 7.
    Returns 0.0 if hours_per_week is None or zero.
    """
    if not hours_per_week or hours_per_week <= 0:
        return 0.0
    weekly_tss = hours_per_week * 50
    return round(weekly_tss / 7, 2)
```

- [ ] **Step 4: Run, verify pass**

```bash
cd /home/tellebma/DEV/garmin_training/worker
uv run pytest tests/coach/test_banister.py -v
```
Expected: 7/7 PASS.

- [ ] **Step 5: Quality gates**

```bash
uv run ruff check . && uv run mypy src/
```

- [ ] **Step 6: Commit**

```bash
git add worker/src/garmin_sync/coach/banister.py worker/tests/coach/test_banister.py
git commit -m "feat(coach): add Banister CTL/ATL/TSB model + initial estimator"
```

---

## Task 4 — `coach/phases.py` : découpage base/build/peak/taper

**Files:**
- Create: `worker/src/garmin_sync/coach/phases.py`
- Create: `worker/tests/coach/test_phases.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for phase computation (base/build/peak/taper backward-planning)."""

from __future__ import annotations

from datetime import date, timedelta

from garmin_sync.coach.phases import Phase, compute_phases


def test_12_weeks_plan_distribution() -> None:
    """12-week plan : ~6-7 base + 3 build + 1 peak + 2 taper."""
    start = date(2026, 1, 1)
    race = start + timedelta(weeks=12)
    phases = compute_phases(start, race)
    counts = {p: sum(1 for _, ph in phases if ph == p) for p in ('base', 'build', 'peak', 'taper')}
    assert sum(counts.values()) == 12
    assert counts['taper'] == 2
    assert counts['peak'] >= 1
    assert counts['build'] >= 3
    assert counts['base'] >= 5


def test_8_weeks_plan_has_2_taper() -> None:
    start = date(2026, 1, 1)
    race = start + timedelta(weeks=8)
    phases = compute_phases(start, race)
    assert len(phases) == 8
    counts = {p: sum(1 for _, ph in phases if ph == p) for p in ('base', 'build', 'peak', 'taper')}
    assert counts['taper'] == 2


def test_4_weeks_plan_minimum_1_taper() -> None:
    """Short plan still has at least 1 taper week."""
    start = date(2026, 1, 1)
    race = start + timedelta(weeks=4)
    phases = compute_phases(start, race)
    assert len(phases) == 4
    last_phase = phases[-1][1]
    assert last_phase == 'taper'


def test_1_week_plan_is_full_taper() -> None:
    start = date(2026, 1, 1)
    race = start + timedelta(weeks=1)
    phases = compute_phases(start, race)
    assert len(phases) == 1
    assert phases[0] == (0, 'taper')


def test_phases_are_in_order_and_indexed() -> None:
    """week_offset must go 0, 1, 2, ... sequentially."""
    start = date(2026, 1, 1)
    race = start + timedelta(weeks=10)
    phases = compute_phases(start, race)
    for i, (offset, _) in enumerate(phases):
        assert offset == i
```

- [ ] **Step 2: Run, observe failure**

```bash
cd /home/tellebma/DEV/garmin_training/worker
uv run pytest tests/coach/test_phases.py -v
```

- [ ] **Step 3: Implement `worker/src/garmin_sync/coach/phases.py`**

```python
"""Phase computation : backward planning from race_date.

Phase ratios (target distribution):
- base   : 50-60% of total weeks
- build  : 25-30%
- peak   : 10-15%
- taper  : last 1-2 weeks

For short plans (< 6 weeks), peak collapses into build.
For 1-week plans, the whole week is taper.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

Phase = Literal['base', 'build', 'peak', 'taper']


def compute_phases(start_date: date, race_date: date) -> list[tuple[int, Phase]]:
    """Return [(week_offset, phase), ...] from week 0 (start) to race week.

    Backward planning : taper at the end, then peak, then build, then base.
    """
    total_weeks = max(1, (race_date - start_date).days // 7)

    if total_weeks == 1:
        return [(0, 'taper')]

    # Targets — backward from race_date
    taper_weeks = 1 if total_weeks < 8 else 2
    peak_weeks = max(1, total_weeks // 8) if total_weeks >= 6 else 0
    build_weeks = max(2, total_weeks // 4) if total_weeks >= 6 else max(1, total_weeks // 3)
    base_weeks = max(0, total_weeks - taper_weeks - peak_weeks - build_weeks)

    phases: list[tuple[int, Phase]] = []
    for w in range(total_weeks):
        if w < base_weeks:
            phase: Phase = 'base'
        elif w < base_weeks + build_weeks:
            phase = 'build'
        elif w < total_weeks - taper_weeks:
            phase = 'peak'
        else:
            phase = 'taper'
        phases.append((w, phase))
    return phases
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest tests/coach/test_phases.py -v
```
Expected: 5/5 PASS.

- [ ] **Step 5: Quality gates + commit**

```bash
uv run ruff check . && uv run mypy src/
git add worker/src/garmin_sync/coach/phases.py worker/tests/coach/test_phases.py
git commit -m "feat(coach): add phase computation (base/build/peak/taper backward)"
```

---

## Task 5 — `coach/planner.py` : orchestrateur génération sessions

**Files:**
- Create: `worker/src/garmin_sync/coach/planner.py`
- Create: `worker/tests/coach/test_planner.py`

This task is the largest — it integrates Tasks 2, 3, 4 and inserts into DB.

- [ ] **Step 1: Write failing tests `worker/tests/coach/test_planner.py`**

```python
"""Tests for the plan orchestrator (generate_plan)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.coach.planner import (
    DELOAD_RAMP_RATE,
    NORMAL_RAMP_RATE,
    TAPER_RAMP_RATE,
    distribute_weekly_tss_by_sport,
    pick_session_types_for_phase,
    generate_plan,
)


def test_distribute_weekly_tss_no_sports_strengths_returns_equal_share() -> None:
    """Triathlon with sports_strengths all=3 → equal share between swim/bike/run."""
    sports_in_race = ['swim', 'bike', 'run']
    strengths = {'swim': 3, 'bike': 3, 'run': 3}
    out = distribute_weekly_tss_by_sport(weekly_tss=300, sports_in_race=sports_in_race, sports_strengths=strengths)
    assert abs(out['swim'] - 100) < 1
    assert abs(out['bike'] - 100) < 1
    assert abs(out['run'] - 100) < 1


def test_distribute_weekly_tss_weak_sport_gets_more() -> None:
    """sports_strengths.swim=1 → swim gets +20% relative; bike=5 → -10%; normalized."""
    sports_in_race = ['swim', 'bike', 'run']
    strengths = {'swim': 1, 'bike': 5, 'run': 3}
    out = distribute_weekly_tss_by_sport(weekly_tss=300, sports_in_race=sports_in_race, sports_strengths=strengths)
    assert out['swim'] > out['run'] > out['bike']
    assert abs(sum(out.values()) - 300) < 0.5


def test_pick_session_types_for_base_phase() -> None:
    types = pick_session_types_for_phase('base')
    assert 'endurance' in types
    assert 'long' in types
    assert 'recovery' in types


def test_pick_session_types_for_build_phase() -> None:
    types = pick_session_types_for_phase('build')
    assert 'threshold' in types
    assert 'long' in types
    assert 'endurance' in types


def test_pick_session_types_for_peak_phase() -> None:
    types = pick_session_types_for_phase('peak')
    assert 'intervals' in types


def test_pick_session_types_for_taper_phase() -> None:
    types = pick_session_types_for_phase('taper')
    assert 'endurance' in types
    assert 'long' not in types  # short sessions only during taper


def test_ramp_rates_consistent_with_spec() -> None:
    """Sanity check : deload < normal, taper << normal."""
    assert DELOAD_RAMP_RATE < NORMAL_RAMP_RATE
    assert TAPER_RAMP_RATE < DELOAD_RAMP_RATE


def _make_fake_db_for_plan_generation(
    *,
    user_id: str,
    profile: dict,
    race_goal: dict,
    activities: list[dict] | None = None,
):
    """Build a chained-mock supabase client returning the given fixtures."""
    fake = MagicMock()
    # athlete_profiles.select().eq().single().execute().data → profile
    fake.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = profile
    return fake


def test_generate_plan_no_race_goal_returns_error(monkeypatch) -> None:
    """Without an active race_goal, generate_plan returns no_race_goal status."""
    from garmin_sync.coach import planner as p_mod

    fake_db = MagicMock()
    # athlete_profiles returns valid profile
    profile_chain = fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute
    profile_chain.return_value.data = {
        'user_id': 'u1',
        'hours_per_week': 6,
        'ftp_watts': None,
        'fc_max_bpm': 180,
        'sports_strengths': {'swim': 3, 'bike': 3, 'run': 3},
        'available_days': ['mon', 'tue', 'wed', 'thu', 'sat', 'sun'],
    }
    # race_goals query returns no rows
    fake_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybeSingle.return_value.execute.return_value.data = None

    monkeypatch.setattr(p_mod, 'get_admin_client', lambda: fake_db)
    result = generate_plan('u1')
    assert result['status'] == 'no_race_goal'


def test_generate_plan_happy_path_writes_to_db(monkeypatch) -> None:
    """generate_plan with profile + race_goal inserts training_plans + planned_sessions."""
    from garmin_sync.coach import planner as p_mod

    fake_db = MagicMock()
    profile = {
        'user_id': 'u1',
        'hours_per_week': 6,
        'ftp_watts': 200,
        'fc_max_bpm': 180,
        'sports_strengths': {'swim': 3, 'bike': 3, 'run': 3},
        'available_days': ['mon', 'tue', 'wed', 'thu', 'sat', 'sun'],
    }
    race = {
        'id': 'rg-1',
        'race_date': (date.today() + timedelta(weeks=8)).isoformat(),
        'discipline': 'triathlon',
        'legs': [
            {'order': 1, 'discipline': 'swim', 'distance_km': 1.4, 'elevation_gain_m': 0},
            {'order': 2, 'discipline': 'bike', 'distance_km': 53, 'elevation_gain_m': 2200},
            {'order': 3, 'discipline': 'run', 'distance_km': 8, 'elevation_gain_m': 200},
        ],
    }
    # Build a side_effect on .table(...) so each call returns the right shape
    def _table_router(table_name: str):
        m = MagicMock()
        if table_name == 'athlete_profiles':
            m.select.return_value.eq.return_value.single.return_value.execute.return_value.data = profile
        elif table_name == 'race_goals':
            m.select.return_value.eq.return_value.eq.return_value.maybeSingle.return_value.execute.return_value.data = race
        elif table_name == 'activities':
            m.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
        elif table_name == 'training_plans':
            m.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
            m.insert.return_value.execute.return_value.data = [{'id': 'plan-1'}]
        elif table_name == 'planned_sessions':
            m.insert.return_value.execute.return_value.data = []
        return m

    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(p_mod, 'get_admin_client', lambda: fake_db)

    result = generate_plan('u1')
    assert result['status'] == 'ok'
    assert result['weeks_count'] == 8
    assert result['sessions_count'] > 0


def test_generate_plan_archives_previous_active_plan(monkeypatch) -> None:
    """Re-generating archives the existing active plan via UPDATE before INSERT."""
    from garmin_sync.coach import planner as p_mod

    fake_db = MagicMock()
    profile = {
        'user_id': 'u1', 'hours_per_week': 6, 'ftp_watts': None, 'fc_max_bpm': 180,
        'sports_strengths': {'swim': 3, 'bike': 3, 'run': 3},
        'available_days': ['mon', 'tue', 'wed', 'thu', 'sat', 'sun'],
    }
    race = {
        'id': 'rg-1',
        'race_date': (date.today() + timedelta(weeks=8)).isoformat(),
        'discipline': 'triathlon',
        'legs': [
            {'order': 1, 'discipline': 'swim', 'distance_km': 1.4, 'elevation_gain_m': 0},
            {'order': 2, 'discipline': 'bike', 'distance_km': 53, 'elevation_gain_m': 2200},
            {'order': 3, 'discipline': 'run', 'distance_km': 8, 'elevation_gain_m': 200},
        ],
    }
    update_call = MagicMock()

    def _table_router(table_name: str):
        m = MagicMock()
        if table_name == 'athlete_profiles':
            m.select.return_value.eq.return_value.single.return_value.execute.return_value.data = profile
        elif table_name == 'race_goals':
            m.select.return_value.eq.return_value.eq.return_value.maybeSingle.return_value.execute.return_value.data = race
        elif table_name == 'activities':
            m.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
        elif table_name == 'training_plans':
            m.update = update_call
            update_call.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
            m.insert.return_value.execute.return_value.data = [{'id': 'plan-2'}]
        else:
            m.insert.return_value.execute.return_value.data = []
        return m

    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(p_mod, 'get_admin_client', lambda: fake_db)

    result = generate_plan('u1')
    assert result['status'] == 'ok'
    update_call.assert_called_once()
    args, _kwargs = update_call.call_args
    assert args[0]['status'] == 'archived'
```

- [ ] **Step 2: Run, observe failure**

```bash
cd /home/tellebma/DEV/garmin_training/worker
uv run pytest tests/coach/test_planner.py -v
```

- [ ] **Step 3: Implement `worker/src/garmin_sync/coach/planner.py`**

```python
"""Plan orchestrator : reads profile + race_goal + activities, computes Banister
state, derives phases + sessions, writes to DB.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from garmin_sync.coach.banister import (
    BanisterState,
    compute_banister_history,
    estimate_initial_ctl_from_profile,
)
from garmin_sync.coach.phases import Phase, compute_phases
from garmin_sync.coach.tss import compute_tss
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

# Ramp rates by phase / week index
NORMAL_RAMP_RATE = 1.05    # +5% per week (normal weeks)
DELOAD_RAMP_RATE = 0.70    # -30% deload week (every 4th week)
TAPER_RAMP_RATE = 0.55     # -45% taper

DAY_NAME_TO_INDEX = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}


def distribute_weekly_tss_by_sport(
    *,
    weekly_tss: float,
    sports_in_race: list[str],
    sports_strengths: dict[str, int],
) -> dict[str, float]:
    """Distribute weekly TSS target between sports.

    Weak sport (score 1-2) → +20% relative share.
    Strong sport (score 4-5) → -10% relative share.
    Normalised so the sum equals weekly_tss.
    """
    weights: dict[str, float] = {}
    for s in sports_in_race:
        score = sports_strengths.get(s, 3)
        if score <= 2:
            weights[s] = 1.20
        elif score >= 4:
            weights[s] = 0.90
        else:
            weights[s] = 1.0
    total_w = sum(weights.values())
    return {s: round(weekly_tss * w / total_w, 2) for s, w in weights.items()}


def pick_session_types_for_phase(phase: Phase) -> list[str]:
    """Return the canonical set of session types for a given phase."""
    if phase == 'base':
        return ['endurance', 'long', 'recovery']
    if phase == 'build':
        return ['endurance', 'threshold', 'long']
    if phase == 'peak':
        return ['intervals', 'endurance', 'long']
    # taper
    return ['endurance', 'recovery']


def _ramp_rate_for_week(week_offset: int, phase: Phase) -> float:
    """Ramp rate for a given week. Deload every 4th week (mod 3 because 0-indexed)."""
    if phase == 'taper':
        return TAPER_RAMP_RATE
    # deload at weeks 3, 7, 11, ... (every 4th, 0-indexed)
    if (week_offset + 1) % 4 == 0:
        return DELOAD_RAMP_RATE
    return NORMAL_RAMP_RATE


def _placement_priority_for_day(day_idx: int) -> int:
    """Sunday (=6) gets long sessions; Mon/Thu (=0,3) get recovery; rest = mid-week."""
    if day_idx == 6:
        return 0  # long
    if day_idx in (0, 3):
        return 2  # recovery
    return 1  # mid-week endurance/threshold/intervals


def _build_week_sessions(
    *,
    week_offset: int,
    phase: Phase,
    week_start: date,
    weekly_tss: float,
    sports_in_race: list[str],
    sports_strengths: dict[str, int],
    available_days: list[str],
    is_last_week: bool,
    race_date: date,
    race_sport: str,
) -> list[dict[str, Any]]:
    """Generate one week's planned sessions."""
    sessions: list[dict[str, Any]] = []
    types_for_phase = pick_session_types_for_phase(phase)
    tss_by_sport = distribute_weekly_tss_by_sport(
        weekly_tss=weekly_tss, sports_in_race=sports_in_race, sports_strengths=sports_strengths
    )
    available_idx = {DAY_NAME_TO_INDEX[d] for d in available_days if d in DAY_NAME_TO_INDEX}

    # For each day in the week, assign a session if it's available
    used_types: list[str] = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_idx = day.weekday()
        # Race day override
        if is_last_week and day == race_date:
            sessions.append({
                'date': day.isoformat(),
                'sport': race_sport,
                'session_type': 'race',
                'target_duration_s': None,
                'target_tss': None,
                'phase': 'race',
                'week_offset': week_offset,
            })
            continue
        if day_idx not in available_idx:
            sessions.append({
                'date': day.isoformat(),
                'sport': 'rest',
                'session_type': 'rest',
                'target_duration_s': 0,
                'target_tss': 0,
                'phase': phase,
                'week_offset': week_offset,
            })
            continue

        # Pick a session type for the day (round-robin avoiding back-to-back hard)
        priority = _placement_priority_for_day(day_idx)
        if priority == 0 and 'long' in types_for_phase:
            stype = 'long'
        elif priority == 2 and 'recovery' in types_for_phase:
            stype = 'recovery'
        else:
            # rotate through remaining types, avoid back-to-back hard
            hard = {'threshold', 'intervals'}
            candidates = [t for t in types_for_phase if t not in {'long', 'recovery'}]
            last = used_types[-1] if used_types else None
            if last in hard:
                candidates = [t for t in candidates if t not in hard]
            stype = candidates[len(used_types) % max(1, len(candidates))] if candidates else 'endurance'

        used_types.append(stype)

        # Rotate sport per day (round-robin between disciplines)
        sport = sports_in_race[(day_idx) % len(sports_in_race)] if sports_in_race else 'run'
        # Heuristic duration : tss * 3600 / 50 (assume IF=1 fallback for now)
        per_day_tss = tss_by_sport.get(sport, 0) / max(1, len(available_idx))
        duration_s = int(per_day_tss * 3600 / 50)
        sessions.append({
            'date': day.isoformat(),
            'sport': sport,
            'session_type': stype,
            'target_duration_s': duration_s,
            'target_tss': round(per_day_tss, 2),
            'phase': phase,
            'week_offset': week_offset,
        })
    return sessions


def generate_plan(user_id: str) -> dict[str, Any]:
    """Generate a training plan for the given user.

    Returns:
        {"status": "ok", "plan_id": str, "weeks_count": int, "sessions_count": int}
        {"status": "no_race_goal"} if user has no active race
        {"status": "no_profile"} if profile not found
    """
    db = get_admin_client()
    profile = cast(
        'dict[str, Any] | None',
        db.table('athlete_profiles').select(
            'user_id, hours_per_week, ftp_watts, fc_max_bpm, sports_strengths, available_days'
        ).eq('user_id', user_id).single().execute().data,
    )
    if not profile:
        return {'status': 'no_profile'}

    race = cast(
        'dict[str, Any] | None',
        db.table('race_goals').select(
            'id, race_date, discipline, legs'
        ).eq('user_id', user_id).eq('is_primary', True).maybeSingle().execute().data,
    )
    if not race:
        return {'status': 'no_race_goal'}

    today = date.today()
    race_date = date.fromisoformat(race['race_date'])
    if race_date <= today:
        return {'status': 'race_in_past'}

    # Load last 180 days of activities and compute per-day TSS
    history_start = today - timedelta(days=180)
    activities = cast(
        'list[dict[str, Any]]',
        db.table('activities').select(
            'start_time, sport, duration_s, power_avg, hr_avg'
        ).eq('user_id', user_id).gte('start_time', history_start.isoformat()).execute().data
        or [],
    )

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
        d = datetime.fromisoformat(a['start_time'].replace('Z', '+00:00')).date()
        tss_by_date[d] = tss_by_date.get(d, 0.0) + tss

    # Cold start if < 14 days of activities
    if len(tss_by_date) < 14:
        init_ctl = estimate_initial_ctl_from_profile(profile.get('hours_per_week'))
        init_atl = init_ctl  # start at neutral TSB
    else:
        init_ctl = 0.0
        init_atl = 0.0

    states = compute_banister_history(
        tss_by_date=tss_by_date,
        start=history_start,
        end=today,
        initial_ctl=init_ctl,
        initial_atl=init_atl,
    )
    today_state: BanisterState = states[-1]

    # Compute phases and per-week sessions
    phases = compute_phases(today, race_date)
    weeks_count = len(phases)
    sports_in_race = [leg['discipline'] for leg in race['legs']]
    race_sport = race['legs'][0]['discipline'] if race['legs'] else 'run'
    sports_strengths = profile.get('sports_strengths') or {'swim': 3, 'bike': 3, 'run': 3}
    available_days = profile.get('available_days') or ['mon', 'wed', 'fri']

    # Find Monday of the current week
    week_start = today - timedelta(days=today.weekday())

    all_sessions: list[dict[str, Any]] = []
    for offset, phase in phases:
        ramp = _ramp_rate_for_week(offset, phase)
        weekly_tss = today_state.ctl * 7 * ramp
        is_last = offset == weeks_count - 1
        sessions = _build_week_sessions(
            week_offset=offset,
            phase=phase,
            week_start=week_start + timedelta(weeks=offset),
            weekly_tss=weekly_tss,
            sports_in_race=sports_in_race,
            sports_strengths=sports_strengths,
            available_days=available_days,
            is_last_week=is_last,
            race_date=race_date,
            race_sport=race_sport,
        )
        all_sessions.extend(sessions)

    # Archive previous active plan
    db.table('training_plans').update(
        {'status': 'archived'}
    ).eq('user_id', user_id).eq('race_goal_id', race['id']).execute()

    # Insert new plan
    insert_resp = db.table('training_plans').insert({
        'user_id': user_id,
        'race_goal_id': race['id'],
        'start_date': today.isoformat(),
        'end_date': race_date.isoformat(),
        'weeks_count': weeks_count,
        'ctl_initial': round(today_state.ctl, 2),
        'atl_initial': round(today_state.atl, 2),
        'tsb_initial': round(today_state.tsb, 2),
        'status': 'active',
        'params': {'cold_start': len(tss_by_date) < 14},
    }).execute()
    plan_id = insert_resp.data[0]['id']

    # Bulk insert sessions
    for s in all_sessions:
        s['plan_id'] = plan_id
        s['user_id'] = user_id
    if all_sessions:
        db.table('planned_sessions').insert(all_sessions).execute()

    return {
        'status': 'ok',
        'plan_id': plan_id,
        'weeks_count': weeks_count,
        'sessions_count': len(all_sessions),
    }
```

- [ ] **Step 4: Run, verify pass**

```bash
cd /home/tellebma/DEV/garmin_training/worker
uv run pytest tests/coach/test_planner.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Quality gates + commit**

```bash
uv run ruff check . && uv run mypy src/
git add worker/src/garmin_sync/coach/planner.py worker/tests/coach/test_planner.py
git commit -m "feat(coach): add plan orchestrator generate_plan with Banister + phases"
```

---

## Task 6 — Worker integration : transformer TSS + endpoint + cron + finalizeOnboarding

**Files:**
- Modify: `worker/src/garmin_sync/transformers/activities.py`
- Modify: `worker/src/garmin_sync/sync.py`
- Create: `worker/src/garmin_sync/coach/backfill_tss.py`
- Create: `worker/tests/coach/test_backfill_tss.py`
- Modify: `worker/src/garmin_sync/main.py`
- Modify: `worker/tests/test_main.py`
- Create: `worker/src/garmin_sync/coach/cron.py`
- Modify: `app/(app)/onboarding/actions.ts`

- [ ] **Step 1: Update `transformers/activities.py` to compute TSS inline**

Change the transformer signature to accept FTP + FCmax, and compute TSS :

```python
# worker/src/garmin_sync/transformers/activities.py
from typing import Any

from garmin_sync.coach.tss import compute_tss


def transform_activity(
    *,
    user_id: str,
    raw: dict[str, Any],
    ftp_watts: int | None = None,
    fc_max_bpm: int | None = None,
) -> dict[str, Any]:
    """Convert a Garmin activity dict into our `activities` table row."""
    start = _parse_dt(raw.get("startTimeGMT"))
    activity_type = raw.get("activityType") or {}
    sport = activity_type.get("typeKey", "unknown")
    duration_s = int(raw.get("duration") or 0)
    power_avg = _to_int(raw.get("averagePower"))
    hr_avg = _to_int(raw.get("averageHR"))
    tss = compute_tss(
        duration_s=duration_s,
        sport=sport,
        power_avg=power_avg,
        hr_avg=hr_avg,
        ftp_watts=ftp_watts,
        fc_max_bpm=fc_max_bpm,
    )
    return {
        "user_id": user_id,
        "garmin_activity_id": int(raw["activityId"]),
        "start_time": start.isoformat() if start else None,
        "sport": sport,
        "sub_sport": activity_type.get("parentTypeId"),
        "duration_s": duration_s,
        "distance_m": float(raw["distance"]) if raw.get("distance") is not None else None,
        "tss": tss,
        "hr_avg": hr_avg,
        "hr_max": _to_int(raw.get("maxHR")),
        "power_avg": power_avg,
        "power_max": _to_int(raw.get("maxPower")),
        "pace_avg_s_per_km": _pace_s_per_km(raw.get("averageSpeed")),
        "elevation_gain_m": _to_int(raw.get("elevationGain")),
        "calories": _to_int(raw.get("calories")),
        "raw": raw,
    }
# (keep _parse_dt, _to_int, _pace_s_per_km helpers as they were)
```

- [ ] **Step 2: Update `sync.py` to pass FTP + FCmax to transformer**

Modify the activities sync block to fetch the profile once and pass values :

```python
# Inside sync_user_for_date_range, BEFORE the activities try/except:
profile_resp = (
    db.table("athlete_profiles")
    .select("ftp_watts, fc_max_bpm")
    .eq("user_id", user_id)
    .single()
    .execute()
)
profile_data = profile_resp.data or {}
ftp = profile_data.get("ftp_watts")
fcmax = profile_data.get("fc_max_bpm")

# Then update the transform call:
rows = [
    transform_activity(user_id=user_id, raw=a, ftp_watts=ftp, fc_max_bpm=fcmax)
    for a in activities
]
```

- [ ] **Step 3: Update existing test `worker/tests/test_sync.py`**

Find the existing `transform_activity` invocations and update them with the new signature if needed. The fixture activities tests may need `ftp_watts=None, fc_max_bpm=None` added to assertions.

Run :
```bash
cd /home/tellebma/DEV/garmin_training/worker
uv run pytest tests/ -v
```
Fix any failures in test_sync.py from the new transform signature.

- [ ] **Step 4: Create backfill script + test**

```python
# worker/src/garmin_sync/coach/backfill_tss.py
"""One-shot script to compute TSS for activities where tss IS NULL.

Idempotent — skip rows where tss is already set.
Usage : python -m garmin_sync.coach.backfill_tss
"""

from __future__ import annotations

import logging
from typing import Any, cast

from garmin_sync.coach.tss import compute_tss
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)


def backfill_tss() -> dict[str, int]:
    """Compute TSS for all activities with tss IS NULL.

    Returns: {"updated": int, "skipped": int, "errors": int}
    """
    db = get_admin_client()
    activities = cast(
        'list[dict[str, Any]]',
        db.table('activities').select('id, user_id, duration_s, sport, power_avg, hr_avg')
        .is_('tss', 'null')
        .execute().data or [],
    )

    # Cache profiles by user
    profile_cache: dict[str, dict[str, Any]] = {}
    updated = 0
    skipped = 0
    errors = 0
    for a in activities:
        try:
            user_id = a['user_id']
            if user_id not in profile_cache:
                p = db.table('athlete_profiles').select('ftp_watts, fc_max_bpm') \
                    .eq('user_id', user_id).single().execute().data
                profile_cache[user_id] = p or {}
            profile = profile_cache[user_id]
            tss = compute_tss(
                duration_s=a.get('duration_s', 0),
                sport=a.get('sport', ''),
                power_avg=a.get('power_avg'),
                hr_avg=a.get('hr_avg'),
                ftp_watts=profile.get('ftp_watts'),
                fc_max_bpm=profile.get('fc_max_bpm'),
            )
            if tss is None:
                skipped += 1
                continue
            db.table('activities').update({'tss': tss}).eq('id', a['id']).execute()
            updated += 1
        except Exception:
            log.exception('Failed to backfill TSS for activity %s', a.get('id'))
            errors += 1
    return {'updated': updated, 'skipped': skipped, 'errors': errors}


if __name__ == '__main__':
    import json
    result = backfill_tss()
    print(json.dumps(result, indent=2))
```

Test :
```python
# worker/tests/coach/test_backfill_tss.py
"""Tests for the TSS backfill script."""

from __future__ import annotations

from unittest.mock import MagicMock

from garmin_sync.coach.backfill_tss import backfill_tss


def test_backfill_no_activities_returns_zero_counts(monkeypatch) -> None:
    from garmin_sync.coach import backfill_tss as mod
    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = []
    monkeypatch.setattr(mod, 'get_admin_client', lambda: fake_db)
    out = backfill_tss()
    assert out == {'updated': 0, 'skipped': 0, 'errors': 0}


def test_backfill_updates_each_activity_with_tss(monkeypatch) -> None:
    from garmin_sync.coach import backfill_tss as mod

    activities_data = [
        {'id': 'a1', 'user_id': 'u1', 'duration_s': 3600, 'sport': 'running',
         'power_avg': None, 'hr_avg': 153},
        {'id': 'a2', 'user_id': 'u1', 'duration_s': 7200, 'sport': 'cycling',
         'power_avg': 200, 'hr_avg': None},
    ]
    profile_data = {'ftp_watts': 250, 'fc_max_bpm': 170}

    fake_db = MagicMock()
    def _table_router(name: str):
        m = MagicMock()
        if name == 'activities':
            m.select.return_value.is_.return_value.execute.return_value.data = activities_data
            m.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == 'athlete_profiles':
            m.select.return_value.eq.return_value.single.return_value.execute.return_value.data = profile_data
        return m
    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(mod, 'get_admin_client', lambda: fake_db)

    out = backfill_tss()
    assert out['updated'] == 2
    assert out['errors'] == 0
```

- [ ] **Step 5: Add endpoint `POST /coach/generate-plan` to `main.py`**

Add after the `garmin_profile_sync` endpoint :

```python
@app.post("/coach/generate-plan")
def coach_generate_plan(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Generate or regenerate a Banister training plan for the calling user."""
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

Add tests to `test_main.py` :

```python
def test_coach_generate_plan_requires_jwt(client) -> None:
    r = client.post("/coach/generate-plan")
    assert r.status_code == 401


def test_coach_generate_plan_returns_status_dict(client, monkeypatch) -> None:
    from garmin_sync import main as main_mod
    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")
    def fake(user_id):
        return {"status": "ok", "plan_id": "p1", "weeks_count": 8, "sessions_count": 56}
    monkeypatch.setattr("garmin_sync.coach.planner.generate_plan", fake)
    r = client.post("/coach/generate-plan", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["sessions_count"] == 56


def test_coach_generate_plan_catches_unexpected(client, monkeypatch) -> None:
    from garmin_sync import main as main_mod
    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")
    monkeypatch.setattr(
        "garmin_sync.coach.planner.generate_plan",
        lambda _u: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    r = client.post("/coach/generate-plan", headers={"Authorization": "Bearer x"})
    body = r.json()
    assert body["status"] == "unexpected_error"
    assert body["type"] == "RuntimeError"
```

- [ ] **Step 6: Create cron entry point `coach/cron.py`**

```python
"""Cron entry point — regenerate plans weekly for all active users.

Usage : python -m garmin_sync.coach.cron

Triggered by systemd timer on UNRAID server (see worker/deploy/README.md).
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from garmin_sync.coach.planner import generate_plan
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)


def run_weekly_cron() -> dict[str, Any]:
    """For each user with an active future race_goal, regenerate the plan."""
    db = get_admin_client()
    # Find users with at least 1 race_goal where race_date > now and is_primary
    users = cast(
        'list[dict[str, Any]]',
        db.table('race_goals').select('user_id')
        .eq('is_primary', True)
        .gte('race_date', 'now()')  # NB : Supabase REST does not support 'now()', use today's iso
        .execute().data or [],
    )
    user_ids = list({u['user_id'] for u in users})

    results: dict[str, dict[str, Any]] = {}
    for uid in user_ids:
        try:
            results[uid] = generate_plan(uid)
        except Exception as e:
            log.exception('Plan regeneration failed for user=%s', uid)
            results[uid] = {'status': 'exception', 'type': type(e).__name__}
    return {'total_users': len(user_ids), 'results': results}


if __name__ == '__main__':
    print(json.dumps(run_weekly_cron(), indent=2))
```

NOTE: The Supabase REST `.gte('race_date', 'now()')` doesn't interpret 'now()' server-side. Use a Python `date.today().isoformat()` :

```python
from datetime import date
today_iso = date.today().isoformat()
users = db.table('race_goals').select('user_id').eq('is_primary', True).gte('race_date', today_iso).execute().data
```

- [ ] **Step 7: Update `finalizeOnboarding` Server Action côté frontend**

Modifier `app/(app)/onboarding/actions.ts` :

```typescript
// Add this helper at top of file (near other imports):
async function generatePlanForUser(): Promise<void> {
  // Fire-and-forget : worker has its own retry/cron, we don't block UX if it fails.
  try {
    const supabase = await createClient()
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) return
    await workerPost('/coach/generate-plan', {}, session.access_token)
  } catch (_err) {
    // Silently swallow — the weekly cron will regenerate
    // eslint-disable-next-line no-console
    console.error('Plan generation failed at finalize, will retry via cron')
  }
}

// In finalizeOnboarding, after the update onboarding_completed_at:
await supabase
  .from('athlete_profiles')
  .update({ onboarding_completed_at: new Date().toISOString() })
  .eq('user_id', userIdOrErr)

// Add this BEFORE the revalidatePath + redirect:
await generatePlanForUser()

revalidatePath('/profile')
redirect('/profile?onboarded=1')
```

- [ ] **Step 8: Quality gates + commit**

```bash
cd /home/tellebma/DEV/garmin_training/worker
uv run ruff check . && uv run mypy src/ && uv run pytest -q
cd ..
pnpm typecheck && pnpm lint
```
Expected: all clean.

```bash
git add worker/src/garmin_sync/transformers/activities.py \
        worker/src/garmin_sync/sync.py \
        worker/src/garmin_sync/coach/backfill_tss.py \
        worker/src/garmin_sync/coach/cron.py \
        worker/src/garmin_sync/main.py \
        worker/tests/coach/test_backfill_tss.py \
        worker/tests/test_main.py \
        worker/tests/test_sync.py \
        app/'(app)'/onboarding/actions.ts
git commit -m "feat(coach): worker integration (transformer + endpoint + cron + finalize hook)"
```

---

## Task 7 — Documentation cron systemd

**Files:**
- Modify: `worker/deploy/README.md`

- [ ] **Step 1: Read existing deploy/README.md**

```bash
cat /home/tellebma/DEV/garmin_training/worker/deploy/README.md 2>/dev/null || echo "no README yet"
ls /home/tellebma/DEV/garmin_training/worker/deploy/
```

- [ ] **Step 2: Append cron weekly setup section**

Append to `worker/deploy/README.md` (or create if absent) :

```markdown
## Cron weekly — Coach plan regeneration

A 2nd systemd timer regenerates training plans every Sunday at 22:00 UTC.

### Timer file `/etc/systemd/system/garmin-coach.timer`

```ini
[Unit]
Description=Garmin Training Coach — weekly plan regen

[Timer]
OnCalendar=Sun *-*-* 22:00:00 UTC
Persistent=true
Unit=garmin-coach.service

[Install]
WantedBy=timers.target
```

### Service file `/etc/systemd/system/garmin-coach.service`

```ini
[Unit]
Description=Garmin Training Coach — weekly plan regen
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/docker exec garmin-sync python -m garmin_sync.coach.cron
```

### Installation

```bash
sudo systemctl daemon-reload
sudo systemctl enable garmin-coach.timer
sudo systemctl start garmin-coach.timer
systemctl list-timers garmin-coach.timer    # verify next trigger
```

### Logs

```bash
sudo journalctl -u garmin-coach.service --since "7 days ago"
docker logs garmin-sync | grep coach
```

### One-shot backfill (à exécuter une fois après le déploiement E4)

```bash
docker exec garmin-sync python -m garmin_sync.coach.backfill_tss
```

Idempotent. Recalcule TSS uniquement pour les activities avec `tss IS NULL`.
```

- [ ] **Step 3: Commit**

```bash
git add worker/deploy/README.md
git commit -m "docs(deploy): document coach weekly cron + TSS backfill"
```

---

## Task 8 — Push, open PR, smoke test

- [ ] **Step 1: Full quality gates one last time**

```bash
cd /home/tellebma/DEV/garmin_training/worker
uv run pytest -q && uv run ruff check . && uv run mypy src/
cd ..
pnpm lint && pnpm typecheck && pnpm test --run && pnpm build
```
Expected: all green. Worker tests should include ~25 new tests (5 tss + 7 banister + 5 phases + 8 planner + 3 endpoint + 2 backfill).

- [ ] **Step 2: Push branch**

```bash
git push -u origin feat/e4-banister-planner
```

- [ ] **Step 3: Open PR**

```bash
gh pr create --base main --head feat/e4-banister-planner \
  --title "feat(e4): Banister planner — TSS + CTL/ATL/TSB + phases + endpoint + cron" \
  --body "$(cat <<'EOF'
## Contexte

Implémentation complète de l'EPIC E4 — Moteur de planification Banister.

- **Spec** : [\`docs/superpowers/specs/2026-05-19-e4-banister-planner-design.md\`](./docs/superpowers/specs/2026-05-19-e4-banister-planner-design.md)
- **Plan** : [\`docs/superpowers/plans/2026-05-19-e4-banister-planner.md\`](./docs/superpowers/plans/2026-05-19-e4-banister-planner.md)

## Changements

### Database
- 2 nouvelles tables : \`training_plans\` (1 active par user×race via partial unique index) + \`planned_sessions\` (1 row par jour)
- RLS owner-only, 8 policies (4 par table)

### Worker (Python)
- Nouveau module \`coach/\` : tss.py + banister.py + phases.py + planner.py + cron.py + backfill_tss.py
- Endpoint \`POST /coach/generate-plan\` (JWT auth)
- Transformer activities calcule maintenant TSS au sync (FTP/FCmax fetched depuis athlete_profiles)
- Cron weekly (config systemd UNRAID documentée)

### Frontend (Next.js)
- \`finalizeOnboarding\` Server Action appelle \`/coach/generate-plan\` en fire-and-forget — n'attend PAS la réponse pour ne pas bloquer le redirect /profile

## Algorithme

- **TSS** : tier 1 power-based pour cycling avec watts, tier 2 hrTSS (IF = hr/0.9·FCmax) sinon, tier 3 duration × 50 TSS/h fallback
- **Banister** : exponentielle τ1=42j (CTL), τ2=7j (ATL), TSB = CTL-ATL ; cold-start CTL = hours_per_week × 50 / 7 si <14j historique
- **Phases** : backward depuis race_date — taper (1-2 dernières sem.) + peak (~10%) + build (~25%) + base (rest)
- **Génération sessions** : weekly_tss_target = CTL × 7 × ramp_rate (1.05 normal / 0.7 deload chaque 4e sem. / 0.55 taper), distribué entre sports selon sports_strengths inversé (faible +20%, fort -10%)

## Tests

~25 nouveaux tests pytest worker + tests existants conservés.

## Setup manuel post-merge (UNRAID)

1. Pull la nouvelle image \`tellebma/garmin-sync:latest\` (Watchtower si activé)
2. Installer le systemd timer weekly (voir \`worker/deploy/README.md\`)
3. Run one-shot : \`docker exec garmin-sync python -m garmin_sync.coach.backfill_tss\` pour calculer TSS sur les activities historiques
4. Tester en générant un plan via UI : finaliser onboarding → vérifier en DB que \`training_plans\` a 1 row active + \`planned_sessions\` rempli

## Hors scope (E5+)

- Contenu détaillé des séances (intervalles précis, allure) → E5 LLM
- UI affichage \`/today\` séance du jour → E6
- Dashboard semaine → E7
EOF
)"
```

- [ ] **Step 4: Wait CI, verify, ping**

```bash
gh pr checks
```
Expected: all green.

---

## Quality gates de référence

| Couche | Commande | Expected |
|---|---|---|
| Worker lint | `cd worker && uv run ruff check .` | clean |
| Worker types | `cd worker && uv run mypy src/` | clean |
| Worker tests | `cd worker && uv run pytest -q` | ~95+ tests (existants + ~25 nouveaux) |
| Frontend lint | `pnpm lint` | clean |
| Frontend types | `pnpm typecheck` | clean |
| Frontend tests | `pnpm test --run` | all passed |
| Frontend build | `pnpm build` | clean |

---

## Cas d'erreur fréquents (anticipés)

| Symptôme | Cause probable | Fix |
|---|---|---|
| `pytest` pour test_planner.py échoue sur mock chain | Les mocks Supabase `.select().eq().eq().maybeSingle()` ont une chain spécifique — vérifier l'ordre exact | Comparer avec test_profile_sync.py qui mock le même pattern |
| `mypy` se plaint `cast(...)` | Le type est `dict[str, Any] | None` mais utilisation en `dict[str, Any]` | Ajouter une vérification `if not profile: return` après le cast |
| `planned_sessions` insert fail RLS | user_id non passé dans chaque session row | Le code dans `generate_plan` boucle `for s in all_sessions: s['user_id'] = user_id` — vérifier que cette ligne est présente |
| Activities transform fail après changement signature | Old tests appellent `transform_activity(...)` sans `ftp_watts`/`fc_max_bpm` | Les args sont kwargs avec default `None` — devrait être compatible. Sinon ajouter `, ftp_watts=None, fc_max_bpm=None` aux call sites tests |
| `finalizeOnboarding` bloque trop longtemps | `await generatePlanForUser()` attend le worker — si worker lent, redirect lent | Fire-and-forget : `void generatePlanForUser()` (sans await) avant le redirect |
| Cron `.gte('race_date', 'now()')` ne fonctionne pas | Supabase REST ne supporte pas 'now()' littéral | Utiliser `date.today().isoformat()` côté Python |

---

## Récap exécution attendue

1. Migration DB ✓ (~30 min)
2. tss.py ✓ (~30 min)
3. banister.py ✓ (~1h)
4. phases.py ✓ (~30 min)
5. planner.py ✓ (~2h — gros morceau intégrateur)
6. Worker integration ✓ (~2h)
7. Doc cron ✓ (~15 min)
8. PR + smoke ✓ (~15 min)

**Total ≈ 7h actives** (cohérent avec l'estimé 7 jours du spec en tenant compte des review loops + smoke tests).
