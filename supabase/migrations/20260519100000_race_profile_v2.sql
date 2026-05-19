-- 20260519100000_race_profile_v2.sql
-- Race Profile v2 : multi-discipline + per-leg distance/elevation

-- Drop ancien check (enum mono-discipline) si présent
alter table public.race_goals drop constraint if exists race_goals_race_distance_check;

-- Rename : race_distance → discipline (parent type)
alter table public.race_goals rename column race_distance to discipline;

-- Nouveau check sur disciplines parent (étendu)
alter table public.race_goals
  add constraint race_goals_discipline_check
  check (discipline in ('triathlon','duathlon','aquathlon','run','bike','swim','autre'));

-- Nouvelles colonnes pour le profil géométrique
alter table public.race_goals
  add column if not exists total_distance_km numeric(7,2)
    check (total_distance_km is null or (total_distance_km > 0 and total_distance_km <= 1000)),
  add column if not exists total_elevation_gain_m integer
    check (total_elevation_gain_m is null or (total_elevation_gain_m >= 0 and total_elevation_gain_m <= 20000)),
  add column if not exists legs jsonb not null default '[]'::jsonb;

comment on column public.race_goals.discipline is
  'Type de course parent : triathlon, duathlon, aquathlon, run, bike, swim, autre.';
comment on column public.race_goals.total_distance_km is
  'Distance totale en km (somme des legs, mise en cache pour query rapide).';
comment on column public.race_goals.total_elevation_gain_m is
  'Dénivelé positif total en mètres (somme des legs, mise en cache).';
comment on column public.race_goals.legs is
  'Détail des segments : [{order:int, discipline:swim|bike|run, distance_km:number, elevation_gain_m:int}].';
