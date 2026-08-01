-- 20260801140000_planned_sessions_pma_sprint.sql
-- Audit coach #121 : le planner émet des types 'pma' et 'sprint' (peak / build
-- avancé) mais le check de planned_sessions ne les autorisait pas. Le bug du
-- plafond d'intensité (min global des niveaux) masquait le problème : aucune
-- séance dure n'était jamais générée, donc la contrainte ne se déclenchait pas.
-- Une fois l'intensité débloquée par discipline, l'insert échouerait sans ça.

alter table public.planned_sessions
  drop constraint if exists planned_sessions_session_type_check;

alter table public.planned_sessions
  add constraint planned_sessions_session_type_check
  check (session_type in (
    'endurance','threshold','intervals','long','recovery','pma','sprint','race','rest'
  ));
