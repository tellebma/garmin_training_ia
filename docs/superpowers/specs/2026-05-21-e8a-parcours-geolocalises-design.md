# E8a — Parcours géolocalisés (design)

**Date :** 2026-05-21
**Statut :** validé en brainstorming, à découper en plan
**EPIC parent :** E8 (parcours géolocalisés)
**Sous-livrable :** E8a (E8b = workout structuré + push Garmin Workout, à venir)

## Objectif

Quand l'athlète a une séance run/vélo générée par le planner (E4) +
détaillée par le LLM (E5), lui proposer **3 boucles géolocalisées réelles**
qui matchent la durée et le dénivelé cible, depuis son domicile (ou une
adresse override). Il peut télécharger le GPX et/ou envoyer le parcours
directement sur Garmin Connect comme "Course" pour navigation montre.

Course cible août-septembre 2026 : E8a doit être livré largement avant
pour validation par les beta-testeurs (5-10 amis triathlètes).

## Scope

**In scope (E8a)** :
- Génération de boucles via GraphHopper self-host (round_trip natif)
- Sports : `run` + `bike` (vélo route). `swim`/`rest`/`brick course-part` exclus.
- Point de départ : domicile géocodé + override adresse à la volée
- 3 boucles candidates retournées par requête, scorées par écart D+
- Cache : les routes déjà générées pour une séance sont ré-affichées par défaut, bouton "Régénérer"
- Export GPX (téléchargement)
- Push Garmin "Course" (parcours géolocalisé, pas workout structuré)
- Persistance : tables `routes` + `route_garmin_exports`
- UI sur page `/today` (bouton + modale)
- Geocoding du champ `athlete_profiles.location` existant (one-time + à l'edit profile)

**Out of scope (E8b et plus tard)** :
- Workout structuré (intervalles, cibles allure/FC) → E8b
- Page `/routes` exploratoire indépendante de la séance
- Édition manuelle d'un parcours suggéré
- Heatmap des activités passées
- VTT, swim navigation
- Multiple start locations sauvegardées (uniquement domicile + override éphémère)
- Sync activité Garmin reçue ↔ route pushée (closing the loop)

## Architecture

```
[PWA Next.js]                            [UNRAID self-host]
   │                                        ┌────────────────────┐
   │  Server Action (auth user JWT)         │ GraphHopper Docker │
   │  POST /api/routes/suggest              │   :8989            │
   │                                        │   - profile bike   │
   ▼                                        │   - profile foot   │
[Worker FastAPI] ──── HTTP ─────────────────▶│   - round_trip    │
   │  /routes/suggest                       │   + Photon :2322   │
   │  /routes/{id}/push-garmin              │     (geocoding)    │
   │  /routes/{id}/gpx                      └────────────────────┘
   │
   │  python-garminconnect ──────────────────▶ [Garmin Connect API]
   │   (upload course)                        course-service endpoint
   ▼
[Supabase Postgres + RLS]
   - routes (polyline GeoJSON, distance, D+, score)
   - route_garmin_exports (route_id, garmin_course_id, status)
   - athlete_profiles (+ location_lat/lng)
```

### Flow type

1. User clique "Suggérer parcours" sur `/today`
2. PWA Server Action → Worker `/routes/suggest` (JWT user)
3. Worker récupère : `planned_session`, `athlete_profiles.location_lat/lng` (ou override), vitesse moyenne user (rolling 30j sur `activities`)
4. Worker convertit `target_duration_s × speed_mps = target_distance_m`
5. Worker génère **8 candidats GraphHopper en parallèle** (asyncio.gather), filtre par tolérance distance (±20%), trie par `|D+_actual − D+_target|`, garde **top 3**
6. Worker insère les 3 routes en DB + retourne payload (polyline + stats + match_score)
7. PWA affiche 3 cartes Leaflet, user sélectionne une
8. PWA propose :
   - "Télécharger GPX" → `GET /api/routes/{id}/gpx` (proxy worker)
   - "Envoyer vers Garmin" → Server Action `pushRouteToGarmin(route_id, course_name)` → worker `/routes/{id}/push-garmin`
9. Worker convertit polyline → GPX via `gpxpy`, push via `python-garminconnect`, upsert `route_garmin_exports`

## Schéma DB (migration 20260526000000)

```sql
create table public.routes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  planned_session_id uuid references public.planned_sessions(id) on delete set null,
  source text not null check (source in ('graphhopper_round_trip','manual_gpx','imported')),
  sport text not null check (sport in ('run','bike')),

  start_lat numeric(10,7) not null,
  start_lng numeric(10,7) not null,
  polyline jsonb not null,  -- GeoJSON LineString {type, coordinates: [[lng,lat,ele],...]}

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

create table public.route_garmin_exports (
  id uuid primary key default gen_random_uuid(),
  route_id uuid not null references public.routes(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,

  garmin_course_id text,
  course_name text not null,

  status text not null check (status in ('pending','success','failed')),
  error_id text,
  pushed_at timestamptz not null default now(),

  unique (route_id)
);

alter table public.route_garmin_exports enable row level security;
create policy "users read own exports" on public.route_garmin_exports for select
  using (auth.uid() = user_id);

-- ─────────────────────────────────────────

alter table public.athlete_profiles
  add column if not exists location_lat numeric(10,7),
  add column if not exists location_lng numeric(10,7);
```

### Décisions schéma

- **`polyline` JSONB GeoJSON** (pas PostGIS) : on lit/écrit en bloc, pas de requête spatiale. Évite d'activer postgis sur Supabase.
- **`planned_session_id` nullable** : prépare une future page `/routes` exploratoire (E8 v2) sans casser le schéma.
- **`route_garmin_exports.unique(route_id)`** : 1 route = 1 push max. Re-push impose de re-générer une route.
- **`match_score` persisté** : debug + affichage "match X%" dans l'UI.
- **`selected_at`** : distinction propose/choisi. Permet purge weekly des non-sélectionnées (cron post-MVP).
- **`location_lat/lng` ajoutés à `athlete_profiles`** : géocodage one-time du champ `location` text existant.

## Endpoints worker

### `POST /routes/suggest`

Auth : JWT user (ES256, pas shared token — action interactive).

**Body** :
```json
{
  "planned_session_id": "uuid",
  "start_override": { "lat": 45.764, "lng": 4.835 }
}
```
ou
```json
{
  "planned_session_id": "uuid",
  "start_override": { "address": "Place Bellecour Lyon" }
}
```

Le nombre de candidats retournés est fixé côté worker (`CANDIDATES_TO_RETURN = 3`).
`start_override` est optionnel : si absent, le worker utilise
`athlete_profiles.location_lat/lng`.

**Réponse 200** :
```json
{
  "routes": [
    {
      "id": "uuid",
      "polyline": {"type":"LineString","coordinates":[...]},
      "distance_m": 10800,
      "elevation_gain_m": 195,
      "estimated_duration_s": 3480,
      "match_score": 5.0,
      "graphhopper_seed": 12345
    }
  ],
  "target": { "duration_s": 3600, "elevation_gain_m": 200, "sport": "run" },
  "estimated_user_speed_mps": 3.1,
  "debug": { "n_candidates_generated": 8, "n_filtered": 5 }
}
```

**Erreurs** :
- `400 invalid_session` (session pas à ce user)
- `404 session_not_found`
- `409 no_start_coords` (profile.location_lat/lng null ET pas d'override)
- `422 no_valid_routes` (GraphHopper retourne 0 boucle valide après filtrage)
- `503 graphhopper_unavailable`

### `POST /routes/{route_id}/push-garmin`

Auth : JWT user.

**Body** :
```json
{ "course_name": "Run endurance — 2026-05-21" }
```
(défaut auto-généré : `"{sport_label} {session_type} — {date_iso}"`)

**Réponse 200** :
```json
{ "garmin_course_id": "12345678", "course_name": "Run endurance — 2026-05-21" }
```

**Erreurs** :
- `404 route_not_found`
- `409 already_pushed` (existant + status=success)
- `502 garmin_push_failed { error_id }`
- `429 garmin_rate_limited`

### `GET /routes/{route_id}/gpx`

Auth : JWT user.

**Réponse 200** : `Content-Type: application/gpx+xml`, `Content-Disposition: attachment; filename="run-2026-05-21.gpx"`, GPX 1.1 (polyline + metadata.name).

## Algorithme matching (worker/src/garmin_sync/route_generator.py)

Constantes :
- `CANDIDATES_TO_GENERATE = 8`
- `CANDIDATES_TO_RETURN = 3`
- `DISTANCE_TOLERANCE_PCT = 0.20`
- `GRAPHHOPPER_TIMEOUT_S = 5`
- `FALLBACK_SPEED_MPS = { "run": 3.33, "bike": 7.77 }`

### `estimate_user_speed(user_id, sport)`
- Récupère activities du user, même sport, 30 derniers jours, `distance_m not null`
- Filtre : `duration_s >= 600 AND distance_m >= 1000` (exclut artefacts)
- Si `len(valid) < 3` → fallback constante
- Sinon : moyenne pondérée par durée : `sum(dist) / sum(time)`

### `suggest_routes(planned_session, start_coords)`
1. Validation sport ∈ {run, bike}
2. `target_distance_m = duration_s × estimate_user_speed(...)`
3. GraphHopper profile : `bike` si sport=bike, sinon `foot`
4. Génère 8 seeds aléatoires, lance 8 requêtes round_trip en parallèle (`asyncio.gather(return_exceptions=True)`)
5. Filtre :
   - Exceptions GraphHopper → rejetées
   - `ratio = distance_actual / target` hors [0.8, 1.2] → rejetées
6. Si 0 valide → `NoRoutesFoundError` (422)
7. Tri par `score = abs(elevation_actual - target_elevation)` croissant
8. Top 3 → insert DB + retour payload

### Score `match_score`
- Si `target_elevation_gain_m is None` (course plate) → score = 0 partout, tri arbitraire
- Sinon : `abs(actual - target)` mètres absolus

### Pourquoi 8 candidats > 3
- GraphHopper round_trip ne contraint pas le D+ → on génère plus pour avoir du choix
- 8 × ~200 ms en parallèle = ~250 ms total (httpx async)
- Tolérance distance ±20% pour rejeter les boucles aberrantes

### Limitations connues
- **Pas de garantie D+ exact** : si user est en plaine, les 3 boucles auront peu de D+. `match_score` rend ça visible. Mitigation future (E8 v2) : custom profile GraphHopper qui pénalise les routes plates.
- **Seeds random** : pas reproductible volontairement. Variété entre 2 demandes successives. Stockage seed permet "re-générer la même" si jamais utile.

## Geocoding

- **Photon** (embedded dans `israelhikingmap/graphhopper` Docker image) sur port 2322
- Endpoint worker `POST /geocoding/search { query }` (utilisé par `StartOverrideInput` + onboarding edit profile)
- Fallback : Nominatim public (`https://nominatim.openstreetmap.org/search`) si Photon down
- One-shot job : à l'enregistrement d'un nouveau `location` text dans `athlete_profiles`, lancer geocoding et sauver `location_lat/lng`

## UI PWA

### Nouveaux composants

```
components/routes/
├── RouteSuggestButton.tsx       # bouton sur /today
├── RouteSuggestModal.tsx        # modale principale (3 cartes + actions)
├── RouteCard.tsx                # 1 carte route (Leaflet + stats + select)
├── RouteMap.tsx                 # wrapper Leaflet réutilisable
├── StartOverrideInput.tsx       # input adresse + geocoding debounced
└── ExportActions.tsx            # boutons "GPX" + "Garmin"
```

### Comportement

- **Cache** : à l'ouverture de la modale, lit `routes` filtrées par `planned_session_id` + ORDER BY `generated_at DESC LIMIT 3`. Si trouvées → affiche directement. Sinon → premier suggest auto.
- **Bouton "Régénérer"** : force nouveau `/routes/suggest` (insère 3 nouvelles routes en DB, les précédentes restent en historique).
- **Override adresse** : input avec debounce 400 ms → Server Action `geocodeAddress(query)` → top 5 suggestions Photon → user pick. lat/lng en state React local (pas DB).
- **Visibilité du bouton "Suggérer parcours"** :
  - Affiché si `session.sport ∈ {run, bike}` → route générée avec ce sport
  - Affiché pour `session.sport = brick` → route générée avec `sport=bike` (partie vélo seulement, la course à pied du brick reste non géolocalisée). La table `routes.sport check` reste limitée à `('run','bike')`.
  - Caché pour `swim`, `rest`

### Librairies

- `react-leaflet` v4 + `leaflet` v1.9 (~50 Ko gzip)
- Tiles OSM publiques `https://tile.openstreetmap.org/{z}/{x}/{y}.png` (attribution affichée)
- Pas de Mapbox GL JS (overkill)

### Empty / error states

| Cas | UI |
|---|---|
| `409 no_start_coords` | Banner "Renseigne ton adresse dans Profil → Personnel" + lien |
| `422 no_valid_routes` | "Aucune boucle trouvée. Essaie un autre point de départ." |
| `503 graphhopper_unavailable` | "Service indisponible. Réessaie dans une minute." |
| Push Garmin failed | Toast erreur + GPX download reste actif (fallback) |

### Onboarding (intégration E3)

- À l'étape "Personnel" du wizard + au formulaire `/profile/perso/edit`, après save du champ `location` text → Server Action geocoding → écrit `location_lat/lng`
- Échec geocoding : message inline "Adresse non géocodée, override possible à chaque session". **Pas de blocage**.

## Infra GraphHopper

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
- **Premier import** : ~30-60 min, RAM peak ~6 Go
- **Steady state** : ~3.5 Go RAM, requêtes 50-200 ms
- **Refresh OSM** : cron UNRAID mensuel (script `worker/deploy/refresh-osm.sh`)
- **Profils activés** : `foot` (run), `bike` (vélo route)

### Variables env worker
```
GRAPHHOPPER_URL=http://graphhopper:8989
GRAPHHOPPER_TIMEOUT_S=5
PHOTON_URL=http://graphhopper:2322
```

## Gestion erreurs (pattern E2)

| Code | error_id pattern | UI fallback |
|---|---|---|
| GraphHopper 5xx/timeout | `gh_<uuid>` | "Service indisponible, réessaie" |
| GraphHopper 200 mais 0 route | `gh_no_route_<uuid>` | "Aucune boucle trouvée, change point de départ" |
| Photon 0 résultat | `geo_not_found_<uuid>` | "Adresse non trouvée" |
| Garmin push 4xx/5xx | `garmin_course_<uuid>` | Toast + GPX download dispo |
| Garmin 429 | `garmin_rate_<uuid>` | "Garmin rate limit, réessaie dans 1h" |
| Worker→Supabase fail | `db_<uuid>` | "Erreur DB" |

Stack traces dans `docker logs garmin-sync` + `docker logs graphhopper`, greppables par `error_id`. Pas de leak navigateur.

## Tests

### Worker Python (pytest)
```
worker/tests/
├── test_routing.py           # mock GraphHopper httpx
├── test_geocoding.py         # mock Photon
├── test_route_generator.py   # estimate_user_speed, score_route, suggest_routes
├── test_gpx.py               # GeoJSON → GPX valide (round-trip via gpxpy)
├── test_garmin_courses.py    # mock python-garminconnect.upload_course
├── test_routes_endpoint.py   # FastAPI TestClient + Supabase mock
└── fixtures/
    ├── graphhopper_round_trip_response.json
    └── garmin_course_upload_response.json
```

Cible : **≥95% coverage worker** (cohérent EQ Quality Gate). Tous les chemins d'erreur testés.

### Frontend
- **Vitest** : `RouteSuggestModal` state machine, `StartOverrideInput` debounce, `RouteCard` rendering
- **Playwright E2E** : flow `/today` → suggest → select → GPX download (check Content-Disposition) → push Garmin (worker mocké via MSW)

### Tests d'intégration manuels (pre-merge)
1. Premier import OSM UNRAID dev → boucle 10km depuis Lyon
2. Override adresse "Place Bellecour Lyon" → coords corrects
3. Download GPX → ouverture Garmin Connect manuel
4. Push Garmin auto → vérif `connect.garmin.com/modern/course/{id}`
5. Session swim/rest → bouton absent
6. Session sans `location_lat` → banner d'erreur

## Quality gates (QUALITY_GATES.md)

- ✅ `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
- ✅ `cd worker && uv run pytest -v && uv run ruff check . && uv run mypy src/`
- ✅ Migration appliquée via `mcp__supabase__apply_migration` (project `peiyrqplymdlmlpsbqzu`)
- ✅ SonarQube ≥95% coverage nouveau code, 0 critical issues
- ✅ Lighthouse PWA score maintenu (Leaflet n'impacte que `/today`)

## Risques

| Risque | Mitigation |
|---|---|
| GraphHopper OOM au démarrage (4 Go RAM) | Limiter par région si problème |
| Garmin change endpoint course-service | Tests d'intégration manuels post-MVP + fallback GPX download |
| Photon flaky | Fallback Nominatim public |
| Tile OSM rate limit (10k/jour) | < 10 users OK ; sinon MapTiler free tier |
| Boucles round_trip irréalistes (chemins privés) | Profils GraphHopper choisis + feedback user post-essai |

## Décomposition prévisionnelle (à raffiner dans plan)

Indication uniquement — le plan d'implémentation détaillera ces tâches.

1. **Infra GraphHopper** : ajouter container, premier import OSM, smoke test round_trip
2. **Migration DB** : `routes`, `route_garmin_exports`, `athlete_profiles.location_lat/lng`
3. **Module worker `routing.py`** : client GraphHopper async
4. **Module worker `geocoding.py`** : client Photon + fallback Nominatim
5. **Module worker `route_generator.py`** : estimate_speed, suggest_routes, scoring
6. **Module worker `gpx.py`** : GeoJSON → GPX
7. **Module worker `garmin_courses.py`** : push course via python-garminconnect
8. **Endpoint worker `/routes/suggest`** + tests
9. **Endpoint worker `/routes/{id}/push-garmin`** + tests
10. **Endpoint worker `/routes/{id}/gpx`** + tests
11. **Server Actions Next.js** : `suggestRoutes`, `pushRouteToGarmin`, `geocodeAddress`
12. **Composants UI** : `RouteSuggestButton`, `RouteSuggestModal`, `RouteCard`, `RouteMap`, `StartOverrideInput`, `ExportActions`
13. **Intégration `/today`** : afficher bouton selon sport
14. **Intégration onboarding/profile** : geocoding du champ `location`
15. **Tests E2E Playwright** flow complet
16. **Doc deploy GraphHopper** : `worker/deploy/README.md` + script refresh OSM

## E8b (out of scope, mentionné pour contexte)

- Parser séance E5 markdown → format Garmin workout structuré (steps, durée, cibles allure/FC/puissance)
- `python-garminconnect.add_workout()`
- Table `workout_exports` (parallèle de `route_garmin_exports`)
- UI : checkbox "Envoyer aussi le workout structuré" dans la modale E8a
- Risque clé : python-garminconnect a `add_workout` officiellement supporté, mais format FIT workout à valider

Spec E8b à écrire après livraison E8a.
