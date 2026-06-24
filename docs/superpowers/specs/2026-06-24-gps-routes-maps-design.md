# Spec — Cartes & traces GPS des activités (sous-spec carto)

- **Date** : 2026-06-24
- **EPIC parapluie** : Refonte graphique & cartographie (sous-spec **A : cartographie**)
- **Statut** : validé en brainstorming, prêt pour plan d'implémentation
- **Auteur** : owner + Claude

## Contexte

L'app affiche déjà des courbes d'activité (FC, altitude, puissance, cadence, allure)
via `recharts` sur la page détail (`app/(app)/history/[id]`). En revanche **aucune
coordonnée GPS n'est stockée** : la table `activity_samples` contient les métriques
temporelles mais pas de latitude/longitude, et il n'existe aucune librairie de carte
dans le projet.

Le worker récupère déjà `get_activity_details` de Garmin et normalise les métriques
par clé (`transformers/activities.py`). Garmin expose les coordonnées GPS dans **le
même payload** sous les clés `directLatitude` / `directLongitude`, actuellement
**ignorées**. Ajouter les cartes ne nécessite donc **aucun appel API supplémentaire**
pour les nouvelles activités — seulement l'extraction de clés déjà présentes.

## Objectif

Afficher les traces GPS des activités vélo et course :

1. Carte interactive de la trace sur la page détail activité.
2. Trace colorée selon une métrique (FC / vitesse / altitude).
3. Vignette de la trace dans chaque ligne de l'historique.
4. Heatmap globale de toutes les traces sur la page stats.

## Décisions validées

| Sujet | Décision | Raison |
|---|---|---|
| Librairie carte | **MapLibre GL JS** | Rendu vectoriel GPU ; gère nativement heatmap, `line-gradient` (trace colorée) et superposition dense. Sans clé API. |
| Fond de carte | **CARTO dark** (tuiles gratuites, sans clé) | Compatible thème dark existant. |
| Vignette historique | **Tracé SVG sans fond de carte** | Zéro requête réseau, rapide même avec 50+ lignes ; pas de N instances WebGL. |
| Backfill GPS | **Throttlé** (N activités/run cron, des plus récentes aux plus vieilles) | Respecte le rate-limit agressif de Garmin (piège connu). |
| Stockage | 2 niveaux : `activity_samples.lat/lng` (pleine résolution) + `activities.route_polyline` (downsamplé ~64 pts) | Éviter de charger 2000 pts × N activités dans les listes/heatmap. |

## Architecture

### 1. Modèle de données

**Migration Supabase additive** (nouveau fichier `supabase/migrations/`), non breaking
(colonnes nullable) :

- `activity_samples` :
  - `latitude numeric(9,6)` — check `latitude is null or latitude between -90 and 90`
  - `longitude numeric(9,6)` — check `longitude is null or longitude between -180 and 180`
  - Pleine résolution → alimente le **tracé détail coloré par métrique**.
- `activities` :
  - `route_polyline jsonb` (nullable) — géométrie compacte downsamplée (~64 points
    `[lng, lat]`), calculée au sync quand le GPS est disponible.
  - Alimente **vignettes SVG** + **heatmap globale** (requête minuscule, rendu léger).

> Choix `jsonb` plutôt que polyline encodée Google : lisible, pas de dépendance de
> décodage côté front, taille négligeable pour ~64 points.

### 2. Worker (extraction + downsampling + backfill)

**`transformers/activities.py`**
- Ajouter `_LAT_KEYS = ("directLatitude", "latitude")` et
  `_LON_KEYS = ("directLongitude", "longitude")`.
- Extraire `latitude` / `longitude` dans chaque sample normalisé (valeurs nulles
  tolérées : indoor, trous GPS). L'extraction reste **défensive** (clés multiples)
  comme le reste du transformer.
- Le signal d'inclusion d'un sample (`_has_sample_signal`) reste inchangé : on ne crée
  pas de sample pour du GPS seul, on enrichit les samples existants.

**Downsampling polyline** (nouvelle fonction pure, ex. `transformers/route.py` ou
util dans `activities.py`)
- Entrée : liste de samples GPS ordonnés. Sortie : ~64 points `[lng, lat]` au plus.
- Stratégie : pas-fixe (1 point sur N) ou Ramer–Douglas–Peucker léger. Filtrer les
  points sans coordonnées. Si < 2 points GPS valides → `route_polyline = null`.

**`sync.py`**
- Lors du sync des samples d'une activité, calculer et écrire `activities.route_polyline`.
- **Nouvelle passe `_sync_missing_gps(db, user_id, client, limit=N)`** :
  - Sélectionne les N activités du user **sans GPS** (`route_polyline is null`),
    triées `start_time desc` (récentes d'abord).
  - Re-fetch `get_activity_details`, upsert `latitude/longitude` dans `activity_samples`
    et écrit `route_polyline`.
  - `N` = config `GPS_BACKFILL_BATCH` (défaut **8**).
  - Tourne à chaque run cron jusqu'à épuisement du backlog.
  - Respecte le wrap 429 existant ; échec sur une activité loggé (`log.exception`) sans
    bloquer les autres (même pattern que `_sync_missing_activity_samples`).

**`config.py`**
- Ajouter `GPS_BACKFILL_BATCH: int = 8` (Pydantic settings).

### 3. Frontend — rendu

**Dépendance** : ajouter `maplibre-gl` au `package.json`. Tous les composants carte
sont **client-only** (`dynamic(() => import(...), { ssr: false })`) pour éviter le SSR
de WebGL.

Nouveaux composants dans `app/(app)/_components/` (proches des charts existants) :

- **`maps/activity-route-map.tsx`** (détail activité)
  - Fond CARTO dark, trace en `line-gradient` colorée par métrique sélectionnable
    (FC / vitesse / altitude) via un petit toggle (réutilise les conventions UI
    existantes : `ChartCard`, boutons shadcn).
  - Données = samples GPS pleine résolution → GeoJSON `LineString` + valeurs métriques
    normalisées `[0,1]` le long de la ligne (`line-progress`).
  - Centrage/zoom auto sur la bounding box de la trace.
- **`maps/route-thumbnail.tsx`** (liste historique)
  - **SVG pur**, pas de tuiles. Prend `route_polyline`, normalise dans un `viewBox`,
    dessine une `<polyline>`/`<path>`. Couleurs du thème dark (token `--primary`).
  - Intégré dans chaque carte de la liste `history` (rendu serveur OK, c'est du SVG
    statique). Fallback discret si `route_polyline` absent (pas de trace → pas de
    vignette ou placeholder neutre).
- **`maps/routes-heatmap.tsx`** (page stats)
  - MapLibre + `heatmap` layer alimenté par l'agrégat de tous les `route_polyline`.
  - Nouvelle section « Où je m'entraîne » sur `app/(app)/stats`.

**Requêtes de données**
- Détail (`history/[id]`) : étendre le `select` existant sur `activity_samples` pour
  inclure `latitude, longitude`.
- Liste (`history/page.tsx`) : ajouter `route_polyline` au `select` des activités.
- Stats : nouvelle requête `select route_polyline from activities where route_polyline is not null`.

**Utils** (`lib/`)
- Builder GeoJSON depuis samples GPS.
- Normalisation/projection des points pour le `viewBox` SVG (réutilisable thumbnail).

### 4. Tests

**Worker (pytest)**
- Extraction lat/lng : payload avec GPS, payload indoor/sans GPS (→ null), clés
  alternatives.
- Downsampling : ≤ 64 points en sortie, ordre préservé, < 2 pts GPS → `null`.
- Sélection backfill : ordre `start_time desc`, respect de la limite, exclusion des
  activités ayant déjà `route_polyline`.

**Frontend (vitest)**
- Util downsampling/normalisation viewBox (cas bbox dégénérée : trace ponctuelle).
- Builder GeoJSON.
- Rendu `RouteThumbnail` (path SVG attendu, absence de trace gérée).

Respect du **quality gate SonarQube** (97% coverage, gate enforced).

### 5. Déploiement / risques

- Migration additive (colonnes nullable) → pas de breaking change ni de downtime.
- Image Docker worker à rebuild/push : le workflow Hub ne build que sur `main` ; pendant
  le dev feature, `docker build && docker push tellebma/garmin-sync:latest` à la main
  pour tester en réel.
- Variabilité du schéma `get_activity_details` Garmin → extraction défensive (déjà la
  philosophie du transformer).
- Rate-limit Garmin : seul le backfill génère des appels supplémentaires, plafonné par
  `GPS_BACKFILL_BATCH`.

## Découpage en livrables

Deux livrables séquentiels (chacun = un plan / une PR) :

- **Livrable A — Pipeline data** : migration + extraction worker + downsampling +
  backfill throttlé + `ActivityRouteMap` (trace simple sur la page détail). À la fin,
  les traces sont visibles sur le détail activité.
- **Livrable B — Rendu enrichi** : trace colorée par métrique (toggle), vignettes SVG
  dans l'historique, heatmap globale sur la page stats.

## Hors périmètre (YAGNI)

- Génération d'images PNG de trace côté worker (Supabase Storage) — écarté au profit du
  SVG.
- Export GPX / partage de trace.
- Édition/découpe de trace.
- Le second sous-spec **B (refonte graphique)** fera l'objet d'un brainstorming séparé.

## Critères de succès

1. Une activité vélo/course avec GPS affiche sa trace sur une carte dark interactive.
2. La trace peut être colorée par FC / vitesse / altitude.
3. La liste historique montre une vignette SVG de chaque trace, sans coût réseau.
4. La page stats affiche une heatmap de toutes les traces.
5. L'historique existant se remplit progressivement via le backfill, sans déclencher de
   blocage Garmin.
6. Quality gates verts (lint, typecheck, tests, build, Sonar).
