-- 20260518000000_e3_onboarding.sql
-- E3 — Profile & Onboarding : nouvelle table race_goals + 2 colonnes athlete_profiles

-- =========================================
-- Table: race_goals
-- 1→N : un user peut avoir plusieurs courses (1 active "is_primary", N archivées)
-- =========================================
create table if not exists public.race_goals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  race_date date not null,
  race_distance text not null
    check (race_distance in ('sprint','olympique','half_ironman','ironman','autre')),
  name text,
  location text,
  target_time_seconds integer
    check (target_time_seconds is null or target_time_seconds between 600 and 86400),
  is_primary boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists race_goals_user_primary_idx
  on public.race_goals (user_id, is_primary) where is_primary;
create unique index if not exists race_goals_one_primary_per_user
  on public.race_goals (user_id) where is_primary;

alter table public.race_goals enable row level security;

drop policy if exists "users read own race_goals"   on public.race_goals;
drop policy if exists "users insert own race_goals" on public.race_goals;
drop policy if exists "users update own race_goals" on public.race_goals;
drop policy if exists "users delete own race_goals" on public.race_goals;

create policy "users read own race_goals"   on public.race_goals for select
  using (auth.uid() = user_id);
create policy "users insert own race_goals" on public.race_goals for insert
  with check (auth.uid() = user_id);
create policy "users update own race_goals" on public.race_goals for update
  using (auth.uid() = user_id);
create policy "users delete own race_goals" on public.race_goals for delete
  using (auth.uid() = user_id);

drop trigger if exists touch_race_goals_updated_at on public.race_goals;
drop trigger if exists trg_race_goals_updated_at on public.race_goals;
create trigger trg_race_goals_updated_at before update on public.race_goals
  for each row execute procedure public.touch_updated_at();

-- =========================================
-- Alter: athlete_profiles
-- Ajouts: hours_per_week + garmin_synced_at
-- =========================================
alter table public.athlete_profiles
  add column if not exists hours_per_week integer
    check (hours_per_week is null or hours_per_week between 1 and 30),
  add column if not exists garmin_synced_at timestamptz;

comment on column public.athlete_profiles.hours_per_week is
  'Heures d''entraînement disponibles par semaine (1-30).';
comment on column public.athlete_profiles.garmin_synced_at is
  'Last successful auto-fetch from Garmin user-settings (FTP/VO2max/FCmax).';
