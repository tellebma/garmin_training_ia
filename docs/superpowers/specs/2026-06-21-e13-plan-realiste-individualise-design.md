# E13 — Plan d'entraînement réaliste et individualisé — Design

**Date** : 2026-06-21
**EPIC** : E13 (P0)
**Statut** : spec validé en brainstorming, à transformer en plan d'implémentation

## Contexte et problème

Les séances générées sont systématiquement **trop courtes et irréalistes** (ex. « vélo
endurance » de 45 min avec 15 min d'échauffement, 18 min de corps et 12 min de retour au
calme). En parallèle, le niveau auto-déclaré par discipline (`sports_strengths`, note 1-5
par sport) est saisi à l'onboarding mais **sous-exploité** par le moteur, et un athlète qui
se déclare disponible 7 jours se voit programmer 7 jours d'entraînement, ce qui est une
erreur de coaching (le repos fait partie de l'entraînement).

### Diagnostic technique (audit du moteur)

1. **Volume hebdo sous-estimé** : `planner.py:572` calcule `weekly_tss = ctl × 7`. Le CTL
   est une moyenne lissée sur *tous* les jours (repos inclus) ; le multiplier par 7
   sous-estime le volume réel d'un athlète qui ne s'entraîne pas 7 j/7 ou qui revient d'une
   coupure. Levier dominant de la régression.
2. **Table `_TSS_PER_HOUR` trop élevée** (`planner.py:159-178`, run 55 / bike 45 / swim 60
   en endurance) : durée = TSS / TSS_h, donc surestimer le TSS/h raccourcit mécaniquement
   chaque séance.
3. **Aucun plancher de durée absolu** : ni dans le prompt LLM (`openai_client.py:18-38`),
   ni dans la validation (`workout_schema.py:82-92`, qui ne contrôle que l'écart ±10 % à la
   cible). Une cible aberrante de 18 min passe sans alerte.
4. **Niveau par discipline sous-exploité** : `sports_strengths` n'agit que sur la
   répartition du volume entre sports (3 paliers grossiers +20 % / 0 / −10 %,
   `planner.py:33-55`) et comme ligne de texte dans le prompt LLM (`openai_client.py:67`).
   Jamais sur l'intensité, le choix des types de séance, ni les durées.
5. **`available_days` traité comme cible** : tout jour hors `available_days` devient repos
   (`planner.py:425-426`), mais aucun cap de fréquence ni plancher de repos n'est appliqué
   quand l'athlète déclare beaucoup de jours.
6. **Repos = repos (UI)** : la section séance de `/today` gère déjà correctement le repos
   (empty state, aucun workout). En revanche les blocs briefing orientés séance
   (`coach_recommendation`, `last_session_feedback`, `next_session_adjustment`) restent
   affichés un jour de repos.

## Périmètre

**Inclus** :
- E13.1 — Durées réalistes (approche hybride).
- E13.2 — Exploitation du niveau par discipline : volume + intensité/types de séance.
- E13.4 — Repos = repos (UI).
- E13.5 — Aperçu live des durées sur le formulaire profil/dispo.
- E13.6 — Disponibilité ≠ entraînement : cap de fréquence + plancher de repos.

**Exclus (autres EPICs / suites)** :
- Mobilité, renforcement, entraînements externes / salle de sport.
- Plafonds de progression hebdo par discipline (→ garde-fous santé/performance).
- Justification de durée par séance sur `/today` / `/plan` (→ E14 bulles explicatives).

## Décisions d'architecture

### E13.1 — Durées réalistes (hybride)

On conserve le modèle Banister (E4) pour la **périodisation du volume hebdo et l'intensité**,
mais on sécurise les sorties de façon déterministe :

1. **Correction du volume hebdo** (`planner.py:572`) : remplacer `weekly_tss = ctl × 7` par
   un calcul cohérent avec le nombre de jours d'entraînement réels et `hours_per_week`,
   afin de ne plus diluer le volume sur 7 jours quand l'athlète s'entraîne sur moins.
2. **Recalage `_TSS_PER_HOUR`** (`planner.py:159-178`) : abaisser les valeurs endurance
   (un Z2 amateur réel est < 45 TSS/h) pour ne plus raccourcir mécaniquement les séances.
3. **Filet de sécurité déterministe** : nouvelle table de bornes
   `[discipline][type][phase]` (plancher/plafond en minutes). La durée finale calculée par
   le planner est **clampée** à ces bornes avant persistance. La validation post-LLM
   (`workout_schema.py`) reçoit en plus un **plancher de durée absolu** par type.

**Table de bornes (valeurs de référence coach, ajustables, en minutes totales)** :

| Discipline | Type | Base | Build | Peak |
|---|---|---|---|---|
| Natation | récup/technique | 30–40 | 30–40 | 25–35 |
| Natation | endurance | 45–60 | 50–70 | 40–55 |
| Natation | seuil/CSS | 45–60 | 50–70 | 45–60 |
| Natation | intervalles/VO2 | 45–60 | 50–65 | 40–55 |
| Natation | longue | 60–75 | 70–90 | 50–60 |
| Vélo | récup | 30–45 | 30–45 | 30–40 |
| Vélo | endurance | 90–180 | 90–150 | 60–105 |
| Vélo | tempo/seuil | 60–90 | 75–120 | 60–75 |
| Vélo | intervalles/VO2 | 60–75 | 60–90 | 50–70 |
| Vélo | longue | 120–210 | 150–240 | 90–150 |
| Course | récup | 30–40 | 30–45 | 25–35 |
| Course | endurance | 40–60 | 45–70 | 35–50 |
| Course | tempo/seuil | 40–55 | 50–65 | 40–50 |
| Course | intervalles/VO2 | 45–60 | 50–65 | 40–55 |
| Course | longue | 60–90 | 75–105 | 50–70 |

**Structure échauffement / corps / retour au calme** (`workout_schema.py`) : remplacer le
ratio fixe (corps ≥ 55 %) par des **plafonds absolus** d'échauffement/RAC + un plancher du
corps principal dépendant du type :

```
warmup_max   = { recup: 5, endurance: 15, tempo: 20, vo2: 25 }   # minutes
cooldown_max = { recup: 5, endurance: 10, tempo: 15, vo2: 15 }   # minutes
main_min_ratio = { recup: 0.90, endurance: 0.80, tempo: 0.60, vo2: 0.50 }
```

Règle clé : l'échauffement ne croît pas linéairement avec la durée. Une endurance de 2 h a
le même plafond d'échauffement (~15 min) qu'une endurance de 1 h.

### E13.2 — Niveau par discipline (volume + intensité/types)

Le niveau `sports_strengths` (1-5) agit sur deux axes dans `planner.py` :

- **Volume — modulation continue** (`distribute_weekly_tss_by_sport`, `planner.py:33-55`) :
  remplacer les 3 paliers par une modulation continue sur l'échelle 1-5 (facteur décroissant
  ~1.25 pour niveau 1 → ~0.85 pour niveau 5). Le niveau oriente aussi le **choix dans la
  fourchette de durée** d'E13.1 : sport faible → bas de fourchette (plus court, plus
  fréquent), sport fort → haut de fourchette.
- **Intensité / types de séance** (`pick_session_types_for_phase`, `planner.py:58-67`) : le
  niveau **filtre les types accessibles** par discipline :
  - niveau 1-2 : endurance, technique, tempo léger. Pas d'intervalles seuil/VO2 durs.
  - niveau 3 : ajoute tempo/seuil modéré.
  - niveau 4-5 : débloque intervalles seuil et VO2.

Le niveau reste passé au prompt LLM (`openai_client.py:67`), avec une consigne renforcée
pour que l'intensité prescrite respecte le palier.

### E13.4 — Repos = repos (UI)

Sur un jour de repos :
- `/today` n'affiche **aucun bloc orienté séance** : pas de compte rendu, pas de structure,
  pas d'ajustement « allège/déplace ta séance ».
- À la place, un message de **récupération** sobre. Les métriques de récup (HRV, sommeil,
  Body Battery) restent visibles car pertinentes un jour de repos.
- Côté worker, `briefing.py` court-circuite les blocs `coach_recommendation` /
  `last_session_feedback` / `next_session_adjustment` quand la séance du jour est `rest` et
  renvoie un payload « repos » dédié, pour que l'UI n'ait pas à filtrer après coup.

### E13.5 — Aperçu live des durées (formulaire profil/dispo)

Sur `app/(app)/profile/_components/dispo-edit-form.tsx` et son équivalent onboarding
`app/(app)/onboarding/_components/step-dispo-form.tsx`, un encart se met à jour en live
quand l'utilisateur règle `hours_per_week`, `available_days` et le niveau par sport :

> **Aperçu de tes séances types**
> Avec 8 h/sem sur 4 jours (vélo 4/5, course 2/5, natation 2/5) :
> - 🚴 Vélo endurance ~1h45–2h15 · seuil ~1h
> - 🏃 Course endurance ~45–55 min (intensité limitée à ton niveau)
> - 🏊 Natation ~45 min, axée technique/fréquence
> Tu te déclares dispo 7 jours, mais je programme 5 séances + 2 jours de repos.

**Architecture** : logique partagée **côté front** dans un module TS pur
`lib/coach/duration-preview.ts`, miroir de la table et des règles de modulation du worker.
Calcul instantané, sans appel réseau. La table est documentée comme « miroir du worker » et
un test compare les fourchettes clés pour détecter une divergence. L'aperçu est indicatif et
pédagogique, pas la vérité contractuelle.

### E13.6 — Disponibilité ≠ entraînement

`available_days` devient un **masque de fenêtres possibles**, plus une cible. Le planner
choisit un sous-ensemble.

**Conversion (en amont de la répartition des séances dans `planner.py`)** :

```
jours_effectifs = min(
    N,                            # jours déclarés dispo (jamais dépassés)
    cap_volume(H),                # H<5h→4, 5-7h→5, 7-9h→6, >=9h→6
    cap_niveau,                   # débutant→4, intermédiaire→5, avancé→6
    7 - repos_min(niveau, phase)  # garantit le plancher de repos
)
jours_repos = 7 - jours_effectifs
```

**Planchers durs** :
- ≥ 1 jour OFF complet par semaine, non négociable (2-3 pour débutant, taper, et semaine de
  récupération du cycle 3:1).
- Volume excédentaire logé en **séances doubles**, pas en jours supplémentaires.

**Cap par discipline (course surtout)** : le compte de jours est décomposé par discipline
avec un cap course distinct (débutant 2-3, inter 3-4, avancé 4-5), **jamais 2 jours course
consécutifs**. Le surplus va sur vélo/natation (faible impact).

**Placement des repos** : OFF après la séance la plus dure et/ou la veille de la sortie
longue ; jamais 2 jours durs consécutifs ; max 2-3 séances qualité par semaine.

**Dérivation du niveau global** : le niveau « débutant / intermédiaire / avancé » utilisé
par les caps dérive de `sports_strengths` 1-5 (ex. moyenne des trois disciplines pour les
caps globaux ; niveau par discipline pour le cap course). À préciser dans le plan.

## Composants modifiés

| Composant | Fichier | Changement |
|---|---|---|
| Volume hebdo | `worker/.../coach/planner.py:572` | Corriger `weekly_tss = ctl × 7` |
| Table TSS/h | `worker/.../coach/planner.py:159-178` | Recaler valeurs endurance |
| Bornes durée | `worker/.../coach/planner.py` | Nouvelle table + clamp avant persistance |
| Conversion dispo→entraînement | `worker/.../coach/planner.py` | Cap fréquence + plancher repos + cap course |
| Modulation volume | `worker/.../coach/planner.py:33-55` | Continue 1-5 (vs 3 paliers) |
| Filtrage types par niveau | `worker/.../coach/planner.py:58-67` | Gate intensité selon niveau |
| Validation séance | `worker/.../coach/workout_schema.py` | Plancher durée absolu + plafonds W/C + plancher corps |
| Prompt LLM | `worker/.../coach/openai_client.py` | Consigne intensité selon palier |
| Briefing repos | `worker/.../coach/briefing.py` | Payload « repos » dédié |
| Aperçu durées | `lib/coach/duration-preview.ts` (nouveau) | Module TS pur miroir du worker |
| Formulaire dispo | `app/(app)/profile/_components/dispo-edit-form.tsx` | Encart aperçu live |
| Onboarding dispo | `app/(app)/onboarding/_components/step-dispo-form.tsx` | Encart aperçu live |
| Page du jour | `app/(app)/today/page.tsx` | Repos = message récup, pas de bloc séance |

## Tests et non-régression

**Worker (pytest)** :
- Conversion dispo→entraînement : N=7/H=8/inter/build → 5 jours + 2 repos ;
  débutant N=7/H=4/base → 4 jours + 3 repos ; plancher ≥ 1 OFF garanti ; cap course (jamais
  2 jours course consécutifs) ; placement repos.
- Durées clampées aux bornes : le cas régressif « vélo endurance 45 min » sort ≥ 1h30 en
  base ; correction `weekly_tss` ; recalage `_TSS_PER_HOUR`.
- Modulation niveau continue (1-5) sur le volume + filtrage des types par niveau
  (swim 1/5 → pas d'intervalles seuil).
- `workout_schema` : plancher de durée absolu par type, plafonds échauffement/RAC, plancher
  corps principal par type.
- `briefing` : un jour de repos ne renvoie pas les blocs orientés séance mais un payload
  « repos ».

**Frontend (vitest)** :
- `lib/coach/duration-preview.ts` : cas clés + test « miroir » alignant les fourchettes avec
  la table worker.
- `/today` : rendu repos = message récup, pas de bloc séance.

**Qualité** : coverage SonarQube maintenu (97 %, gate enforced). Les nouvelles fonctions de
planner sont pures → faciles à couvrir.

## Critères d'acceptation

- Aucune séance endurance/longue générée en deçà du plancher de durée de sa phase.
- L'échauffement/RAC ne représentent plus une part excessive d'une séance courte.
- Le niveau par discipline modifie volume **et** intensité/types de séance de façon visible.
- Un athlète déclarant 7 jours dispo reçoit un nombre de séances capé + ≥ 1 jour de repos.
- Jamais 2 jours de course consécutifs.
- Un jour de repos n'affiche aucun compte rendu/structure de séance, seulement de la récup.
- Le formulaire dispo affiche un aperçu live des durées et du nombre réel de séances/repos.
```
