-- Cartographie GPS — coordonnées des samples + polyligne downsamplée par activité.
-- Additif uniquement (colonnes nullable) : aucun impact sur les lignes existantes.

alter table public.activity_samples
  add column if not exists latitude numeric(9, 6)
    check (latitude is null or latitude between -90 and 90),
  add column if not exists longitude numeric(9, 6)
    check (longitude is null or longitude between -180 and 180);

alter table public.activities
  add column if not exists route_polyline jsonb;

comment on column public.activities.route_polyline is
  'Polyligne GPS downsamplée (<=64 points [lng, lat]) pour vignettes et heatmap. Null si pas de GPS.';
