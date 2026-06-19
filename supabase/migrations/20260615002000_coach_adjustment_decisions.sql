-- Trace des décisions utilisateur sur les ajustements coach proposés.
-- Objectif : auditer acceptation/refus et éviter de reproposer le même ajustement.

create table if not exists public.coach_adjustment_decisions (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  planned_session_id uuid not null references public.planned_sessions(id) on delete cascade,
  original_session_type text,
  suggested_session_type text not null,
  decision text not null check (decision in ('accepted', 'ignored')),
  source text not null default 'daily_briefing',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint coach_adjustment_decisions_unique
    unique (user_id, planned_session_id, suggested_session_type)
);

create index if not exists coach_adjustment_decisions_user_session_idx
  on public.coach_adjustment_decisions (user_id, planned_session_id, updated_at desc);

alter table public.coach_adjustment_decisions enable row level security;

create policy "users read own coach adjustment decisions"
  on public.coach_adjustment_decisions for select
  using (auth.uid() = user_id);

create policy "users insert own coach adjustment decisions"
  on public.coach_adjustment_decisions for insert
  with check (auth.uid() = user_id);

create policy "users update own coach adjustment decisions"
  on public.coach_adjustment_decisions for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop trigger if exists trg_coach_adjustment_decisions_updated_at
  on public.coach_adjustment_decisions;
create trigger trg_coach_adjustment_decisions_updated_at
  before update on public.coach_adjustment_decisions
  for each row execute procedure public.touch_updated_at();

comment on table public.coach_adjustment_decisions is
  'Décisions utilisateur sur les ajustements coach proposés dans le briefing.';
comment on column public.coach_adjustment_decisions.decision is
  'accepted ou ignored, pour auditer et éviter les suggestions répétées.';
