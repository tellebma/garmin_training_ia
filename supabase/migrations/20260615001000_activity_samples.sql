-- Samples temporels d'activité Garmin.
-- Permet les graphes détaillés FC / altitude / allure / puissance / cadence.

create table if not exists public.activity_samples (
  user_id uuid not null references auth.users(id) on delete cascade,
  garmin_activity_id bigint not null,
  sample_index integer not null check (sample_index >= 0),
  sample_time timestamptz,
  elapsed_s numeric(10,2) check (elapsed_s is null or elapsed_s >= 0),
  distance_m numeric(12,2) check (distance_m is null or distance_m >= 0),
  elevation_m numeric(8,2),
  heart_rate_bpm integer check (heart_rate_bpm is null or heart_rate_bpm between 30 and 240),
  power_w integer check (power_w is null or power_w between 0 and 2000),
  cadence_rpm integer check (cadence_rpm is null or cadence_rpm between 0 and 260),
  speed_m_s numeric(8,3) check (speed_m_s is null or speed_m_s >= 0),
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, garmin_activity_id, sample_index)
);

create index if not exists activity_samples_activity_idx
  on public.activity_samples (user_id, garmin_activity_id, sample_index);

alter table public.activity_samples enable row level security;

create policy "users read own activity samples"
  on public.activity_samples for select
  using (auth.uid() = user_id);

comment on table public.activity_samples is
  'Samples temporels extraits des détails Garmin pour tracer FC, altitude, allure, puissance et cadence.';
