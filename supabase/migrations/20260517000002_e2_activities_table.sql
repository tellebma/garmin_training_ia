-- E2 — activities table — one row per Garmin activity
create table public.activities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  garmin_activity_id bigint not null,
  start_time timestamptz not null,
  sport text not null,
  sub_sport text,
  duration_s integer not null check (duration_s >= 0),
  distance_m numeric(10,2) check (distance_m is null or distance_m >= 0),
  tss numeric(6,2) check (tss is null or tss >= 0),
  hr_avg integer check (hr_avg is null or hr_avg between 30 and 240),
  hr_max integer check (hr_max is null or hr_max between 30 and 240),
  power_avg integer check (power_avg is null or power_avg between 0 and 2000),
  power_max integer check (power_max is null or power_max between 0 and 2000),
  pace_avg_s_per_km numeric(6,2),
  elevation_gain_m integer,
  calories integer,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (user_id, garmin_activity_id)
);

create index activities_user_start_idx on public.activities (user_id, start_time desc);
create index activities_user_sport_idx on public.activities (user_id, sport);

alter table public.activities enable row level security;

create policy "users read own activities"
  on public.activities for select
  using (auth.uid() = user_id);
