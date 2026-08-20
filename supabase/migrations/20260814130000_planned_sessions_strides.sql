-- 20260814130000_planned_sessions_strides.sql
-- Audit qualité #165 : le niveau déclaré (1 ou 2) interdisait TOUTE séance de
-- qualité, dans toutes les phases. Le planner module désormais le DOSAGE au lieu
-- de fermer l'accès, et introduit un type de qualité léger accessible à tous les
-- niveaux dès la phase base : 'strides' (côtes courtes / accélérations).
-- Sans cette migration, l'insert des séances planifiées échouerait sur le check.

alter table public.planned_sessions
  drop constraint if exists planned_sessions_session_type_check;

alter table public.planned_sessions
  add constraint planned_sessions_session_type_check
  check (session_type in (
    'endurance','threshold','intervals','long','recovery','pma','sprint','strides','race','rest'
  ));
