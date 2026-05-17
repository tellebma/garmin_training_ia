-- E2 — sleep — one row per (user, date)
create table public.sleep (
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  sleep_duration_s integer check (sleep_duration_s is null or sleep_duration_s between 0 and 86400),
  sleep_score integer check (sleep_score is null or sleep_score between 0 and 100),
  deep_sleep_s integer,
  light_sleep_s integer,
  rem_sleep_s integer,
  awake_s integer,
  bedtime timestamptz,
  wake_time timestamptz,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, date)
);

create index sleep_user_date_idx on public.sleep (user_id, date desc);

alter table public.sleep enable row level security;

create policy "users read own sleep"
  on public.sleep for select
  using (auth.uid() = user_id);
