# Widget « Mes cols » — cols autour de chez moi + nombre de franchissements

**Date** : 2026-07-08
**EPIC** : Post-MVP / gadget stats
**Priorité** : P2 (fonctionnalité gadget, non bloquante)
**Statut** : spec validée

## Problème / objectif

L'utilisateur veut, dans ses statistiques, une liste des cols situés autour de son
domicile avec, pour chacun, le nombre de fois où il l'a gravi au fil de ses activités
Garmin. Aucune donnée de ce type n'existe aujourd'hui : ni référentiel de cols, ni
coordonnées domicile, ni logique de détection de franchissement sur les tracés GPS.

## Décisions (brainstorming owner 2026-07-08)

- **Source des cols** : automatique via l'API Overpass (OpenStreetMap), tag
  `mountain_pass=yes`, dans un rayon de **50 km** autour du domicile.
- **Domicile** : pas de saisie manuelle — déduit automatiquement de la **médiane** des
  points de départ GPS de toutes les activités de l'utilisateur (robuste face à un
  voyage ponctuel, contrairement à une moyenne).
- **Détection de franchissement** : proximité — le tracé GPS de l'activité passe à
  moins de **150 m** du point sommital du col. Pas de distinction montée/descente (« j'ai
  fait ce col », peu importe le sens).
- **Sports concernés** : toutes activités disposant de données GPS (pas de filtre par
  discipline).
- **Périmètre affiché** : **tous** les cols du rayon de 50 km, y compris ceux jamais
  gravis (affichés à « 0 fois ») — effet « bucket list ».
- **Calcul** : intégré au cron worker quotidien existant (`_run_post_sync_recomputes`),
  pas de calcul à la volée côté Next.js. Résultats persistés en base, lus tels quels par
  la page stats.
- **Limitation assumée** : au plus **1 franchissement compté par activité et par col**.
  Un aller-retour sur le même col dans une seule sortie ne compte qu'une fois — évite la
  complexité de détecter des passages multiples dans un même tracé, cas rare en usage
  triathlon.

## Modèle de données

Nouvelle migration Supabase.

```sql
-- Référentiel global des cols (partagé entre users, alimenté depuis OSM)
create table public.cols (
  id uuid primary key default gen_random_uuid(),
  osm_id bigint not null unique,
  name text not null,
  latitude numeric(9,6) not null
    check (latitude between -90 and 90),
  longitude numeric(9,6) not null
    check (longitude between -180 and 180),
  elevation_m integer,
  fetched_at timestamptz not null default now()
);

alter table public.cols enable row level security;

create policy "authenticated users read cols"
  on public.cols for select
  to authenticated
  using (true);
-- Pas de policy insert/update/delete : écriture réservée au service role (worker).

-- Franchissements détectés par activité
create table public.col_crossings (
  user_id uuid not null references auth.users(id) on delete cascade,
  col_id uuid not null references public.cols(id) on delete cascade,
  garmin_activity_id bigint not null,
  crossed_at timestamptz not null,       -- start_time de l'activité
  min_distance_m numeric(6,1) not null,  -- distance mini mesurée au sommet
  primary key (user_id, col_id, garmin_activity_id)
);

create index col_crossings_user_col_idx
  on public.col_crossings (user_id, col_id);

alter table public.col_crossings enable row level security;

create policy "users read own col crossings"
  on public.col_crossings for select
  using (auth.uid() = user_id);

-- Colonnes ajoutées à athlete_profiles
-- Note : `lat`/`lon` existent déjà dans le schéma initial (E1) mais ne sont
-- utilisées nulle part dans le code — on les réutilise pour le domicile calculé
-- au lieu d'ajouter des colonnes redondantes.
alter table public.athlete_profiles
  add column home_computed_at timestamptz,
  add column cols_cache_updated_at timestamptz,
  -- position du domicile au moment du dernier fetch Overpass réussi (pour détecter
  -- un déplacement > 5km et redéclencher un refresh même si < 30 jours)
  add column cols_cache_home_lat numeric(9,6),
  add column cols_cache_home_lon numeric(9,6),
  add column col_matching_cursor timestamptz;
```

Toute écriture sur `cols` et `col_crossings` passe par le client service-role du worker
(comme `activities`, `activity_samples`, etc.) — pas de policy insert côté client.

## Pipeline de calcul (worker Python)

Trois fonctions nouvelles, appelées dans l'ordre depuis
`_run_post_sync_recomputes(user_id)` (`worker/src/garmin_sync/cron.py`), chacune
encapsulée dans son propre `try/except` + `capture()` Sentry (même pattern que
`recompute_daily_state` / `recompute_recovery_baselines` existants) pour qu'un échec
n'interrompe jamais le reste du cron.

### 1. `compute_home_location(user_id)`

Nouveau module `worker/src/garmin_sync/coach/home_location.py`.

- Récupère le premier point (`route_polyline[0]`, format `[lng, lat]`) de chaque
  activité GPS de l'utilisateur (`activities.route_polyline is not null`).
- Calcule la médiane de latitude et la médiane de longitude séparément.
- Écrit `lat`, `lon`, `home_computed_at` dans `athlete_profiles` (colonnes `lat`/`lon`
  existantes, réutilisées).
- Si aucune activité GPS : ne touche à rien (colonnes restent `null`, le reste du
  pipeline est skip côté frontend via l'état vide).

### 2. `refresh_nearby_cols(home_lat, home_lon)`

Nouveau module `worker/src/garmin_sync/coach/overpass.py`.

- Requête Overpass API :
  `node[mountain_pass=yes](around:50000,{home_lat},{home_lon});out;`
- Upsert dans `cols` par `osm_id` (conflict → update `name`/`latitude`/`longitude`/
  `elevation_m`/`fetched_at`).
- Se déclenche uniquement si l'une de ces conditions est vraie (sinon skip, pas d'appel
  réseau) :
  - `cols_cache_updated_at` est `null` (jamais fetché) ;
  - `cols_cache_updated_at` a plus de 30 jours ;
  - le domicile a bougé de plus de 5 km depuis le dernier fetch (comparaison avec
    `cols_cache_home_lat`/`cols_cache_home_lon`, mis à jour à chaque fetch réussi).
- Timeout explicite sur l'appel HTTP (Overpass est un service public, parfois lent ou
  indisponible) ; toute erreur réseau est loggée + capturée Sentry, sans lever
  d'exception qui remonterait au cron.

### 3. `recompute_col_crossings(user_id)`

Nouveau module `worker/src/garmin_sync/coach/col_matching.py`.

- Sélectionne les cols du référentiel `cols` dans un rayon de 50 km du domicile
  (distance haversine calculée en Python — volume faible, pas besoin de PostGIS).
- Sélectionne les activités GPS de l'utilisateur avec
  `start_time > col_matching_cursor` (ou tout l'historique si le curseur est `null` —
  couvre automatiquement le backfill initial, sans script séparé).
- Pour chaque activité sélectionnée :
  - charge ses `activity_samples` (lat/lng pleine résolution — plus précis que le
    `route_polyline` downsamplé à 64 points, qui pourrait manquer un passage bref près
    d'un col sur un tracé long) ;
  - pour chaque col proche, calcule la distance mini entre le tracé et le point
    sommital du col ;
  - si la distance mini est ≤ 150 m → upsert une ligne dans `col_crossings`.
- Une fois toutes les activités du batch traitées, avance `col_matching_cursor` au
  `start_time` maximum traité.

Ce découpage en 3 fonctions pures/testables isolément suit le pattern existant de
`worker/src/garmin_sync/transformers/`.

## Frontend

### Widget sur `/stats` — chargement asynchrone, non bloquant

**Contrainte performance** : ce widget ne doit **jamais ralentir le rendu initial** de
la page stats. Il est donc **isolé du `Promise.all` principal** de `CockpitBody` :

- Nouveau composant serveur async dédié, ex. `<ColsWidget userId={userId} />`, qui fait
  ses propres requêtes Supabase (`athlete_profiles.lat/lon`, `cols`,
  `col_crossings`) indépendamment du reste du cockpit.
- Rendu dans sa **propre frontière `<Suspense>`**, avec un fallback skeleton dédié
  (nouveau `ColsWidgetSkeleton`, à l'image de `CockpitSkeleton` déjà utilisé pour
  l'ensemble de la page — voir `app/(app)/_components/skeletons/`).
- Placé dans `StatsPage` (ou `CockpitBody`) de façon à démarrer son fetch **en
  parallèle** du reste (pas en cascade après le `Promise.all` principal) : le composant
  et son Suspense sont montés dès le rendu du parent, React/Next déclenche le fetch dès
  que le composant async démarre, indépendamment de la résolution du `Promise.all` du
  cockpit.
- Résultat perçu : le cockpit principal (déjà rapide) s'affiche sans attendre les
  données cols ; le widget cols affiche son skeleton puis se peuple dès que ses
  requêtes répondent — jamais l'inverse.

Requêtes Supabase server-side, propres à ce composant :

- `athlete_profiles` : `lat`, `lon`.
- `cols` : tous les cols (dataset global de petite taille), filtrage par distance
  ≤ 50 km du domicile fait côté TypeScript après fetch.
- `col_crossings` de l'utilisateur, groupés par `col_id` (count + `max(crossed_at)`).

Fonction pure d'agrégation dans un nouveau fichier `lib/dashboard/cols.ts` :
regroupe les crossings par col, calcule le nombre de passages et la distance au
domicile, trie par nombre de passages décroissant puis par distance croissante pour
les cols à 0. Testée en Vitest, à l'image des autres fonctions de `lib/dashboard/`.

Rendu (table simple, cohérent avec les autres widgets texte de la page) :

| Nom | Altitude | Distance | Grimpé |
|---|---|---|---|
| Col du Truc | 1850 m | 12 km | 4 fois |
| Col du Machin | 1200 m | 28 km | 0 fois |

### États vides

- `lat` / `lon` absents (pas assez d'activités GPS) : message
  « Pas encore assez de données GPS pour situer chez toi. »
- Domicile connu mais aucun col dans le rayon de 50 km (région sans relief significatif
  au sens OSM) : message « Aucun col recensé dans un rayon de 50 km autour de chez
  toi. »

Aucun appel réseau (Overpass) n'est déclenché depuis le frontend — tout passe par le
worker et la base.

## Tests

- **Worker (pytest)** :
  - `compute_home_location` : médiane sur plusieurs activités, cas aucune activité GPS.
  - `refresh_nearby_cols` : client Overpass mocké — upsert par `osm_id`, skip si cache
    frais (< 30 jours et déplacement < 5 km), gestion d'une erreur réseau (timeout).
  - `recompute_col_crossings` : seuil 150 m (cas juste dans/hors seuil), avancement du
    curseur, cas sans activité GPS, cas aucun col à proximité.
- **Frontend (Vitest)** : `lib/dashboard/cols.ts` — groupement par col, tri, cas 0
  franchissement, cas liste de cols vide.

## Workflow d'implémentation

Implémentation dans un **git worktree dédié** (pas dans le clone principal), sur une
branche `feat/cols-widget`, poussée puis mergée via PR en fin de travail — cf.
`superpowers:using-git-worktrees`. La spec elle-même peut rester committée sur `main`
en local.

## Hors scope

- Édition manuelle de la liste des cols par l'utilisateur.
- Distinction montée stricte vs simple passage.
- Mini-carte visuelle des cols (liste/tableau uniquement pour cette V1).
- Notion de « domicile » explicitement saisi par l'utilisateur (recalcul automatique
  uniquement).
