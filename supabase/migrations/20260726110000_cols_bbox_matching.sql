-- Refonte détection cols : matching par bbox d'activité (plus de limite 50 km domicile).

-- Index pour les requêtes bbox du worker (cols candidats dans l'emprise d'une activité).
create index cols_lat_lon_idx on public.cols (latitude, longitude);

-- Rejoue tout l'historique au prochain cron : les activités sont re-matchées avec la
-- nouvelle logique (Overpass + matching sur le bbox de chaque activité), ce qui fait
-- apparaître les cols gravis loin du domicile (ex. col du Chaussy, sortie du 2026-07-25).
-- L'upsert de col_crossings est idempotent — aucun doublon possible.
update public.athlete_profiles set col_matching_cursor = null;
