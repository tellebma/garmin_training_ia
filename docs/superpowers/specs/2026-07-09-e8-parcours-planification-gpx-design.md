# E8 — Parcours géolocalisés & planification GPX (design)

**Date :** 2026-07-09
**Statut :** validé en brainstorming, à découper en plan
**EPIC parent :** E8 (parcours géolocalisés)
**Supersède :** `docs/superpowers/specs/2026-05-21-e8a-parcours-geolocalises-design.md`
(jamais implémentée — infra GraphHopper absente, aucune table `routes` en DB). Cette
spec reprend l'essentiel du design E8a (génération de boucles, export GPX) et l'étend
avec un mode de création manuelle appuyé sur le widget "Mes cols" (livré le
2026-07-08) ainsi qu'une intégration directe au plan d'entraînement.

**Écart vs E8a original :** le push automatique vers Garmin Connect comme "Course"
est retiré du scope de cette itération. Vérification faite sur le code source de
`python-garminconnect==0.3.3` (déjà utilisé par le worker) : la librairie n'expose
**aucune** méthode de push de course navigable — uniquement l'upload de workouts
structurés (intervalles) et l'upload d'activités terminées. Un push serait possible
via l'appel bas niveau `client.connectapi`/`.post()` vers l'endpoint interne
`course-service` de Garmin, mais celui-ci n'est pas documenté et nécessiterait une
rétro-ingénierie (capture de la requête réelle du site Garmin Connect). Décision
owner (2026-07-09) : livrer l'export GPX seul dans cette itération (import manuel sur
Garmin Connect, ~30 secondes) ; le push automatique passe en post-MVP, à investiguer
séparément.

## Objectif

Donner à l'athlète un volet de planification d'entraînement géolocalisé :

1. **Mode auto** (repris d'E8a) : pour une séance run/bike planifiée par le moteur
   E4/E5, suggérer 3 boucles réelles qui matchent durée + dénivelé cible, depuis son
   domicile (ou une adresse override).
2. **Mode manuel** (nouveau) : permettre de tracer un parcours de zéro, en s'appuyant
   sur les cols connus autour de chez soi (table `cols`, widget existant) et/ou des
   points libres posés sur une carte, routés via GraphHopper.

Dans les deux cas : export GPX (import manuel sur Garmin Connect), et possibilité
d'associer le parcours à une séance du plan — y compris en créant une "sortie libre"
hors du contenu généré automatiquement (ex : grosse sortie montagne le week-end).

Course cible août-septembre 2026 : à livrer largement avant pour validation par les
beta-testeurs (5-10 amis triathlètes).

## Scope

**In scope** :
- Génération de boucles via GraphHopper self-host (`round_trip`) — mode auto, repris
  d'E8a à l'identique (algorithme, scoring, cache, régénération).
- Construction manuelle de parcours : sélection de cols (table `cols` existante) et/ou
  points libres sur carte, routage GraphHopper multi-points (Directions API, pas
  `round_trip`).
- Récupération de cols hors du rayon 50 km domicile déjà en cache, via appel Overpass
  à la volée sur la zone visible de la carte.
- Sports : `run` + `bike` (vélo route). `swim`/`rest`/`brick course-part` exclus.
- Point de départ : `athlete_profiles.lat/lon` (calculé automatiquement par le
  pipeline "Mes cols", médiane des départs GPS) + override adresse à la volée.
- Export GPX (téléchargement).
- Association d'un parcours (auto ou manuel) à une séance planifiée existante.
- Création d'une "sortie libre" : le parcours met à jour la `planned_session` du jour
  choisi (sport, séance, cibles, lien route), avec confirmation si conflit.
- Persistance : table `routes` (reprise d'E8a) + colonnes ajoutées sur
  `planned_sessions`.
- Page `/routes` indépendante (2 onglets), remplace la modale `/today` d'E8a.

**Out of scope (itérations suivantes)** :
- Push automatique vers Garmin Connect comme "Course" (voir écart ci-dessus) —
  nécessite une rétro-ingénierie de l'endpoint `course-service`, non couvert par
  `python-garminconnect`. Table `route_garmin_exports` non créée dans cette itération.
- Workout structuré (intervalles, cibles allure/FC) → E8b (existant, séparé)
- Édition manuelle d'un parcours déjà sauvegardé (on retrace de zéro si besoin)
- Optimisation de l'ordre des waypoints (TSP) — l'ordre suit les clics utilisateur
- Heatmap des activités passées (déjà livré ailleurs, E14)
- VTT, navigation swim
- Multiple start locations sauvegardées (uniquement domicile calculé + override
  éphémère)
- Sync activité Garmin reçue ↔ route pushée (closing the loop)

## Architecture

```
[PWA Next.js — /routes]                  [UNRAID self-host]
   │                                        ┌────────────────────┐
   │  Server Actions (auth user JWT)        │ GraphHopper Docker │
   │  suggestRoutes / buildRoute            │   :8989             │
   │  geocodeAddress / refreshColsArea      │   - profile bike   │
   │  linkRouteToSession / applyRouteToPlan │   - profile foot   │
   ▼                                        │   - round_trip     │
[Worker FastAPI]                            │   - directions     │
   │  POST /routes/suggest                  │   + Photon :2322   │
   │  POST /routes/build                    │     (geocoding)    │
   │  GET  /routes/{id}/gpx                 └────────────────────┘
   │  POST /cols/refresh-area  ──────────────▶ Overpass API (public)
   │  POST /routes/{id}/apply-to-plan
   │  POST /routes/{id}/link-session
   ▼
[Supabase Postgres + RLS]
   - routes (polyline GeoJSON, waypoints, distance, D+, score)
   - cols (référentiel existant, widget "Mes cols")
   - planned_sessions (+ route_id, origin)
   - athlete_profiles.lat/lon (déjà calculé par le pipeline cols)
```

### Flow type — mode auto (repris d'E8a)

1. Sur `/today`, bouton "Suggérer parcours" → redirige vers `/routes?session={id}`
   (au lieu d'ouvrir une modale).
2. `/routes` détecte le query param, pré-sélectionne l'onglet "Suggestion auto",
   pré-remplit sport/durée/D+ cible depuis la `planned_session`. Sans query param :
   sport et cible saisis manuellement (formulaire libre).
3. PWA Server Action → Worker `POST /routes/suggest` (JWT user).
4. Worker récupère `athlete_profiles.lat/lon` (ou override), vitesse moyenne user
   (rolling 30j sur `activities`), génère 8 candidats GraphHopper `round_trip` en
   parallèle, filtre ±20% distance, trie par écart D+, garde top 3.
5. PWA affiche 3 cartes Leaflet, user sélectionne une.
6. Actions : télécharger GPX, associer à une séance / ajouter au plan (section
   commune, voir plus bas).

### Flow type — mode manuel (nouveau)

1. Sur `/routes`, onglet "Tracer moi-même".
2. Carte Leaflet centrée sur `athlete_profiles.lat/lon` (override adresse possible).
3. Panneau latéral liste les cols connus (table `cols`, rayon 50 km) — clic pour
   ajouter comme waypoint. Clic direct sur la carte pour ajouter un point libre.
4. Si la carte est déplacée hors de la zone connue → bouton "Chercher des cols ici" →
   Server Action `refreshColsArea(bbox_center, radius_m)` → Worker
   `POST /cols/refresh-area` → appel Overpass sur cette zone → upsert `cols`
   (dédoublonné par `osm_id`) → PWA recharge la liste.
5. Liste ordonnée de waypoints (départ → col(s)/points → retour, ordre de clic,
   réordonnable par drag).
6. Bouton "Calculer l'itinéraire" → Server Action `buildRoute(sport, start,
   waypoints)` → Worker `POST /routes/build` → GraphHopper Directions API multi-
   points (profil `foot` ou `bike`) → polyline routée + distance/D+/durée estimée →
   insert DB (`source='graphhopper_waypoints'`, `waypoints` jsonb).
7. Actions : identiques au mode auto (export GPX, associer/ajouter au plan).

### Association au plan (commun aux deux modes)

- **"Associer à une séance existante"** : sélecteur des `planned_sessions` à venir
  compatibles (sport run/bike) → Server Action `linkRouteToSession(route_id,
  planned_session_id)` → Worker `POST /routes/{id}/link-session` → update
  `routes.planned_session_id`. Pas de changement de contenu de séance.
- **"Ajouter au plan comme sortie libre"** : sélecteur de date dans la plage du plan
  actif → Server Action `applyRouteToPlan(route_id, date)` → Worker
  `POST /routes/{id}/apply-to-plan` → update de la `planned_session` déjà existante
  pour ce jour (E4 crée une ligne par jour du plan, y compris repos) : `sport`,
  `session_type='long'` (valeur fixe pour toute sortie libre — cohérente avec le sens
  de "grosse sortie hors plan" et déjà une valeur valide du check existant),
  `target_duration_s`/`target_tss` recalculés depuis distance/durée estimée — via la
  table `_TSS_PER_HOUR[(sport, "long")]` déjà utilisée par `coach/planner.py`
  (`target_tss = _TSS_PER_HOUR[(sport, "long")] * estimated_duration_s / 3600`),
  `notes` ("Sortie libre planifiée via /routes"), `route_id`, `origin='route'`.
  - Si le jour a déjà une séance non-repos prévue → réponse `{status:
    "session_conflict", existing_sport, existing_session_type}` (voir convention de
    réponse dans la section Endpoints) → modale de confirmation "remplacer la séance
    prévue ?" → retry avec `force:true`.
  - Si l'utilisateur n'a pas de plan actif (E4 non généré) → bouton désactivé +
    tooltip "Génère d'abord ton plan d'entraînement".
  - Le cron E5 (génération LLM du contenu détaillé) continue de tourner normalement
    sur cette séance — une sortie libre reçoit aussi un briefing markdown généré.

## Schéma DB (nouvelle migration)

```sql
-- Reprise d'E8a, schéma inchangé pour routes (route_garmin_exports non créée dans
-- cette itération : le push Garmin est hors scope, voir écart en tête de spec)
create table public.routes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  planned_session_id uuid references public.planned_sessions(id) on delete set null,
  source text not null check (source in (
    'graphhopper_round_trip','graphhopper_waypoints','manual_gpx','imported'
  )),
  sport text not null check (sport in ('run','bike')),

  start_lat numeric(10,7) not null,
  start_lng numeric(10,7) not null,
  polyline jsonb not null,  -- GeoJSON LineString {type, coordinates: [[lng,lat,ele],...]}
  waypoints jsonb,          -- mode manuel : [{lat,lng,col_id?}], null en mode auto

  distance_m numeric(10,2) not null check (distance_m > 0),
  elevation_gain_m integer not null check (elevation_gain_m >= 0),
  estimated_duration_s integer check (estimated_duration_s is null or estimated_duration_s > 0),

  target_duration_s integer,
  target_elevation_gain_m integer,
  match_score numeric(5,2),

  graphhopper_seed integer,
  generated_at timestamptz not null default now(),
  selected_at timestamptz
);

create index routes_user_session_idx on public.routes (user_id, planned_session_id);
create index routes_user_generated_idx on public.routes (user_id, generated_at desc);

alter table public.routes enable row level security;
create policy "users read own routes" on public.routes for select using (auth.uid() = user_id);
-- Insert/update via worker (service role), pas d'INSERT user direct

-- ─────────────────────────────────────────
-- Intégration au plan

alter table public.planned_sessions
  add column if not exists route_id uuid references public.routes(id) on delete set null,
  add column if not exists origin text not null default 'planner'
    check (origin in ('planner','route'));

-- Pas de colonnes location_lat/lng sur athlete_profiles : on réutilise lat/lon,
-- déjà ajoutées et calculées automatiquement par le pipeline "Mes cols"
-- (worker/src/garmin_sync/coach/home_location.py).
```

### Décisions schéma

- **`polyline` JSONB GeoJSON** (pas PostGIS), repris d'E8a : pas de requête spatiale
  nécessaire.
- **`waypoints` JSONB nullable** : traçabilité du mode manuel (debug, futur "retracer
  à partir de"), pas d'édition prévue dans cette itération.
- **Pas de nouvelles colonnes lat/lng sur `athlete_profiles`** : simplification vs
  E8a original, on s'appuie sur le calcul automatique déjà livré par le widget cols.
- **`planned_sessions.origin`** : colonne de traçabilité/affichage uniquement (badge
  "sortie libre" dans le calendrier), n'interfère pas avec la logique de sélection de
  `session_type` du moteur E4 (`pick_session_types_for_phase` etc.) ni avec le calcul
  CTL/ATL (qui lit `activities`, pas `planned_sessions`).

## Endpoints worker

**Convention de réponse (écart vs E8a original, alignement sur le reste de l'API
worker)** : E8a décrivait des codes HTTP REST classiques (404/409/422/503). Or
**tous** les endpoints `/coach/*` et `/garmin/*` existants renvoient en réalité un
**HTTP 200 avec un champ `status` discriminant** dans le corps JSON (voir
`ConnectResult`, `EnsureSessionsResult`, `RegenerateSessionResult` dans
`lib/worker.ts`, et `except SessionNotFound: return {"status": "session_not_found"}`
dans `main.py`) — seuls les échecs d'authentification (401) et de requête
malformée (400) restent de vrais codes HTTP. Les erreurs inattendues passent par
`report_endpoint_error()` → `{status: "unexpected_error", error_id, type}`, toujours
en 200. Cette spec suit cette convention établie plutôt que celle d'E8a.

### `POST /routes/suggest` (repris d'E8a, adapté à la convention `status`)

Auth JWT user. Body `{ planned_session_id?, sport?, target_duration_s?,
target_elevation_gain_m?, start_override? }` — `planned_session_id` optionnel
désormais (mode `/routes` sans contexte de séance : cible saisie manuellement, sport
et cibles alors requis).

**Réponse (200 dans tous les cas)** :
- Succès : `{ status: "ok", routes: [...], target: {...}, estimated_user_speed_mps }`
- `{ status: "invalid_session" }` (session pas à ce user)
- `{ status: "session_not_found" }`
- `{ status: "no_start_coords" }` (pas de `athlete_profiles.lat/lon` ni override)
- `{ status: "no_valid_routes" }` (GraphHopper retourne 0 boucle valide après filtrage)
- `{ status: "graphhopper_unavailable" }`
- `{ status: "unexpected_error", error_id, type }`

### `POST /routes/build` (nouveau)

Auth JWT user.

**Body** :
```json
{
  "sport": "bike",
  "start": { "lat": 45.764, "lng": 4.835 },
  "waypoints": [
    { "lat": 45.90, "lng": 5.10, "col_id": "uuid-col-galibier" },
    { "lat": 45.85, "lng": 5.05 }
  ]
}
```

Worker appelle GraphHopper Directions API avec les points ordonnés (départ +
waypoints + retour départ implicite), profil `foot`/`bike`. Retourne polyline routée
+ distance/D+/durée estimée (vitesse moyenne user, comme le mode auto). Insert DB
`source='graphhopper_waypoints'`.

**Réponse (200 dans tous les cas)** :
- Succès : `{ status: "ok", route: {...} }`
- `{ status: "no_route_found" }` (GraphHopper ne peut pas relier les points)
- `{ status: "graphhopper_unavailable" }`
- `{ status: "unexpected_error", error_id, type }`

### `POST /cols/refresh-area` (nouveau)

Auth JWT user. Body `{ lat, lng, radius_m }` (défaut `radius_m=25000`, plafonné à
50000 pour limiter la charge Overpass). Réutilise le module
`worker/src/garmin_sync/coach/overpass.py` existant (widget cols), appelé pour un
centre arbitraire au lieu du domicile uniquement. Upsert `cols` par `osm_id`.

**Réponse (200 dans tous les cas)** :
- Succès : `{ status: "ok", cols_count: N }`
- `{ status: "overpass_unavailable" }` (timeout ou erreur réseau, pas de blocage —
  la liste de cols reste simplement vide pour cette zone)
- `{ status: "unexpected_error", error_id, type }`

### `POST /routes/{route_id}/apply-to-plan` (nouveau)

Auth JWT user. Body `{ date, force? }`. Update de la `planned_session` du jour
(sport/session_type/target_duration_s/target_tss/notes/route_id/origin='route').

**Réponse (200 dans tous les cas)** :
- Succès : `{ status: "ok", planned_session_id, replaced: boolean }`
- `{ status: "route_not_found" }`
- `{ status: "no_active_plan" }`
- `{ status: "session_conflict", existing_sport, existing_session_type }` (si `force`
  absent et jour déjà occupé par une séance non-repos)
- `{ status: "unexpected_error", error_id, type }`

### `POST /routes/{route_id}/link-session` (nouveau)

Auth JWT user. Body `{ planned_session_id }` → update `routes.planned_session_id`
uniquement.

**Réponse (200 dans tous les cas)** :
- Succès : `{ status: "ok" }`
- `{ status: "route_not_found" }`
- `{ status: "invalid_session" }`
- `{ status: "unexpected_error", error_id, type }`

### `GET /routes/{route_id}/gpx` (repris d'E8a, inchangé)

Seul endpoint qui reste un vrai code HTTP REST (fichier téléchargeable, pas un appel
JSON piloté par `status`). Auth JWT user. Réponse 200 : `Content-Type:
application/gpx+xml`, `Content-Disposition: attachment;
filename="{sport}-{date}.gpx"`, GPX 1.1 (polyline + metadata.name). Réponse
`404 {"detail": "route_not_found"}` (via `HTTPException`) si la route n'existe pas ou
n'appartient pas à l'utilisateur.

## UI PWA

### Nouvelle arborescence

```
app/(app)/routes/
├── page.tsx                     # /routes — lit ?session= si présent
components/routes/
├── RouteTabs.tsx                 # "Suggestion auto" / "Tracer moi-même"
├── AutoSuggestPanel.tsx          # reprend RouteSuggestModal (E8a) en panneau plein-page
├── ManualBuildPanel.tsx          # carte + panneau cols + waypoints
├── RouteCard.tsx                 # 1 carte route (Leaflet + stats + select)
├── RouteMap.tsx                  # wrapper Leaflet réutilisable
├── ColsPickerList.tsx            # liste des cols connus, recherche, clic → waypoint
├── WaypointsList.tsx             # liste ordonnée + drag-to-reorder + suppression
├── StartOverrideInput.tsx        # input adresse + geocoding debounced (repris E8a)
├── LinkToPlanActions.tsx         # "Associer à une séance" / "Ajouter au plan"
└── ExportActions.tsx             # bouton "Télécharger GPX"
```

### Comportement

- **Cache mode auto** : identique E8a (routes déjà générées pour la session,
  ré-affichées par défaut ; bouton "Régénérer").
- **Mode manuel** : pas de cache — chaque construction est un nouveau `routes` en DB,
  historique consultable mais pas de "reprendre mon brouillon" dans cette itération.
- **Visibilité "Ajouter au plan"** : grisé + tooltip si pas de plan actif.
- **Conflit de séance** : modale "Le {date} a déjà une séance prévue ({sport}
  {session_type}). Remplacer ?" avant `force:true`.

### Librairies

**Écart vs E8a original** : E8a prévoyait `react-leaflet` + `leaflet` (aucune des deux
n'est dans `package.json`). Le code existant (`ActivityRouteMap`, `RouteThumbnail`,
`RoutesHeatmap` — livrés avec E14 cartographie GPS) utilise déjà **`maplibre-gl`**
(`^5.24.0`, déjà en dépendance) avec le style CartoDB dark-matter. On suit ce
précédent plutôt que d'introduire une deuxième lib de cartographie : `RouteMap.tsx`
est un nouveau wrapper maplibre-gl (pas Leaflet), et réutilise les helpers existants
`lib/maps/route-geojson.ts` (`buildRouteGeoJson`, `routeBounds`) pour construire les
features GeoJSON affichées. Le clic sur la carte (ajout de waypoint en mode manuel)
utilise `map.on('click', …)`, équivalent maplibre-gl du `onClick` Leaflet.

### Empty / error states

Chaque ligne correspond à la valeur du champ `status` renvoyé par le worker (voir
convention de réponse, section Endpoints) — tous en HTTP 200.

| `status` | UI |
|---|---|
| `no_start_coords` (aucune activité GPS encore synchronisée) | Banner "Synchronise au moins une activité GPS pour calculer ton point de départ, ou saisis une adresse" |
| `no_valid_routes` / `no_route_found` | "Aucun itinéraire trouvé. Essaie un autre point de départ ou d'autres waypoints." |
| `graphhopper_unavailable` | "Service indisponible. Réessaie dans une minute." |
| `overpass_unavailable` | "Impossible de chercher des cols sur cette zone pour l'instant." |
| `no_active_plan` | Bouton "Ajouter au plan" désactivé + tooltip |
| `session_conflict` | Modale de confirmation "remplacer ?" |
| `unexpected_error` | Toast générique + `error_id` affiché (support) |

## Infra GraphHopper (reprise d'E8a, inchangée)

```yaml
# worker/docker-compose.prod.yml
services:
  graphhopper:
    image: israelhikingmap/graphhopper:latest  # build avec Photon embedded
    container_name: graphhopper
    restart: unless-stopped
    ports:
      - "127.0.0.1:8989:8989"
      - "127.0.0.1:2322:2322"   # Photon geocoding
    volumes:
      - graphhopper-data:/data
      - ./graphhopper/config.yml:/graphhopper/config.yml:ro
    environment:
      JAVA_OPTS: "-Xmx4g -Xms4g"

volumes:
  graphhopper-data:
```

- **OSM source** : `https://download.geofabrik.de/europe/france-latest.osm.pbf` (~4 Go)
- **Premier import** : ~30-60 min, RAM peak ~6 Go ; steady state ~3.5 Go RAM
- **Profils activés** : `foot` (run), `bike` (vélo route)
- **Directions API** : même instance GraphHopper, endpoint `/route` (multi-points)
  au lieu de `/route?algorithm=round_trip`
- **Overpass** : appel direct à l'API publique existante (déjà utilisée par le
  pipeline cols), pas de nouvelle infra

### Variables env worker

```
GRAPHHOPPER_URL=http://graphhopper:8989
GRAPHHOPPER_TIMEOUT_S=5
PHOTON_URL=http://graphhopper:2322
```

## Gestion erreurs (pattern établi : `report_endpoint_error`, cf. `observability.py`)

Chaque endpoint attrape les exceptions **connues** (typées, ex. `NoStartCoordsError`,
`GraphhopperUnavailableError`, `SessionConflictError`) et les traduit explicitement en
`{status: "..."}` — même pattern que `except SessionNotFound: return {"status":
"session_not_found"}` dans `main.py`. Toute exception **non prévue** tombe dans le
`except Exception as e: return report_endpoint_error(e, endpoint="...", user_id=...)`
générique, qui génère un `error_id` (uuid8), logge + capture Sentry, et renvoie
`{status: "unexpected_error", error_id, type}` — jamais de trace brute exposée au
navigateur.

Stack traces complètes dans `docker logs garmin-sync` + `docker logs graphhopper`,
greppables par `error_id`. Capture Sentry sur chaque bloc (pattern des recomputes
cron existants, `capture(exc, where=..., **tags)`).

## Tests

### Worker Python (pytest)
```
worker/tests/
├── test_routing.py             # mock GraphHopper httpx (round_trip + directions)
├── test_geocoding.py           # mock Photon
├── test_overpass_area.py       # mock Overpass, refresh zone arbitraire
├── test_route_generator.py     # estimate_user_speed, score_route, suggest_routes
├── test_route_builder.py       # build_route (waypoints → polyline routée)
├── test_gpx.py                 # GeoJSON → GPX valide (round-trip via gpxpy)
├── test_routes_endpoint.py     # FastAPI TestClient + Supabase mock (suggest/build)
├── test_apply_to_plan.py       # update planned_session, conflit, no_active_plan
└── fixtures/
    ├── graphhopper_round_trip_response.json
    └── graphhopper_directions_response.json
```

Cible : **≥95% coverage worker** (cohérent EQ Quality Gate). Tous les chemins
d'erreur testés.

### Frontend
- **Vitest** : `RouteTabs` state, `ManualBuildPanel` waypoints add/reorder/remove,
  `AutoSuggestPanel` (repris de `RouteSuggestModal`), `LinkToPlanActions` conflict flow
- **Playwright E2E** :
  - Flow auto : `/today` → clic "Suggérer" → `/routes?session=` → sélection → GPX
    download (Content-Disposition)
  - Flow manuel : `/routes` → onglet manuel → clic 2 cols → "Calculer l'itinéraire" →
    tracé affiché → "Ajouter au plan" → confirmation conflit

### Tests d'intégration manuels (pre-merge)
1. Premier import OSM UNRAID dev → boucle 10 km depuis Lyon (mode auto)
2. Tracé manuel via 2 cols connus → itinéraire routé cohérent
3. Pan carte hors zone connue → "Chercher des cols ici" → nouveaux cols apparaissent
4. Download GPX → ouverture Garmin Connect manuel (import manuel)
5. "Ajouter au plan" sur un jour de repos → séance mise à jour, badge "sortie libre"
6. "Ajouter au plan" sur un jour déjà occupé → modale conflit → remplacement confirmé
7. Aucun plan actif → bouton désactivé
8. Session swim/rest → onglets `/routes` sans cible (accès libre uniquement)

## Quality gates (QUALITY_GATES.md)

- ✅ `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
- ✅ `cd worker && uv run pytest -v && uv run ruff check . && uv run mypy src/`
- ✅ Migration appliquée via `mcp__supabase__apply_migration` (project
  `peiyrqplymdlmlpsbqzu`)
- ✅ SonarQube ≥95% coverage nouveau code, 0 critical issues
- ✅ Lighthouse PWA score maintenu (Leaflet n'impacte que `/routes`)

## Risques

| Risque | Mitigation |
|---|---|
| GraphHopper OOM au démarrage (4 Go RAM) | Limiter par région si problème |
| Photon flaky | Fallback Nominatim public |
| Overpass rate limit / lenteur | Timeout explicite, échec silencieux (liste de cols vide, pas de blocage) |
| Style tiles CartoDB indisponible | Même dépendance déjà en prod via `ActivityRouteMap` (E14), risque non nouveau |
| Boucles/itinéraires irréalistes (chemins privés) | Profils GraphHopper choisis + feedback user post-essai |
| `apply-to-plan` écrase une séance planifiée par erreur | Confirmation explicite obligatoire sur conflit (pas de force silencieux) |

## Décomposition prévisionnelle (à raffiner dans le plan)

1. **Infra GraphHopper** : container, premier import OSM, smoke test round_trip +
   directions
2. **Migration DB** : `routes`, `planned_sessions.route_id`/`origin`
3. **Module worker `routing.py`** : client GraphHopper async (round_trip + directions)
4. **Module worker `geocoding.py`** : client Photon + fallback Nominatim (repris E8a)
5. **Module worker `overpass.py`** : extension pour zone arbitraire (réutilise
   l'existant du widget cols)
6. **Module worker `route_generator.py`** : estimate_speed, suggest_routes, scoring
   (repris E8a)
7. **Module worker `route_builder.py`** : build_route (waypoints → GraphHopper
   directions → polyline)
8. **Module worker `gpx.py`** : GeoJSON → GPX (repris E8a)
9. **Module worker `plan_integration.py`** : apply_route_to_plan, link_route_to_session
10. **Endpoints worker** : `/routes/suggest`, `/routes/build`, `/routes/{id}/gpx`,
    `/cols/refresh-area`, `/routes/{id}/apply-to-plan`, `/routes/{id}/link-session` +
    tests
11. **Server Actions Next.js** : `suggestRoutes`, `buildRoute`, `geocodeAddress`,
    `refreshColsArea`, `applyRouteToPlan`, `linkRouteToSession`
12. **Composants UI** : `RouteTabs`, `AutoSuggestPanel`, `ManualBuildPanel`,
    `ColsPickerList`, `WaypointsList`, `RouteCard`, `RouteMap`, `StartOverrideInput`,
    `LinkToPlanActions`, `ExportActions`
13. **Page `/routes`** : lecture query param `?session=`, routing des 2 onglets
14. **Intégration `/today`** : bouton redirige vers `/routes?session={id}`
15. **Tests E2E Playwright** : flow auto + flow manuel complet
16. **Doc deploy GraphHopper** : `worker/deploy/README.md` + script refresh OSM

## E8b (out of scope, mentionné pour contexte)

- Parser séance E5 markdown → format Garmin workout structuré (steps, durée, cibles
  allure/FC/puissance)
- `python-garminconnect.upload_running_workout()` / `upload_cycling_workout()` (déjà
  disponibles dans la lib, contrairement au push de course)
- UI : checkbox "Envoyer aussi le workout structuré"

Spec E8b à écrire après livraison de cette spec. Le push automatique de "Course" vers
Garmin (retiré de cette itération, voir écart en tête de spec) sera aussi à
investiguer séparément, indépendamment d'E8b.
