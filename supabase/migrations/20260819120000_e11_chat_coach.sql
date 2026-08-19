-- 20260819120000_e11_chat_coach.sql
-- E11 — Chat coach contextuel (tool calling).
--
-- Le chat n'injecte pas les métriques dans le prompt : le LLM appelle des outils
-- bornés côté worker, qui lisent la base et ne renvoient que des agrégats. Cette
-- migration pose la persistance des conversations, étend le rate limit existant
-- et ajoute le garde-fou budgétaire.
--
-- Choix de conception : le worker (service_role) est seul à écrire. Le client ne
-- fait que lire ses propres conversations et les supprimer. Aucune écriture
-- client — sinon un utilisateur pourrait forger des messages `assistant` et
-- empoisonner le contexte renvoyé au modèle au tour suivant.

-- ---------------------------------------------------------------------------
-- 1. Conversations
-- ---------------------------------------------------------------------------

create table if not exists public.coach_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null default 'Nouvelle conversation',
  last_message_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists coach_conversations_user_last_msg_idx
  on public.coach_conversations (user_id, last_message_at desc);

alter table public.coach_conversations enable row level security;

create policy coach_conversations_select_own
  on public.coach_conversations for select
  using (auth.uid() = user_id);

-- Suppression autorisée (l'utilisateur doit pouvoir effacer son historique :
-- il contient ses données de santé). Les messages tombent par cascade.
create policy coach_conversations_delete_own
  on public.coach_conversations for delete
  using (auth.uid() = user_id);

drop trigger if exists trg_coach_conversations_updated_at on public.coach_conversations;
create trigger trg_coach_conversations_updated_at
  before update on public.coach_conversations
  for each row execute procedure public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- 2. Messages
-- ---------------------------------------------------------------------------

create table if not exists public.coach_messages (
  id bigserial primary key,
  conversation_id uuid not null
    references public.coach_conversations(id) on delete cascade,
  -- Dénormalisé depuis la conversation : permet une policy RLS sans jointure et
  -- un index direct. Cohérence garantie par le worker (seul écrivain).
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'tool')),
  content text,
  -- Outils demandés par le modèle sur ce tour (role='assistant'), pour audit :
  -- [{"name": "get_form_state", "arguments": {...}}]
  tool_calls jsonb,
  -- Nom de l'outil exécuté (role='tool') et taille du résultat avant troncature,
  -- pour repérer les outils qui gonflent le contexte.
  tool_name text,
  tool_result_chars integer,
  created_at timestamptz not null default now()
);

create index if not exists coach_messages_conversation_idx
  on public.coach_messages (conversation_id, id);

create index if not exists coach_messages_user_created_idx
  on public.coach_messages (user_id, created_at desc);

alter table public.coach_messages enable row level security;

create policy coach_messages_select_own
  on public.coach_messages for select
  using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 3. Rate limit : nouvelle action 'chat'
-- ---------------------------------------------------------------------------

alter table public.coach_rate_limits
  drop constraint if exists coach_rate_limits_action_check;

alter table public.coach_rate_limits
  add constraint coach_rate_limits_action_check
  check (action in ('ensure_sessions', 'regenerate_session', 'daily_briefing', 'chat'));

-- ---------------------------------------------------------------------------
-- 4. Garde-fou budgétaire
-- ---------------------------------------------------------------------------
--
-- Un compteur d'appels ne protège de rien sur un chat : 20 messages courts
-- coûtent ~$0.03, 20 messages en fin de longue conversation coûtent ~$1.60, et
-- le compteur voit la même chose. Le quota est donc exprimé en dollars, lus
-- depuis llm_usage qui trace déjà chaque appel.
--
-- p_user_id NULL => dépense globale de l'application (plafond app-level).

create or replace function public.coach_llm_spend_usd(
  p_since timestamptz,
  p_user_id uuid default null
)
returns numeric
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(sum(cost_usd), 0)::numeric
  from public.llm_usage
  where created_at >= p_since
    and (p_user_id is null or user_id = p_user_id);
$$;

-- SEC-3 : Postgres accorde EXECUTE à PUBLIC par défaut, et anon/authenticated
-- sont membres de PUBLIC. Un `grant to service_role` seul ne restreint rien —
-- la fonction resterait appelable via /rest/v1/rpc/ avec un p_user_id choisi
-- par l'appelant, ce qui divulguerait la dépense LLM d'un autre athlète.
revoke execute on function public.coach_llm_spend_usd(timestamptz, uuid)
  from public, anon, authenticated;
grant execute on function public.coach_llm_spend_usd(timestamptz, uuid)
  to service_role;

-- ---------------------------------------------------------------------------
-- 5. Profil d'activité agrégé — la condition de viabilité du chat
-- ---------------------------------------------------------------------------
--
-- Une sortie longue porte plusieurs milliers de lignes dans activity_samples.
-- Renvoyées brutes au modèle, c'est ~150 000 tokens pour un seul appel d'outil —
-- et ce résultat est réinjecté dans chaque tour suivant de la conversation.
--
-- Cette RPC fait l'agrégation côté base : N tranches d'effectif égal (ntile),
-- avec altitude, FC et vitesse moyennes. Une trentaine de lignes suffisent à
-- répondre à « où ai-je cassé dans la montée ». Le nombre de tranches est borné
-- ici, en SQL : le modèle ne peut pas le contourner en demandant p_buckets=5000.

create or replace function public.coach_activity_profile(
  p_user_id uuid,
  p_activity_id uuid,
  p_buckets integer default 20
)
returns table (
  bucket integer,
  t_start_min numeric,
  t_end_min numeric,
  km_start numeric,
  km_end numeric,
  elevation_min integer,
  elevation_max integer,
  hr_avg integer,
  speed_kmh numeric
)
language sql
stable
security definer
set search_path = public
as $$
  with bounded as (
    select least(greatest(coalesce(p_buckets, 20), 4), 30) as n
  ),
  act as (
    select a.garmin_activity_id
    from public.activities a
    where a.id = p_activity_id
      and a.user_id = p_user_id
  ),
  sliced as (
    select
      s.elapsed_s,
      s.distance_m,
      s.elevation_m,
      s.heart_rate_bpm,
      s.speed_m_s,
      ntile((select n from bounded)) over (order by s.sample_index) as b
    from public.activity_samples s
    where s.garmin_activity_id = (select garmin_activity_id from act)
      and s.user_id = p_user_id
  )
  select
    b::integer,
    round(min(elapsed_s) / 60.0, 1),
    round(max(elapsed_s) / 60.0, 1),
    round(min(distance_m) / 1000.0, 2),
    round(max(distance_m) / 1000.0, 2),
    round(min(elevation_m))::integer,
    round(max(elevation_m))::integer,
    round(avg(heart_rate_bpm))::integer,
    round(avg(speed_m_s) * 3.6, 1)
  from sliced
  group by b
  order by b;
$$;

revoke execute on function public.coach_activity_profile(uuid, uuid, integer)
  from public, anon, authenticated;
grant execute on function public.coach_activity_profile(uuid, uuid, integer)
  to service_role;

-- ---------------------------------------------------------------------------
-- 6. Kill switch
-- ---------------------------------------------------------------------------

insert into public.feature_flags (key, enabled, description)
values (
  'chat_enabled',
  false,
  'Coupe le chat coach (E11). Basculé automatiquement à false si le budget LLM mensuel global est dépassé.'
)
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- Commentaires
-- ---------------------------------------------------------------------------

comment on table public.coach_conversations is
  'Conversations du chat coach (E11). Écriture service-role uniquement ; l''utilisateur lit et supprime les siennes.';
comment on table public.coach_messages is
  'Messages du chat coach, y compris les tours d''outils (role=tool) pour audit des données transmises au LLM.';
comment on column public.coach_messages.tool_calls is
  'Outils demandés par le modèle sur ce tour, pour auditer a posteriori quelles données sont sorties.';
comment on column public.coach_messages.tool_result_chars is
  'Taille du résultat d''outil avant troncature — sert à repérer les outils qui gonflent le contexte.';
comment on function public.coach_activity_profile is
  'Profil d''une activité en tranches agrégées (ntile, 4-30 bornées en SQL). Évite de sortir des milliers de samples bruts vers le LLM. Service-role only.';
comment on function public.coach_llm_spend_usd is
  'Dépense LLM en USD depuis p_since, pour un user ou globale (p_user_id NULL). Service-role only.';
