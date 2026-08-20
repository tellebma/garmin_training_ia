-- E22.1 — Décomposition des activités multisport (triathlon / duathlon / aquathlon).
--
-- Une activité multisport arrive de Garmin comme UNE ligne `activities` agrégée
-- (sport normalisé en `brick`) : distance et allure moyennes y mélangent nage, vélo
-- et course, ce qui les rend inexploitables — notamment sur le calque de partage.
-- Cette table porte la décomposition, une ligne par segment, sans toucher aux
-- métriques du parent : le TSS et la charge restent calculés sur la seule ligne
-- `activities`, donc aucun risque de double comptage.

create table if not exists public.activity_segments (
  user_id uuid not null references auth.users(id) on delete cascade,
  -- Activité parent (multisport) dans `activities`.
  garmin_activity_id bigint not null,
  segment_index integer not null check (segment_index >= 0),
  -- Discipline canonique du segment : swim / bike / run / transition, ou la valeur
  -- Garmin telle quelle si elle n'est pas reconnue (le front dégrade proprement).
  sport text not null,
  -- Activité enfant Garmin correspondante, quand la décomposition en vient.
  garmin_child_activity_id bigint,
  start_time timestamptz,
  duration_s integer check (duration_s is null or duration_s >= 0),
  distance_m numeric(12,2) check (distance_m is null or distance_m >= 0),
  elevation_gain_m integer,
  hr_avg integer check (hr_avg is null or hr_avg between 30 and 240),
  pace_avg_s_per_km numeric(8,2) check (pace_avg_s_per_km is null or pace_avg_s_per_km >= 0),
  created_at timestamptz not null default now(),
  primary key (user_id, garmin_activity_id, segment_index)
);

create index if not exists activity_segments_activity_idx
  on public.activity_segments (user_id, garmin_activity_id, segment_index);

alter table public.activity_segments enable row level security;

create policy "users read own activity segments"
  on public.activity_segments for select
  using (auth.uid() = user_id);

comment on table public.activity_segments is
  'Segments (nage / vélo / course / transition) d''une activité multisport Garmin.';

-- Marqueur « décomposition déjà tentée », sur le modèle de `route_polyline` pour le GPS :
-- une activité multisport sans enfants exploitables ne doit pas être re-interrogée chez
-- Garmin à chaque cron.
alter table public.activities
  add column if not exists segments_checked_at timestamptz;

comment on column public.activities.segments_checked_at is
  'Date de la dernière tentative de décomposition multisport (NULL = jamais tentée).';
