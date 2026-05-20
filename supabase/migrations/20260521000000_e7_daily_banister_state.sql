-- 20260521000000_e7_daily_banister_state.sql
-- E7 — Table matérialisée Banister CTL/ATL/TSB par jour pour reads frontend rapides.

create table if not exists public.daily_banister_state (
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  ctl numeric(6,2) not null check (ctl >= 0),
  atl numeric(6,2) not null check (atl >= 0),
  tsb numeric(6,2) not null,
  daily_tss numeric(6,2) check (daily_tss is null or daily_tss >= 0),
  computed_at timestamptz not null default now(),
  primary key (user_id, date)
);

create index if not exists daily_banister_user_date_idx
  on public.daily_banister_state (user_id, date desc);

alter table public.daily_banister_state enable row level security;

drop policy if exists "users read own banister" on public.daily_banister_state;
create policy "users read own banister" on public.daily_banister_state for select
  using (auth.uid() = user_id);
-- Pas de policy INSERT/UPDATE/DELETE : seul le service-role (cron worker) écrit.

comment on table public.daily_banister_state is
  'Banister CTL/ATL/TSB matérialisé par jour. Recalculé par le cron sync Garmin daily.';
