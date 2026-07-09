# Séances ciblées (sprint / PMA / seuil / endurance qualitative) — vélo, course, natation

**Date** : 2026-07-09
**Statut** : spec validé (brainstorming)
**Priorité** : P1
**EPIC** : Coaching (E5 — génération séances LLM)

## Contexte & besoin

Aujourd'hui, `session_type` couvre `recovery`, `endurance`, `long`, `threshold`, `intervals`.
Les séances à haute intensité (sprint force explosive, PMA plafond physiologique) tombent
toutes sous le générique `"intervals"` — le LLM doit deviner laquelle produire, sans pilotage
explicite du planificateur. Résultat : pas de garantie de progression structurée sur un
domaine précis (vitesse de pointe vs plafond aérobie vs seuil), et une séance très explosive
type sprint (beaucoup de récupération, peu de travail réel) casse l'enveloppe de validation
actuelle (`main_min_ratio` ≥ 50% pour `"intervals"`).

Origine : demande owner d'ajouter des séances structurées comparables à un exemple externe
(coach app tierce, 4 séances vélo <1h : sprints 10×10s, seuil 3×8min, PMA 5×1min30, endurance
qualitative avec relances de cadence), étendu à course et natation — "pas juste faire du
volume".

## Ce qui existe déjà (vérifié dans le code)

- `sports.py` : vélo/course/natation traités de façon symétrique.
- `workout_schema.py` : `IntervalSet` (reps + work + rest) supporte déjà les structures
  d'intervalles courtes pour les 3 disciplines.
- `athlete_profiles` : `ftp_watts` (vélo) et `vma_kmh` (course) déjà injectés dans le prompt
  LLM (`openai_client.py:_athlete_lines`) — **aucun équivalent pour la natation**.
- Pas de champ cadence dans `IntervalTarget`.
- `planner.py:pick_session_types_for_phase` : base=[endurance,long,recovery],
  build=[endurance,threshold,long], peak=[intervals,endurance,long], taper=[endurance,recovery].
- `duration_bounds.py` : bornes réalistes par (sport, type, phase), déjà couvrant `threshold`
  pour vélo en peak (50-75min, compatible avec l'exemple ~50min).

## Périmètre de cette itération

1. Deux nouveaux `session_type` pilotés par le planificateur : **`sprint`** et **`pma`**.
2. Champ cadence structurel (`cadence_low`/`cadence_high`) dans le schéma de workout.
3. Repère physiologique de référence natation (**CSS**, Critical Swim Speed) au même
   niveau que FTP/VMA.
4. Léger ajustement du prompt `threshold` pour coller plus précisément à l'exemple
   (2-4 sets de 6-10min au lieu de 1-2 sets ≥8min).
5. `"intervals"` (générique) reste dans le schéma/caps pour compatibilité (séances déjà en
   DB, tests existants) mais **n'est plus émis par le planificateur** une fois `sprint`/`pma`
   en place.

Hors scope : validation numérique de la cadence (pas de bornes physiologiques dures — champ
informatif), dérivation automatique du CSS depuis l'historique d'activités (saisie manuelle
comme FTP/VMA aujourd'hui), refonte du type `"long"` ou `"recovery"`.

## Modèle de données

### `athlete_profiles`

Nouvelle colonne `css_per_100m_s` (integer, nullable) — Critical Swim Speed en
secondes/100m, saisie manuelle (profil + onboarding), même pattern que `ftp_watts`/`vma_kmh`.
Migration Supabase avec la colonne nullable, pas de backfill.

### `IntervalTarget` (workout_schema.py + workout-types.ts, mirroir strict)

```python
class IntervalTarget(BaseModel):
    label: Zone
    rpe: Rpe
    bpm_low: int | None = None
    bpm_high: int | None = None
    watts_low: int | None = None
    watts_high: int | None = None
    pace_low_kmh: float | None = None
    pace_high_kmh: float | None = None
    cadence_low: int | None = None   # nouveau
    cadence_high: int | None = None  # nouveau
```

Interprétation contextuelle par sport (documentée en commentaire, jamais validée
numériquement) : rpm en vélo, foulées/min en course, coups de bras/min en natation.
`validate_workout_for_session` ne vérifie pas ces valeurs — champ informatif transmis
tel quel à la montre / au texte de la séance.

### `session_type`

Ajout de `"sprint"` et `"pma"` partout où `session_type` est une union de littéraux
(`planner.py`, `workout_schema.py`, `workout-types.ts`, éventuellement des types Zod/TS
côté frontend consommant ce champ — à vérifier lors du plan d'implémentation).

## Périodisation (planner.py)

| Phase | Types (avant) | Types (après) |
|---|---|---|
| base | endurance, long, recovery | *(inchangé)* |
| build | endurance, threshold, long | endurance, threshold, **pma**, long *(pma en 2e moitié de build)* |
| peak | intervals, endurance, long | **pma**, **sprint**, endurance, long |
| taper | endurance, recovery | endurance, recovery, **sprint** *(léger, faible volume)* |

- `_HARD_TYPES_BY_LEVEL` : `pma` requiert niveau 4-5 (aussi exigeant que l'actuel
  `"intervals"`) ; `sprint` accessible dès niveau 3 (technique/explosivité, faible volume,
  moins traumatisant qu'un seuil long).
- `threshold` : prompt ajusté (`2-4 sets de 6-10min, récup 2-5min` au lieu de
  `1-2 sets ≥8min, 2-3min`) ; bornes de durée vélo déjà compatibles (peak 50-75min).
- Nouvelles entrées à ajouter : `_TSS_PER_HOUR[(sport, "sprint"/"pma")]`,
  `_SESSION_TYPE_WEIGHT["sprint"/"pma"]`, `_ELEVATION_SESSION_WEIGHT["sprint"/"pma"] = 0.0`
  (comme `intervals` — pas de dénivelé dédié sur des répétitions courtes),
  `duration_bounds.py` pour `(sport, "sprint"/"pma", phase)` avec des bornes courtes
  réalistes (~30-50min sprint, ~35-60min pma, cohérent avec les bornes `intervals`
  existantes par sport/phase).

## Génération LLM (workout_schema.py + openai_client.py)

### Nouvelles `StructureCaps`

- `"sprint"` : `main_min_ratio` bas (~25-30%) — une séance sprint est dominée par la
  récupération (10×10s/90s ≈ 37% de travail réel dans l'exemple), fondamentalement
  différente des autres types où le corps de séance domine. Floor court (~25-30min),
  warmup proportionnellement plus long (montée en température progressive avant du 100%
  à froid).
- `"pma"` : `main_min_ratio` intermédiaire (~40%), floor ~35-40min, proche de l'actuel
  `"intervals"` (0.50/40min) mais légèrement assoupli.

### Prompt système (`_SYSTEM_PROMPT`)

Nouvelles règles :
- `"sprint"` : répétitions très courtes (5-15s) à intensité maximale (Z5), récupération
  large (6-10× le temps de travail).
- `"pma"` : répétitions 1-3min à 110-130% seuil (Z4-Z5), récupération égale au temps
  de travail.

### Prompt athlète (`_athlete_lines`)

Ajoute `- CSS : {css} s/100m` quand `sport == "swim"` et `athlete.css_per_100m_s` est
renseigné (miroir du pattern FTP/VMA existant).

## Tests

- `test_workout_schema.py` : enveloppe `sprint`/`pma` satisfiable par une structure
  proche de l'exemple (10×10s/90s sur ~45min pour sprint) — le cas qui casse
  actuellement avec `main_min_ratio` à 50%.
- `test_openai_client.py` : prompt contient la ligne CSS pour swim, les règles
  sprint/pma dans le system prompt.
- `test_planner.py` / tests duration_bounds : nouveaux types présents dans les bonnes
  phases/niveaux, absents en base, gating niveau respecté.
- Migration Supabase : colonne nullable, testée comme les migrations précédentes du
  projet.

## Risques / points d'attention pour le plan d'implémentation

- Vérifier tous les endroits où `session_type` est une union de littéraux stricte
  (TS et Python) pour ne rien oublier — un type manqué casserait le typecheck plutôt
  que de fail silencieusement, ce qui est le comportement souhaité.
- Les séances déjà planifiées en DB avec `session_type = "intervals"` restent valides
  (schéma/caps conservés) — pas de migration de données nécessaire.
- Le retrait d'`"intervals"` de l'émission du planificateur change la distribution des
  types en phase `peak` pour les plans **déjà générés avant ce changement** : sans
  action, ils gardent leurs séances `"intervals"` existantes (pas de régénération
  automatique) ; les futurs `generate_plan()` émettront `sprint`/`pma` à la place.
