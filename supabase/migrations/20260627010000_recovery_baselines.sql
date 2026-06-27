-- 20260627010000_recovery_baselines.sql
-- E9.3: baselines de récupération personnelles, matérialisées au sync.
-- Une ligne par user ; le worker (service_role) écrit, l'user lit la sienne.

create table if not exists public.recovery_baselines (
  user_id uuid primary key references auth.users(id) on delete cascade,
  computed_at timestamptz not null default now(),
  hrv jsonb,
  resting_hr jsonb,
  sleep jsonb,
  stress jsonb,
  body_battery jsonb,
  raw_meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.recovery_baselines enable row level security;

drop policy if exists "recovery_baselines_select_own" on public.recovery_baselines;

create policy "recovery_baselines_select_own"
  on public.recovery_baselines for select
  using (auth.uid() = user_id);

comment on table public.recovery_baselines is
  'E9.3 — baselines de récupération (HRV, FC repos, sommeil, stress, Body Battery) matérialisées au sync. Service-role écrit, user lit la sienne.';
