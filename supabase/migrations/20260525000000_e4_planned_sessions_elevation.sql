-- 20260525000000_e4_planned_sessions_elevation.sql
-- E4 follow-up: per-session target elevation gain. Populated by the planner
-- only when the race has significant per-sport elevation (>300m bike, >100m run).

alter table public.planned_sessions
  add column if not exists target_elevation_gain_m integer
    check (target_elevation_gain_m is null or (target_elevation_gain_m >= 0 and target_elevation_gain_m <= 5000));

comment on column public.planned_sessions.target_elevation_gain_m is
  'Cible D+ pour la séance (mètres). NULL = pas de cible (course plate ou sport sans dénivelé).';
