# Widget « Mes cols » → « Mes cols & sommets » — ajout des sommets (natural=peak)

**Date** : 2026-07-12
**EPIC** : Post-MVP / gadget stats
**Priorité** : P2 (fonctionnalité gadget, non bloquante)
**Statut** : spec validée

## Problème / objectif

Le widget « Mes cols » (livré, `docs/superpowers/specs/2026-07-08-cols-stats-widget-design.md`)
ne référence que les nœuds OpenStreetMap tagués `mountain_pass=yes`. Les sommets/crêtes qui
ne sont pas des cols routiers — ex. le Crêt d'Arjoux (natural=peak, 815 m, près de chez
l'owner) — sont donc structurellement invisibles, quelle que soit leur pertinence locale ou
leur proximité avec les tracés GPS de l'utilisateur.

Comparaison faite avec l'app ColQuest (référence du domaine « chasse aux cols/sommets ») :
elle matche aussi les sorties Strava contre une base de sommets OSM, sans distinction stricte
col/pic — modèle proche de ce qui est déjà en place ici via `col_crossings` (détection par
proximité GPS réelle, pas par simple rayon autour du domicile).

## Décisions (brainstorming owner 2026-07-12)

- **Source ajoutée** : tag OSM `natural=peak`, en plus du `mountain_pass=yes` existant, même
  rayon de 50 km autour du domicile calculé.
- **Modèle de données** : extension de la table `cols` existante avec une colonne `type`
  (`'col'` | `'peak'`), pas de nouvelle table. `col_crossings` reste inchangée (déjà générique
  par `col_id`) — sa portée s'élargit simplement aux sommets.
- **Filtre de bruit** : seuil d'altitude **≥ 500 m** appliqué uniquement aux `natural=peak`
  (les cols routiers restent sans filtre, comme aujourd'hui). Un nœud `peak` sans tag `ele`
  est écarté — impossible de vérifier le seuil, on préfère la précision au rappel plutôt que
  d'admettre des buttes non qualifiées.
- **Détection de franchissement** : réutilise telle quelle la logique existante (proximité
  ≤ 150 m du tracé GPS, `recompute_col_crossings`) — aucune distinction de traitement entre
  col et sommet à ce niveau.
- **UI** : un seul widget, renommé **« Mes cols & sommets »**, avec deux sections/tableaux
  triés séparément (cols puis sommets), chacune masquée si vide. Pas de nouveau widget, pas de
  fusion en liste unique badgée.
- **Hors scope** : autres tags OSM (`natural=saddle`, `natural=ridge`, `natural=volcano`…),
  seuil d'altitude configurable par l'utilisateur, mini-carte, renommage des tables/colonnes
  DB existantes (`cols`/`col_crossings` restent tels quels — la colonne `type` porte la
  distinction sémantique, pas le nom de la table).

## Modèle de données

Migration additive Supabase (pas de nouvelle table).

```sql
alter table public.cols
  add column type text not null default 'col'
    check (type in ('col', 'peak'));
```

`col_crossings` ne change pas de schéma. Row `type = 'col'` par défaut pour préserver les
lignes existantes (tous les cols actuels sont issus de `mountain_pass=yes`).

## Pipeline de calcul (worker Python)

### `refresh_nearby_cols` (`worker/src/garmin_sync/coach/overpass.py`)

- Requête Overpass combinée en un seul appel HTTP (union des deux filtres) :

  ```
  [out:json][timeout:25];
  (
    node[mountain_pass=yes](around:50000,{home_lat},{home_lon});
    node[natural=peak](around:50000,{home_lat},{home_lon});
  );
  out;
  ```

- `_build_query` mis à jour pour générer cette requête union.
- Parsing des éléments : le `type` de la ligne upsert est déduit du tag qui a matché
  (`mountain_pass=yes` → `'col'`, `natural=peak` → `'peak'`). Un élément peut théoriquement
  matcher les deux filtres (rare) — dans ce cas `'col'` est prioritaire (un col nommé qui est
  aussi taggé `natural=peak` reste avant tout un col dans l'usage triathlon/vélo).
- Filtre d'altitude appliqué **avant** l'upsert : les éléments `type='peak'` avec
  `elevation_m is None or elevation_m < 500` sont exclus de la liste `rows`. Les éléments
  `type='col'` ne sont pas filtrés (comportement actuel inchangé).
- Reste du pipeline (cache 30 jours / déplacement 5 km, upsert par `osm_id`, gestion des
  erreurs réseau) : **inchangé**, s'applique déjà indifféremment du type de nœud.

### `recompute_col_crossings` (`worker/src/garmin_sync/coach/col_matching.py`)

Aucun changement. La fonction sélectionne déjà « les cols du référentiel `cols` dans un rayon
de 50 km du domicile » sans filtrer par type — elle couvre donc automatiquement les nouveaux
sommets dès qu'ils sont upsertés par `refresh_nearby_cols`.

## Frontend

### `lib/dashboard/cols.ts`

- `ColSummary` gagne un champ `type: 'col' | 'peak'` (lu depuis `cols.type`).
- La fonction d'agrégation regroupe désormais par `type` avant d'appliquer le tri existant à
  l'intérieur de chaque groupe (franchissements décroissants, puis distance croissante pour
  les entrées à 0). Retourne deux listes triées (ou une structure `{ cols, peaks }`) plutôt
  qu'une liste plate.

### `cols-widget.tsx`

- Titre : **« Mes cols & sommets »**. Description ajustée en conséquence (garde la mention du
  rayon de 50 km).
- Deux instances de `ColsTable` — une par section (« Cols », « Sommets ») — chacune rendue
  seulement si sa liste est non vide. Si les deux listes sont vides, l'état vide existant
  s'applique (texte adapté : « Aucun col ni sommet recensé dans un rayon de 50 km autour de
  chez toi. »).
- Le seuil d'affichage `VISIBLE_COUNT` (10) et le mécanisme « Afficher les N autres »
  s'appliquent indépendamment à chaque section.

### États vides

- `lat`/`lon` absents : message inchangé.
- Domicile connu, aucun col **et** aucun sommet ≥ 500 m dans le rayon : nouveau message
  générique (ci-dessus).
- Domicile connu, cols présents mais aucun sommet (ou l'inverse) : la section vide n'est
  simplement pas rendue, pas de message d'état vide dédié par section (évite la surcharge
  visuelle pour un cas mineur).

## Tests

- **Worker (pytest)** :
  - `refresh_nearby_cols` : réponse Overpass mockée contenant les deux tags dans la même
    requête → vérifie le `type` assigné à chaque ligne upsertée ; cas peak sans `ele` (exclu) ;
    cas peak avec `ele < 500` (exclu) ; cas peak avec `ele >= 500` (inclus) ; cas nœud matchant
    les deux filtres (priorité `'col'`).
  - `recompute_col_crossings` : pas de nouveau test requis (comportement déjà générique par
    type), un test de non-régression suffit à confirmer qu'un crossing est bien créé pour un
    col de `type='peak'`.
- **Frontend (Vitest)** : `lib/dashboard/cols.ts` — agrégation par type, tri à l'intérieur de
  chaque groupe, cas une section vide / les deux vides.

## Workflow d'implémentation

Implémentation dans un **git worktree dédié**, branche `feat/e-post-mvp-cols-sommets`, PR en
fin de travail — cf. `superpowers:using-git-worktrees`. La spec reste committée sur `main` en
local.

## Suivi

- `docs/superpowers/BACKLOG.md` : nouvel item « Sommets (natural=peak) dans le widget cols »,
  Post-MVP / P2.
- GitHub Projects « Garmin Training Coach — Backlog » (#4) : item correspondant créé en
  *Todo*, EPIC « Post-MVP », Priorité P2.
