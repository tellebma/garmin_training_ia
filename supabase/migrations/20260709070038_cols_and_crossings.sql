-- Référentiel global des cols (partagé entre users, alimenté depuis OSM Overpass).
create table public.cols (
  id uuid primary key default gen_random_uuid(),
  osm_id bigint not null unique,
  name text not null,
  latitude numeric(9, 6) not null
    check (latitude between -90 and 90),
  longitude numeric(9, 6) not null
    check (longitude between -180 and 180),
  elevation_m integer,
  fetched_at timestamptz not null default now()
);

alter table public.cols enable row level security;

create policy "authenticated users read cols"
  on public.cols for select
  to authenticated
  using (true);

comment on table public.cols is
  'Référentiel global des cols (mountain_pass OSM), alimenté par le worker via Overpass API. Écriture service-role uniquement.';

-- Franchissements détectés par activité (au plus 1 par activité + col).
create table public.col_crossings (
  user_id uuid not null references auth.users(id) on delete cascade,
  col_id uuid not null references public.cols(id) on delete cascade,
  garmin_activity_id bigint not null,
  crossed_at timestamptz not null,
  min_distance_m numeric(6, 1) not null check (min_distance_m >= 0),
  primary key (user_id, col_id, garmin_activity_id)
);

create index col_crossings_user_col_idx
  on public.col_crossings (user_id, col_id);

alter table public.col_crossings enable row level security;

create policy "users read own col crossings"
  on public.col_crossings for select
  using (auth.uid() = user_id);

comment on table public.col_crossings is
  'Franchissements de cols détectés par proximité GPS (<=150m), calculés par le worker. Au plus 1 ligne par (user, col, activité).';

-- Domicile calculé + état du pipeline cols, sur athlete_profiles.
-- Note: `lat`/`lon` existent déjà (schéma E1) et n'étaient utilisés nulle part —
-- réutilisés ici pour le domicile calculé plutôt que d'ajouter des colonnes redondantes.
alter table public.athlete_profiles
  add column home_computed_at timestamptz,
  add column cols_cache_updated_at timestamptz,
  -- position du domicile au moment du dernier fetch Overpass réussi (pour détecter
  -- un déplacement > 5km et redéclencher un refresh même si < 30 jours) — distinct de
  -- lat/lon, qui représentent le domicile ACTUEL recalculé chaque jour.
  add column cols_cache_home_lat numeric(9, 6),
  add column cols_cache_home_lon numeric(9, 6),
  add column col_matching_cursor timestamptz;
