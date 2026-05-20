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
