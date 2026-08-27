-- E26 — Après-course : le cap se choisit une fois l'épreuve courue.
--
-- E23 s'arrêtait au débrief : rien ne disait un mot sur la course, rien ne demandait à
-- l'athlète ce qu'il voulait faire ensuite. E27 a donné à l'app un moteur pour continuer
-- sans objectif ; il manque l'endroit où l'athlète choisit.
--
-- Choix structurant : l'état vit sur `race_goals` (une course a UN seul après-course, la
-- table est déjà scopée par RLS et déjà lue par tous les écrans concernés), et la question
-- à poser est DÉRIVÉE par une requête — jamais un événement poussé par le worker. Le tag
-- course arrive par trois chemins (sync, backfill, tag manuel) : les trois auraient dû
-- penser à armer le prompt, et `backfill_races` aurait ouvert un « Bravo ! » sur des
-- épreuves de 2024.
--
-- Additif uniquement : contrat expand/contract respecté.

alter table public.race_goals
  add column if not exists post_race_choice text
    check (post_race_choice is null
           or post_race_choice in ('new_race', 'maintain', 'improve', 'dismissed')),
  add column if not exists post_race_answered_at timestamptz,
  add column if not exists post_race_prompt_snoozed_until date,
  add column if not exists post_race_prompt_count smallint not null default 0;

-- Pas de colonne `status` : elle serait redondante, donc désynchronisable.
-- `post_race_choice is not null` EST l'état « répondu » — même principe que
-- `activities.race_goal_id is not null` qui EST le tag course (E23).
comment on column public.race_goals.post_race_choice is
  'Cap choisi après cette course (E26). NULL = question encore ouverte, y compris quand '
  'le plan tourne déjà en maintien par défaut.';
comment on column public.race_goals.post_race_prompt_count is
  'Nombre de reports. À partir de 2, l''app n''ouvre plus de modale et laisse une '
  'bannière discrète : trois interruptions au maximum.';

-- =========================================
-- Répondre : le choix et son effet, dans le même appel
-- =========================================

create or replace function public.answer_post_race_prompt(
  p_race_goal_id uuid,
  p_choice text
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
  if p_choice not in ('new_race', 'maintain', 'improve', 'dismissed') then
    raise exception 'invalid post-race choice: %', p_choice;
  end if;

  -- `security definer` court-circuite RLS : la propriété se vérifie explicitement.
  update public.race_goals
     set post_race_choice = p_choice,
         post_race_answered_at = now()
   where id = p_race_goal_id
     and user_id = v_user;

  if not found then
    raise exception 'race goal not found';
  end if;

  -- Le cap est écrit dans le MÊME appel que le choix : deux allers-retours laisseraient,
  -- en cas d'échec entre les deux, un choix enregistré sans effet sur le plan.
  -- 'new_race' ne bascule rien ici : c'est l'écriture de la nouvelle course qui repasse
  -- le mode sur 'race' (trigger E27). 'dismissed' laisse le défaut s'appliquer.
  if p_choice in ('maintain', 'improve') then
    perform public.set_training_mode(p_choice);
  end if;
end;
$$;

-- =========================================
-- Reporter : la cadence vit dans la RPC, pas dans le client
-- =========================================

-- Le client ne doit pas pouvoir décider quand on le relance. J+2 au premier report,
-- J+5 ensuite — et au-delà de deux reports l'app cesse d'interrompre (la lecture côté
-- front bascule sur une bannière permanente).
create or replace function public.snooze_post_race_prompt(p_race_goal_id uuid)
returns date
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user uuid := auth.uid();
  v_count smallint;
  v_until date;
begin
  if v_user is null then
    raise exception 'not authorized';
  end if;

  select post_race_prompt_count into v_count
    from public.race_goals
   where id = p_race_goal_id and user_id = v_user
   for update;

  if v_count is null then
    raise exception 'race goal not found';
  end if;

  v_count := v_count + 1;
  v_until := current_date + (case when v_count = 1 then 2 else 5 end);

  update public.race_goals
     set post_race_prompt_count = v_count,
         post_race_prompt_snoozed_until = v_until
   where id = p_race_goal_id
     and user_id = v_user;

  return v_until;
end;
$$;

-- Postgres accorde EXECUTE à PUBLIC par défaut : le `grant` seul ne restreint rien,
-- il faut révoquer explicitement (piège SEC-2).
revoke execute on function public.answer_post_race_prompt(uuid, text) from public, anon;
revoke execute on function public.snooze_post_race_prompt(uuid) from public, anon;
grant execute on function public.answer_post_race_prompt(uuid, text) to authenticated;
grant execute on function public.snooze_post_race_prompt(uuid) to authenticated;
