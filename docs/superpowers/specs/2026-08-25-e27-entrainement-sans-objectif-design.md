# E27 — Entraînement sans objectif : maintien et progression continue — design

**Date** : 2026-08-25
**EPIC** : E27 — Entraînement sans objectif
**Priorité** : P1
**Prérequis fonctionnel de** : E26 (après-course) — les choix « maintenir » et « progresser »
n'ont d'effet que si ce moteur existe.

## Demande owner

> « Ce que l'utilisateur veut faire : définir un nouveau goal, maintenir l'état actuel, juste
> s'améliorer sans pour autant choisir un nouveau goal. »

## Problème

Tout le moteur de plan dérive d'une `race_date` : ancre de préparation, phases, rampes, taper,
séance du jour J. Sans course future, `_load_plan_inputs` renvoie `no_race_goal` ou
`race_in_past` et **rien n'est généré** (`planner.py:1299-1304`).

Un athlète entre deux objectifs, ou qui s'entraîne sans en viser aucun, n'a donc aucun plan —
alors que c'est l'état le plus courant hors saison, et l'état par défaut le lendemain de chaque
course.

## Le constat qui dimensionne l'EPIC

Le moteur existant fait déjà presque tout. Trois briques seulement supposent une course :

| Brique | Rôle | Sans course |
|---|---|---|
| `compute_phases(start, race_date)` | découpage base/build/peak/taper | à remplacer par un cycle |
| `compute_week_load_multipliers(phases)` | courbe de charge hebdo | déjà bonne, à paramétrer |
| `RaceTarget` | jour J, legs, D+, parts par discipline | à rendre optionnel |

Tout le reste — sélection des jours, rotation des disciplines, types de séance par niveau,
budget TSS par sport, plafond de rampe, cible de D+, génération LLM de la séance — est
indépendant de l'existence d'une épreuve et se réutilise **tel quel**.

## Choix structurants

### 1. Le maintien est le **point fixe** du modèle, pas une nouvelle formule

`compute_base_weekly_tss` vaut `ctl × 7`. Or à l'équilibre du modèle exponentiel, la CTL est la
moyenne glissante du TSS quotidien : **maintenir sa CTL, c'est produire exactement `7 × CTL` de
TSS par semaine**. Le mode maintien n'a donc besoin d'aucun calcul nouveau — c'est
`base_weekly` avec un multiplicateur hebdomadaire de **1.0**.

La progression, symétriquement, c'est le `NORMAL_RAMP_RATE = 1.05` déjà en place. Les deux modes
se réduisent à **une courbe de multiplicateurs différente**, pas à un second moteur.

### 2. Le piège de l'horizon roulant : la rampe ne doit être appliquée qu'**une fois**

`base_weekly` est recalculé à chaque génération depuis la **CTL mesurée du jour**. En mode course
c'est sans danger : la fenêtre est bornée et le plafond horaire borne la dérive.

Avec un horizon **roulant régénéré chaque semaine**, appliquer `progression^k` à une CTL qui a
déjà monté de 5 % la semaine précédente compose deux fois la même progression — la charge
demandée explose en quelques semaines.

Deux règles, non négociables :

- **les multiplicateurs sont intra-cycle, sans mémoire** : ils valent la position dans le cycle
  de 4 semaines, jamais une progression cumulée depuis le début du mode. La semaine 0 de
  l'horizon est ancrée sur la CTL réellement mesurée ; les semaines 1 à 3 ne servent qu'à
  **dessiner** ce qui vient, et seront recalculées avant d'être exécutées.
  **La progression réelle d'un cycle à l'autre est portée par la CTL mesurée qui monte**, pas
  par la composition des facteurs — c'est ce qui rend le mode `improve` auto-régulé : une
  semaine encaissée fait monter la base, une semaine sautée ne la fait pas monter ;
- **le deload est ancré sur un calendrier absolu**, pas sur l'offset dans l'horizon. Sinon la
  4ᵉ semaine n'arrive jamais : l'horizon repart à zéro chaque semaine, et le deload recule
  indéfiniment. L'ancre est `training_mode_since` :
  `semaine_de_cycle = ((today - training_mode_since).days // 7) % 4`.

C'est le même raisonnement que l'ancre `prep_start_date` d'E13 (« la périodisation ne se
recalcule pas depuis `today` ») — appliqué à un plan qui n'a pas de fin.

### 3. `training_mode` est la **source de vérité unique**

```sql
alter table public.athlete_profiles
  add column training_mode text not null default 'race'
    check (training_mode in ('race', 'maintain', 'improve')),
  add column training_mode_since date;
```

Le risque évident serait deux vérités : la colonne d'un côté, l'existence d'un `race_goal`
primaire futur de l'autre. La règle est donc que **créer un objectif écrit `training_mode =
'race'` dans la même transaction** (comme `answer_post_race_prompt` écrit le mode pour les deux
autres choix, E26.4). `generate_plan` lit la colonne, et elle seule, pour choisir sa branche.

`training_mode_since` est l'ancre de cycle du §2 : elle ne bouge qu'au **changement de mode**,
jamais à la régénération.

### 4. Cycles 3 + 1, sans taper ni pic

`compute_cycle_phases(weeks: int, mode, *, cycle_week: int)` produit la même structure
`[(offset, phase)]` que `compute_phases`, ce qui laisse tout l'aval inchangé :

| Mode | Cycle de 4 semaines | Multiplicateurs |
|---|---|---|
| `maintain` | `base`, `base`, `base`, `base` (4ᵉ = deload) | 1.0, 1.0, 1.0, 0.70 |
| `improve` | `base`, `build`, `build`, `base` (4ᵉ = deload) | 1.0, 1.05, 1.10, 0.75 |

Ces facteurs sont **relatifs à la CTL du moment**, et se répètent à l'identique à chaque cycle :
`compute_week_load_multipliers` ne convient pas telle quelle ici, puisqu'elle compose sa
progression d'une semaine à l'autre (comportement voulu sur un plan borné par une course, fatal
sur un plan sans fin — cf. §2).

Ni `peak` ni `taper` : ce sont des phases d'affûtage **vers une date**, elles n'ont aucun sens
sans épreuve. `pick_session_types_for_phase` fournit déjà les types adaptés à `base` et `build`,
plafonnés par le niveau de l'athlète — rien à écrire.

Horizon : **4 semaines**, régénéré chaque semaine par le cron existant. Assez pour voir venir un
bloc et sa décharge, assez court pour que la projection ne mente pas.

### 5. `RaceTarget` devient `TrainingTarget`, avec un jour J optionnel

`race` n'est utilisé qu'à cinq endroits : `time_shares` (répartition des disciplines),
`has_bike_run_transition` (séances d'enchaînement), `dplus_by_sport` (cible de D+), `day` +
`sport` + `legs` + `athlete` (séance du jour J). Fabriquer une fausse course pour les satisfaire
serait un mensonge qui remonterait partout (J-N sur `/today`, vue course, stats).

À la place : renommage en `TrainingTarget` avec `race_day: date | None`. Quand il est `None`,
`_race_day_session` n'est jamais appelé et la dernière semaine n'a rien de particulier.
Refactor mécanique, sans changement de comportement en mode course — à couvrir par les tests
existants du planner avant d'ajouter quoi que ce soit.

Sans course, les entrées manquantes se dérivent de l'athlète, pas de l'épreuve :

- **disciplines** : celles que l'athlète pratique réellement (historique 90 j, même source que
  `load_effective_strengths`), à défaut ses `sports_strengths` ;
- **parts de temps** : proportionnelles au temps observé par discipline sur 90 jours — on
  maintient ce qui est pratiqué, on ne réinvente pas une répartition triathlon ;
- **D+ cible** : le D+ hebdomadaire **observé**, maintenu (`observed_weekly_dplus`), au lieu
  d'une progression vers le D+ d'une course.

### 6. Semaine de récupération post-course, quel que soit le cap

Prioritaire sur tout le reste : si une course a eu lieu dans la fenêtre récente, les jours qui
suivent sont en récupération, **y compris** si l'athlète enchaîne sur un nouvel objectif. Le
barème est dérivé de la durée de l'épreuve, pas de son format déclaré (un « olympique » bouclé
en 3h30 fatigue plus qu'un sprint en 1h10) :

| Durée de l'épreuve | Récupération |
|---|---|
| < 1 h 30 | 3 jours (recovery / repos) |
| 1 h 30 – 4 h | 1 semaine |
| > 4 h | 2 semaines |

Pendant la fenêtre : uniquement `recovery` et `endurance` courte, multiplicateur de charge
0.5 la première semaine, 0.75 la seconde. Aucune séance de qualité, aucune longue.

### 7. Ce que devient un plan de course en cours

`generate_plan` supprime les séances du plan précédent avant d'insérer (idempotence acquise) :
une bascule de mode régénère simplement, il n'y a pas d'état intermédiaire à gérer. Les séances
**passées** ne sont pas touchées — elles portent l'historique du réalisé.

## Statuts de retour

`race_in_past` et `no_race_goal` cessent d'être des impasses :

| Situation | Aujourd'hui | Après E27 |
|---|---|---|
| Course future | plan périodisé | inchangé |
| Course passée, mode `maintain` / `improve` | `race_in_past` | plan cyclique |
| Course passée, mode `race` (pas encore répondu) | `race_in_past` | récup puis maintien (E26.6) |
| Jamais de course, mode `race` (onboarding incomplet) | `no_race_goal` | inchangé |

Le dernier cas reste une impasse **volontairement** : un athlète qui n'a pas fini son onboarding
doit finir son onboarding, pas recevoir un plan par défaut.

## Tests

- `compute_cycle_phases` — cycle correct pour chaque mode, deload à la bonne semaine absolue
  quelle que soit la date de régénération.
- **Non-régression de la double rampe** : régénérer 6 semaines de suite en mode `improve` avec
  une CTL qui suit la charge produite ne doit pas dépasser la progression théorique de +5 %/sem
  (c'est le test qui protège du piège §2 — sans lui, le bug est invisible en revue).
- Maintien — sur 8 semaines simulées, la CTL projetée reste dans ±5 % de la CTL de départ.
- `TrainingTarget` — les tests existants du planner en mode course doivent passer **sans
  modification de leurs attentes** après le refactor.
- Récupération post-course — les trois tranches de barème, et la priorité sur le mode choisi.
- Plafond horaire — la rampe `improve` converge vers `hours_cap` et ne le dépasse jamais.

## Hors périmètre V1

- Blocs thématiques choisis par l'athlète (« bloc côtes », « bloc vitesse ») — c'est du coaching
  dirigé, pas du maintien.
- Périodisation inverse ou polarisée paramétrable.
- Reprise après blessure / arrêt long : la CTL mesurée s'en charge mécaniquement (elle a chuté,
  la charge suit), mais un vrai protocole de reprise progressive est un sujet à part.
