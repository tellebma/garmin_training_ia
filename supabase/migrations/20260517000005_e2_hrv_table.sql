-- E2 — HRV — one row per (user, date)
create table public.hrv (
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  hrv_rmssd numeric(6,2) check (hrv_rmssd is null or hrv_rmssd between 0 and 300),
  hrv_status text check (
    hrv_status is null or hrv_status in ('balanced', 'unbalanced', 'low', 'poor', 'no_status')
  ),
  hrv_weekly_avg numeric(6,2),
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, date)
);

create index hrv_user_date_idx on public.hrv (user_id, date desc);

alter table public.hrv enable row level security;

create policy "users read own hrv"
  on public.hrv for select
  using (auth.uid() = user_id);
