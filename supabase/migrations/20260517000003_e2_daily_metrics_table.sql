-- E2 — daily metrics: one row per (user, date)
create table public.daily_metrics (
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  resting_hr integer check (resting_hr is null or resting_hr between 30 and 120),
  body_battery_low integer check (body_battery_low is null or body_battery_low between 0 and 100),
  body_battery_high integer check (body_battery_high is null or body_battery_high between 0 and 100),
  stress_avg integer check (stress_avg is null or stress_avg between 0 and 100),
  steps integer check (steps is null or steps >= 0),
  active_calories integer check (active_calories is null or active_calories >= 0),
  total_calories integer check (total_calories is null or total_calories >= 0),
  readiness_score numeric(5,2) check (readiness_score is null or readiness_score between 0 and 100),
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, date)
);

create index daily_metrics_user_date_idx on public.daily_metrics (user_id, date desc);

alter table public.daily_metrics enable row level security;

create policy "users read own daily_metrics"
  on public.daily_metrics for select
  using (auth.uid() = user_id);

create trigger trg_daily_metrics_updated_at
  before update on public.daily_metrics
  for each row execute procedure public.touch_updated_at();
