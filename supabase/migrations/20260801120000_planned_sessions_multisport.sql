-- 20260801120000_planned_sessions_multisport.sql
-- Audit coach #135 : la journée de course d'un triathlon était typée
-- sport = 'swim' (premier leg) — l'athlète voyait sa course affichée comme une
-- séance de natation. Le planner écrit désormais la discipline du race_goal
-- ('triathlon' / 'duathlon' / 'aquathlon') sur la séance 'race' : le check de
-- planned_sessions doit accepter ces valeurs.

alter table public.planned_sessions
  drop constraint if exists planned_sessions_sport_check;

alter table public.planned_sessions
  add constraint planned_sessions_sport_check
  check (sport in (
    'swim','bike','run','brick','rest','triathlon','duathlon','aquathlon'
  ));
