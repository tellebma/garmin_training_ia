-- E23 — Vue course : rattachement activité → course, résultats officiels, tag manuel.
--
-- Une course n'existait qu'AVANT l'épreuve (`race_goals` + séance du jour J). Après,
-- l'activité retombait dans l'historique comme une sortie ordinaire : rien ne disait que
-- c'était une course, et les données propres à l'épreuve (temps officiel, classement,
-- transitions chronométrées) n'avaient nulle part où vivre.
--
-- Une course EST un `race_goal` : pas de nouvelle entité, pas de double vérité. Une épreuve
-- passée est un race_goal `is_primary = false` ; une épreuve jamais planifiée se crée
-- rétroactivement via les policies d'insert existantes.
--
-- Additif uniquement (colonnes nullable, table nouvelle) : contrat expand/contract respecté.

-- =========================================
-- 1. Rattachement activité → course
-- =========================================

-- Pas de colonne `is_race` séparée : `race_goal_id is not null` EST le tag. Une seule
-- source de vérité, donc pas d'état incohérent (`is_race` vrai sans course rattachée).
alter table public.activities
  add column if not exists race_goal_id uuid
    references public.race_goals(id) on delete set null,
  add column if not exists race_tag_source text
    check (race_tag_source is null or race_tag_source in ('auto', 'manual'));

comment on column public.activities.race_goal_id is
  'Course (race_goals) à laquelle cette activité appartient. NULL = activité ordinaire.';
comment on column public.activities.race_tag_source is
  'Origine du tag : auto (détection worker) ou manual (décision de l''athlète). '
  'La détection automatique ne réécrit jamais une ligne manual.';

create index if not exists activities_user_race_idx
  on public.activities (user_id, race_goal_id)
  where race_goal_id is not null;

-- =========================================
-- 2. Résultats officiels et ressenti — une ligne par course
-- =========================================

create table if not exists public.race_results (
  race_goal_id uuid primary key references public.race_goals(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,

  -- Chronos officiels (secondes). La montre démarre et s'arrête toujours un peu à côté
  -- de la ligne : quand un temps officiel existe, il prime sur le temps Garmin.
  official_time_s integer check (official_time_s is null or official_time_s between 60 and 172800),
  swim_time_s integer check (swim_time_s is null or swim_time_s between 0 and 86400),
  t1_time_s integer check (t1_time_s is null or t1_time_s between 0 and 7200),
  bike_time_s integer check (bike_time_s is null or bike_time_s between 0 and 86400),
  t2_time_s integer check (t2_time_s is null or t2_time_s between 0 and 7200),
  run_time_s integer check (run_time_s is null or run_time_s between 0 and 86400),

  -- Classements (officiels ou relevés sur la feuille de résultats).
  overall_rank integer check (overall_rank is null or overall_rank >= 1),
  overall_finishers integer check (overall_finishers is null or overall_finishers >= 1),
  category text check (category is null or char_length(category) <= 40),
  category_rank integer check (category_rank is null or category_rank >= 1),
  category_finishers integer check (category_finishers is null or category_finishers >= 1),

  bib_number text check (bib_number is null or char_length(bib_number) <= 20),
  results_url text check (results_url is null or results_url ~ '^https?://'),

  -- Contexte que la montre ne mesure pas.
  weather text check (weather is null or char_length(weather) <= 500),
  nutrition text check (nutrition is null or char_length(nutrition) <= 1000),
  gear text check (gear is null or char_length(gear) <= 500),
  incidents text check (incidents is null or char_length(incidents) <= 1000),
  comment text check (comment is null or char_length(comment) <= 2000),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.race_results is
  'Résultats officiels et ressenti d''une course (E23.5 V1 : saisie manuelle ; '
  'l''import depuis les plateformes de chronométrage alimentera les mêmes colonnes).';

create index if not exists race_results_user_idx on public.race_results (user_id);

alter table public.race_results enable row level security;

drop policy if exists "users read own race_results"   on public.race_results;
drop policy if exists "users insert own race_results" on public.race_results;
drop policy if exists "users update own race_results" on public.race_results;
drop policy if exists "users delete own race_results" on public.race_results;

create policy "users read own race_results" on public.race_results for select
  using (auth.uid() = user_id);
create policy "users insert own race_results" on public.race_results for insert
  with check (auth.uid() = user_id);
create policy "users update own race_results" on public.race_results for update
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "users delete own race_results" on public.race_results for delete
  using (auth.uid() = user_id);

drop trigger if exists trg_race_results_updated_at on public.race_results;
create trigger trg_race_results_updated_at
  before update on public.race_results
  for each row execute procedure public.touch_updated_at();

-- =========================================
-- 3. Tag manuel — RPC (RLS sur `activities` n'autorise que la lecture côté client)
-- =========================================

create or replace function public.set_activity_race(
  p_activity_id uuid,
  p_race_goal_id uuid
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user uuid := auth.uid();
begin
  if v_user is null then
    raise exception 'not authorized';
  end if;

  -- Les deux objets doivent appartenir à l'appelant : `security definer` court-circuite
  -- RLS, la vérification de propriété est donc explicite ici.
  if not exists (
    select 1 from public.race_goals g where g.id = p_race_goal_id and g.user_id = v_user
  ) then
    raise exception 'race goal not found';
  end if;

  update public.activities
     set race_goal_id = p_race_goal_id,
         race_tag_source = 'manual'
   where id = p_activity_id
     and user_id = v_user;

  if not found then
    raise exception 'activity not found';
  end if;
end;
$$;

create or replace function public.clear_activity_race(p_activity_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user uuid := auth.uid();
begin
  if v_user is null then
    raise exception 'not authorized';
  end if;

  -- `race_tag_source = 'manual'` est conservé : c'est ce marqueur qui empêche la
  -- détection automatique de re-taguer au prochain sync une activité écartée à la main.
  update public.activities
     set race_goal_id = null,
         race_tag_source = 'manual'
   where id = p_activity_id
     and user_id = v_user;

  if not found then
    raise exception 'activity not found';
  end if;
end;
$$;

-- Postgres accorde EXECUTE à PUBLIC par défaut (anon et authenticated en sont membres) :
-- le `grant` seul ne restreint rien, il faut révoquer explicitement (piège SEC-2).
revoke execute on function public.set_activity_race(uuid, uuid) from public, anon;
revoke execute on function public.clear_activity_race(uuid) from public, anon;
grant execute on function public.set_activity_race(uuid, uuid) to authenticated;
grant execute on function public.clear_activity_race(uuid) to authenticated;
