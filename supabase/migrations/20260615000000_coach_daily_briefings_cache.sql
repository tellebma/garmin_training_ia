-- Cache des briefings quotidiens coach.
-- Objectif : éviter de recalculer toute l'analyse à chaque ouverture de /today.

create table if not exists public.coach_daily_briefings (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  briefing_date date not null,
  logic_version text not null,
  payload jsonb not null,
  computed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint coach_daily_briefings_user_date_unique unique (user_id, briefing_date)
);

create index if not exists coach_daily_briefings_user_date_idx
  on public.coach_daily_briefings (user_id, briefing_date desc);

alter table public.coach_daily_briefings enable row level security;

-- Pas d'accès client direct pour l'instant : le worker service_role lit et écrit ce cache.
-- La future UI peut exposer un accès lecture utilisateur si on veut afficher computed_at.

drop trigger if exists trg_coach_daily_briefings_updated_at
  on public.coach_daily_briefings;
create trigger trg_coach_daily_briefings_updated_at
  before update on public.coach_daily_briefings
  for each row execute procedure public.touch_updated_at();

comment on table public.coach_daily_briefings is
  'Cache JSONB du briefing quotidien coach par utilisateur et par date.';
comment on column public.coach_daily_briefings.logic_version is
  'Version de la logique coach utilisée pour invalider les anciens payloads.';
comment on column public.coach_daily_briefings.payload is
  'Payload sérialisé retourné par /coach/daily-briefing.';
