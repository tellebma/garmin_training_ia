# E23 — Vue course : détection, débrief et jalon de progression — design

**Date** : 2026-08-24
**EPIC** : E23 — Vue course
**Priorité** : P1
**Statut** : spec validée, implémentation V1 en cours

## Demande owner

> « J'aimerais que tu ajoutes une chose dans le backlog : la vue course. À prendre en compte
> dans les progressions. De plus j'aimerais que les jours de course, si on détecte une activité,
> on les tag comme course et qu'on ait une page historique quelque peu différente, avec par
> exemple un retour sur la course : les éléments bons, les points d'amélioration, la possibilité
> de rajouter d'autres stats qu'on peut avoir via la course (officielles ou non, par exemple via
> les API de course). J'aimerais prendre en exemple mon premier triathlon, avoir une vue un peu
> spéciale. »

## Problème

Une course n'existe aujourd'hui que **avant** l'épreuve :

- `race_goals` porte l'objectif (date, discipline, `legs`, `target_time_seconds`) ;
- `race_day.py` (PR #174) remplit la séance du jour J (temps estimé, pacing, transitions).

Après l'épreuve, la course **disparaît** : l'activité Garmin retombe dans `/history` comme une
sortie ordinaire. Rien ne dit que c'était une course, le réalisé n'est comparé ni à l'objectif ni
à l'épreuve précédente, et les données propres à la course (temps officiel, classement,
transitions chronométrées) n'ont nulle part où vivre.

## Objectif V1

Faire de la course un **objet de première classe** : détectée, tagguée, débriefée, enrichissable
et comptée dans les progressions.

| Lot | Contenu | Statut V1 |
|---|---|---|
| E23.1 | Détection auto + tag manuel + course rétroactive | dans V1 |
| E23.2 | Page course dédiée (splits, transitions, objectif vs réalisé) | dans V1 |
| E23.3 | Débrief coach (points forts / axes d'amélioration) + ressenti athlète | dans V1 |
| E23.4 | La course comme jalon dans les progressions (`/stats`) | dans V1 |
| E23.5 | Stats externes — **saisie manuelle** | dans V1 |
| E23.5 | Stats externes — **import API chrono** (Njuko, Sporkrono…) | hors V1 |
| E23.6 | Vue « souvenir » — badge première course + chemin parcouru | V1 minimale |

## Choix structurants

### 1. Une course **est** un `race_goal` — pas une nouvelle entité

`race_goals` porte déjà tout ce qui définit une épreuve : date, nom, lieu, discipline, `legs`
(distance et D+ par segment), temps visé. Créer une table `races` dupliquerait ce modèle et
obligerait à synchroniser deux vérités.

Conséquences :

- une course **passée** est un `race_goal` avec `is_primary = false` ;
- une course **jamais planifiée** (épreuve faite avant l'app, ou dossard pris au dernier moment)
  se crée rétroactivement comme `race_goal` — les policies RLS d'insert existent déjà ;
- l'index unique `race_goals_one_primary_per_user` reste satisfait (une seule course *à venir*).

### 2. Rattachement porté par l'activité

```sql
alter table public.activities
  add column race_goal_id uuid references public.race_goals(id) on delete set null,
  add column race_tag_source text check (race_tag_source in ('auto','manual'));
```

Pas de colonne `is_race` séparée : `race_goal_id is not null` **est** le tag. Une seule source de
vérité, pas d'état incohérent possible (`is_race = true` sans course rattachée).

`race_tag_source` distingue le tag automatique du tag posé à la main : la détection auto ne doit
jamais écraser une décision de l'athlète (dé-tagger un footing tagué à tort doit tenir dans le
temps), donc **le re-tag automatique ne touche que les lignes `auto` ou nulles**.

### 3. Détection déterministe côté worker, jamais côté LLM

Une activité est rattachée à une course si **les trois** conditions sont réunies :

1. **date** : `start_time` (date locale UTC) == `race_goals.race_date` ;
2. **discipline** : le sport de l'activité est compatible avec la course — sport du `leg` pour une
   épreuve mono-discipline, l'un des sports des `legs` ou un sport multisport
   (`brick`/`multi_sport`/`triathlon`…) pour une épreuve à transitions ;
3. **volume plausible** : la distance couvre au moins **60 %** de la distance attendue (somme des
   `legs` pour un multisport agrégé, distance du `leg` pour une activité mono-discipline).
   Sans distance exploitable, on retombe sur un plancher de durée (**20 min**).

Le garde-fou 3 évite le faux positif le plus probable : le footing de décrassage ou la reco de
parcours faite le matin même de la course.

Le calcul vit dans une **fonction pure** `match_race_activities()` (worker,
`coach/race_tagging.py`) : entrée = lignes `race_goals` + lignes `activities`, sortie = les
rattachements. La persistance est isolée dans `apply_race_tags()`. Pas d'appel LLM : un
rattachement doit être reproductible et explicable.

Points d'appel :

- **au sync** (`sync_user_for_date_range`), sur la fenêtre synchronisée : une course détectée
  le jour même ;
- **au backfill** (`python -m garmin_sync.coach.backfill_races`), sur tout l'historique : les
  courses déjà passées avant la mise en service, dont le premier triathlon de l'owner.

### 4. Les splits viennent d'`activity_segments` (E22.1), pas d'un nouveau pipeline

Un triathlon Garmin arrive comme **une** activité parent agrégée + N enfants (natation, T1, vélo,
T2, course). E22.1 (PR #207) persiste déjà cette décomposition dans `activity_segments`
(une ligne par discipline **et par transition**). La vue course la lit telle quelle.

Cas dégradé prévu : certaines montres publient les disciplines comme **activités séparées**. La
vue course accepte donc **N activités rattachées** à la même course et reconstruit alors les
transitions par les **trous entre activités** (fin de l'une → début de la suivante).

Ordre de préférence pour construire la ligne de temps :
`activity_segments` de l'activité multisport → sinon les activités rattachées, triées par
`start_time`.

### 5. Débrief coach déterministe (pas de LLM en V1)

Comme pour `race_day.py` et `activity-analysis.ts`, le débrief est **calculé** :

- écart au temps visé (`target_time_seconds`) ;
- part de chaque segment dans le temps total, comparée à la répartition **estimée** par les
  vitesses de référence partagées avec le planner (`estimate_race_time_shares`) ;
- dérive de FC entre première et seconde moitié d'épreuve ;
- coût des transitions (T1/T2) rapporté au temps total ;
- comparaison à la **course précédente de même discipline** (temps total, temps par discipline) ;
- charge de préparation réellement effectuée (volume et nombre de séances entre
  `prep_start_date` et `race_date`).

Sortie : deux listes explicites — **ce qui a marché** / **axes d'amélioration** — plus un verdict
court. Un LLM n'apporterait ici qu'un risque d'analyse inventée sur des chiffres que l'on a déjà.

### 6. Stats externes : saisie manuelle d'abord, import ensuite

Aucune plateforme de chronométrage (Njuko, Sporkrono, ChronoRace, Livetrail, FFTri) n'expose
d'API standardisée ; plusieurs n'en exposent aucune et changent de format de page d'une épreuve à
l'autre. Construire l'import en premier, c'est bâtir 5 adaptateurs fragiles avant d'avoir un seul
écran qui affiche la donnée.

V1 = **table `race_results` + formulaire** : temps officiel, splits officiels
(natation / T1 / vélo / T2 / course), classement scratch et catégorie, dossard, lien résultats,
plus le contexte non mesuré par la montre (météo, nutrition, matériel, incidents, ressenti libre).

Quand un temps **officiel** existe, il prime sur le temps Garmin dans l'affichage et dans les
comparaisons — la montre démarre et s'arrête toujours un peu à côté de la ligne.

V2 (hors périmètre, reste en Todo) : import par URL de résultats derrière un adaptateur par
fournisseur, alimentant exactement les mêmes colonnes.

### 7. Progressions : la course comme jalon

Sur `/stats`, un widget **« Mes courses »** liste les épreuves détectées, du plus récent au plus
ancien : temps retenu (officiel si présent), écart au temps visé, écart à la course précédente de
même discipline, lien vers la vue course. C'est le point d'entrée demandé (« à prendre en compte
dans les progressions ») : la progression d'un triathlète se lit d'abord d'une course à l'autre,
pas d'un footing à l'autre.

## Écrans

### `/history/race/[id]` — la vue course

1. **Bandeau épreuve** : nom, lieu, date, discipline, distances par leg, badge
   **« Première course »** quand c'est la plus ancienne course de l'athlète.
2. **Verdict** : temps total (officiel si connu), écart au temps visé, classement si saisi.
3. **Ligne de temps par segment** : natation / T1 / vélo / T2 / course — durée, distance, allure
   ou vitesse selon la discipline, FC moyenne, part du temps total.
4. **Débrief coach** : ce qui a marché / axes d'amélioration.
5. **Comparaison** : course précédente de même discipline, discipline par discipline.
6. **Le chemin parcouru** : volume, nombre de séances et durée de la préparation.
7. **Résultats officiels & ressenti** : formulaire de saisie (repliable, pré-rempli).
8. **Carte du parcours** et lien vers les activités sources.

### `/history/[id]` — fiche activité

Bandeau « Cette activité fait partie de la course *X* » avec lien, plus l'action
**marquer / démarquer comme course** (et création rétroactive de l'épreuve si aucune n'existe à
cette date).

### `/history` — liste

Badge **Course** sur les activités taguées.

## Modèle de données

```sql
-- Rattachement activité → course
alter table public.activities
  add column race_goal_id uuid references public.race_goals(id) on delete set null,
  add column race_tag_source text check (race_tag_source in ('auto','manual'));

-- Résultats officiels et ressenti (1 ligne par course)
create table public.race_results (
  race_goal_id uuid primary key references public.race_goals(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  official_time_s integer,
  swim_time_s integer, t1_time_s integer, bike_time_s integer,
  t2_time_s integer, run_time_s integer,
  overall_rank integer, overall_finishers integer,
  category text, category_rank integer, category_finishers integer,
  bib_number text, results_url text,
  weather text, nutrition text, gear text, incidents text, comment text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

RLS : select / insert / update / delete réservés au propriétaire (`auth.uid() = user_id`).

Tag manuel : RPC `set_activity_race(p_activity_id uuid, p_race_goal_id uuid)` et
`clear_activity_race(p_activity_id uuid)` en `security definer` (RLS sur `activities` n'autorise
que la lecture côté client), avec `revoke execute … from public, anon` — piège SEC-2 déjà vécu.

## Périmètre exclu (reste en Todo)

- Import automatique des résultats depuis les plateformes de chronométrage (E23.5 V2).
- Récit narratif long et export partageable de la vue souvenir (E23.6 complet) — la V1 se limite
  au badge « Première course » et au bloc « chemin parcouru ».
- Repères de course dessinés **dans** les graphiques Banister / volume : le widget « Mes courses »
  couvre le besoin de lecture ; les `ReferenceLine` viendront avec E14.
- Débrief rédigé par LLM.
