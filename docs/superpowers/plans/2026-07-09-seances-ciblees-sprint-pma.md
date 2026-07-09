# Séances ciblées (sprint / PMA / seuil / endurance qualitative) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter deux nouveaux types de séance pilotés par le planificateur (`sprint`, `pma`), un champ cadence structurel, et un repère physiologique de référence natation (CSS), pour que le moteur de coaching produise des séances ciblées (vitesse de pointe, plafond aérobie) pour vélo, course ET natation — pas seulement du volume générique.

**Architecture:** Le worker Python (`worker/src/garmin_sync/coach/`) pilote la génération : `planner.py` décide du `session_type` par jour selon la phase Banister et le niveau athlète, `duration_bounds.py` borne la durée réaliste, `workout_schema.py` définit l'enveloppe de validation numérique du workout généré, `openai_client.py` construit le prompt LLM et valide la réponse. Le frontend (`lib/`, `app/`) reflète le schéma (`workout-types.ts`) et expose la saisie du nouveau champ profil CSS (onboarding + édition profil).

**Tech Stack:** Python 3.12, Pydantic v2, pytest (worker) ; TypeScript, Next.js App Router, Zod, Vitest + Testing Library (frontend) ; Supabase Postgres (migration SQL).

## Global Constraints

- Répertoire de travail worker : `worker/` — toutes les commandes `uv run ...` se lancent depuis `worker/`.
- Quality gates avant chaque commit worker : `uv run ruff format . && uv run ruff check . && uv run mypy src/`.
- Quality gates avant chaque commit frontend : `pnpm lint && pnpm typecheck` (build complet en fin de plan, pas à chaque tâche).
- Conventional Commits stricts (`feat:`, `fix:`, `test:`, `docs:`), body lines ≤ 100 chars.
- Ne PAS modifier la signature publique de `validate_workout_for_session` / `describe_session_envelope` / `envelope_for_session` — seules les tables de données (`_CAPS_BY_TYPE`, `_BOUNDS_MIN`, etc.) changent.
- `lib/coach/workout-types.ts` DOIT rester le miroir exact de `worker/src/garmin_sync/coach/workout_schema.py::IntervalTarget` (commentaire déjà présent en tête du fichier Python).
- Spec de référence : `docs/superpowers/specs/2026-07-09-seances-ciblees-sprint-pma-design.md`.

---

## Task 1: Migration — colonne `css_per_100m_s`

**Files:**
- Create: `supabase/migrations/20260709000000_athlete_profiles_css.sql`

**Interfaces:**
- Produces: colonne `athlete_profiles.css_per_100m_s` (integer, nullable), consommée par les tâches 5 (backend prompt), 8-10 (frontend).

- [ ] **Step 1: Écrire la migration**

```sql
-- 20260709000000_athlete_profiles_css.sql
-- Ajoute le repère physiologique de référence natation (Critical Swim Speed,
-- en secondes/100m), au même niveau que ftp_watts (vélo) / vma_kmh (course).
-- Pattern identique à la colonne d'origine (20260517000000_initial_schema.sql) :
-- nullable, saisie manuelle, contrainte CHECK bornant les valeurs réalistes.

alter table public.athlete_profiles
  add column css_per_100m_s integer
    check (css_per_100m_s is null or css_per_100m_s between 40 and 300);
```

- [ ] **Step 2: Vérifier visuellement la cohérence avec la migration d'origine**

Ouvrir `supabase/migrations/20260517000000_initial_schema.sql` et confirmer que le pattern
(`integer check (col is null or col between X and Y)`) est identique à celui de `ftp_watts`.
Pas de test automatisé pour les migrations SQL dans ce projet — elles sont auto-appliquées en
CI sur `main` par `.github/workflows/supabase-migrations.yml` (E17). Pas de commit séparé :
cette migration est commitée avec la Task 5 (Step 6) qui l'utilise pour de vrai côté backend,
OU seule maintenant si tu préfères des commits atomiques — dans ce cas :

```bash
git add supabase/migrations/20260709000000_athlete_profiles_css.sql
git commit -m "feat(db): add athlete_profiles.css_per_100m_s (Critical Swim Speed)"
```

---

## Task 2: `workout_schema.py` — champ cadence structurel

**Files:**
- Modify: `worker/src/garmin_sync/coach/workout_schema.py:18-28` (classe `IntervalTarget`)
- Test: `worker/tests/coach/test_workout_schema.py`

**Interfaces:**
- Consumes: rien de nouveau (classe existante étendue).
- Produces: `IntervalTarget.cadence_low: int | None`, `IntervalTarget.cadence_high: int | None`
  — consommés par la Task 7 (miroir TS) et potentiellement lus/affichés côté frontend (hors
  scope de ce plan, champ juste transporté).

- [ ] **Step 1: Écrire le test qui échoue**

Dans `worker/tests/coach/test_workout_schema.py`, ajouter après `test_target_with_bpm_range` :

```python
def test_target_with_cadence_range():
    t = IntervalTarget(label="Z2", rpe=5, cadence_low=100, cadence_high=110)
    assert t.cadence_low == 100
    assert t.cadence_high == 110


def test_target_cadence_defaults_to_none():
    t = IntervalTarget(label="Z2", rpe=5)
    assert t.cadence_low is None
    assert t.cadence_high is None
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

```bash
cd worker && uv run pytest tests/coach/test_workout_schema.py::test_target_with_cadence_range -v
```
Attendu : FAIL avec `TypeError: IntervalTarget() got unexpected keyword argument 'cadence_low'`.

- [ ] **Step 3: Ajouter les champs au modèle**

Dans `worker/src/garmin_sync/coach/workout_schema.py`, modifier `IntervalTarget` :

```python
class IntervalTarget(BaseModel):
    """Physiological target for an interval block."""

    label: Zone
    rpe: Rpe
    bpm_low: int | None = None
    bpm_high: int | None = None
    watts_low: int | None = None
    watts_high: int | None = None
    pace_low_kmh: float | None = None
    pace_high_kmh: float | None = None
    # Cadence : interprétation dépendante du sport, jamais validée numériquement
    # (pas de bornes physiologiques universelles) — rpm en vélo, foulées/min en
    # course, coups de bras/min en natation. Champ informatif transmis tel quel.
    cadence_low: int | None = None
    cadence_high: int | None = None
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

```bash
cd worker && uv run pytest tests/coach/test_workout_schema.py -v
```
Attendu : PASS pour tous les tests du fichier (aucune régression).

- [ ] **Step 5: Commit**

```bash
git add worker/src/garmin_sync/coach/workout_schema.py worker/tests/coach/test_workout_schema.py
git commit -m "feat(coach): add optional cadence fields to IntervalTarget"
```

---

## Task 3: `workout_schema.py` — `StructureCaps` pour `sprint` et `pma`

**Files:**
- Modify: `worker/src/garmin_sync/coach/workout_schema.py:88-95` (`_CAPS_BY_TYPE`)
- Test: `worker/tests/coach/test_workout_schema.py`

**Interfaces:**
- Consumes: `StructureCaps`, `envelope_for_session`, `validate_workout_for_session` (existants,
  inchangés dans leur logique — seules les données ajoutées).
- Produces: `structure_caps_for_type("sprint")` et `structure_caps_for_type("pma")` retournent
  des `StructureCaps` valides, consommés par `describe_session_envelope`/`validate_workout_for_session`
  (Task 5, prompt LLM) et par le planner (Task 6, via `session_type`).

**Contexte numérique (vérifié par calcul manuel de `envelope_for_session`, à ne pas re-dériver)** :

Pour une séance `sprint` cible 2700s (45min, cas de l'exemple original 10×10s/90s récup) :
`tol=300`, `min_total=max(1500,2400)=2400`, `budget=int(0.70*2400)=1680`,
`warmup_max=min(900,1008)=900`, `cooldown_max=min(600,780)=600`. Un workout avec main=1000s
(10 reps × (10s work + 90s rest)), warmup≈850s, cooldown=600s → total=2450s, dans la fenêtre
`[2400,3000]`, ratio main/total=40.8% ≥ 25% → **satisfiable**.

Pour une séance `pma` cible 2700s (5×1min30 work/rest = 900s main) : avec `main_min_ratio=0.35`,
`budget=int(0.65*2400)=1560`, `warmup_max=min(1200,936)=936`, `cooldown_max=min(900,624)=624`,
total achievable jusqu'à 900+1560=2460s, dans `[2400,3000]`, ratio=900/2460=36.6% ≥ 35% →
**satisfiable**.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `worker/tests/coach/test_workout_schema.py`, ajouter :

```python
def test_structure_caps_pma():
    caps = structure_caps_for_type("pma")
    assert caps.warmup_max_s == 20 * 60
    assert caps.cooldown_max_s == 15 * 60
    assert caps.main_min_ratio == 0.35
    assert caps.floor_s == 30 * 60


def test_structure_caps_sprint():
    caps = structure_caps_for_type("sprint")
    assert caps.warmup_max_s == 15 * 60
    assert caps.cooldown_max_s == 10 * 60
    assert caps.main_min_ratio == 0.25
    assert caps.floor_s == 25 * 60


def test_sprint_example_workout_passes_validation():
    """Régression : la séance sprint 10x10s/90s (exemple qui a motivé cette feature)
    doit être satisfiable par l'enveloppe de validation pour une cible ~45min."""
    session = {"session_type": "sprint", "target_duration_s": 2700}
    z5 = IntervalTarget(label="Z5", rpe=10)
    z1 = IntervalTarget(label="Z1", rpe=2)
    work = IntervalBlock(duration_s=10, target=z5)
    rest = IntervalBlock(duration_s=90, target=z1)
    sprint_set = IntervalSet(reps=10, work=work, rest=rest)
    workout = Workout(
        warmup=IntervalBlock(duration_s=850, target=z1),
        main=[sprint_set],
        cooldown=IntervalBlock(duration_s=600, target=z1),
        summary_md="10x10s à fond",
    )
    assert validate_workout_for_session(workout, session) is workout


def test_pma_example_workout_passes_validation():
    """Régression : la séance PMA 5x1min30 (exemple qui a motivé cette feature)
    doit être satisfiable par l'enveloppe de validation pour une cible ~45min."""
    session = {"session_type": "pma", "target_duration_s": 2700}
    z4 = IntervalTarget(label="Z4", rpe=9)
    z1 = IntervalTarget(label="Z1", rpe=2)
    work = IntervalBlock(duration_s=90, target=z4)
    rest = IntervalBlock(duration_s=90, target=z1)
    pma_set = IntervalSet(reps=5, work=work, rest=rest)
    workout = Workout(
        warmup=IntervalBlock(duration_s=930, target=z1),
        main=[pma_set],
        cooldown=IntervalBlock(duration_s=620, target=z1),
        summary_md="5x1min30 PMA",
    )
    assert validate_workout_for_session(workout, session) is workout
```

Étendre aussi le test paramétré existant `test_workout_following_announced_caps_passes_validation`
en ajoutant `("pma", 2700)` et `("sprint", 2700)` à la liste de paramètres (ligne ~201-211) :

```python
@pytest.mark.parametrize(
    ("session_type", "target_s"),
    [
        ("recovery", 2400),
        ("endurance", 3600),
        ("endurance", 2700),
        ("long", 7200),
        ("threshold", 3600),
        ("intervals", 3600),
        ("pma", 2700),
        ("sprint", 2700),
        ("unknown", 3000),
    ],
)
def test_workout_following_announced_caps_passes_validation(session_type, target_s):
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

```bash
cd worker && uv run pytest tests/coach/test_workout_schema.py -v -k "sprint or pma"
```
Attendu : FAIL — `structure_caps_for_type("sprint")` retourne actuellement `_DEFAULT_CAPS`
(0.55 ratio), pas les valeurs attendues.

- [ ] **Step 3: Ajouter les entrées à `_CAPS_BY_TYPE`**

Dans `worker/src/garmin_sync/coach/workout_schema.py`, modifier `_CAPS_BY_TYPE` :

```python
_CAPS_BY_TYPE: dict[str, StructureCaps] = {
    "recovery": StructureCaps(5 * 60, 5 * 60, 0.80, 20 * 60),
    "endurance": StructureCaps(15 * 60, 10 * 60, 0.75, 30 * 60),
    "long": StructureCaps(15 * 60, 10 * 60, 0.80, 50 * 60),
    "threshold": StructureCaps(20 * 60, 15 * 60, 0.60, 40 * 60),
    "intervals": StructureCaps(25 * 60, 15 * 60, 0.50, 40 * 60),
    "pma": StructureCaps(20 * 60, 15 * 60, 0.35, 30 * 60),
    "sprint": StructureCaps(15 * 60, 10 * 60, 0.25, 25 * 60),
}
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

```bash
cd worker && uv run pytest tests/coach/test_workout_schema.py -v
```
Attendu : PASS pour tous les tests du fichier.

- [ ] **Step 5: Commit**

```bash
git add worker/src/garmin_sync/coach/workout_schema.py worker/tests/coach/test_workout_schema.py
git commit -m "feat(coach): add sprint/pma structure caps to workout envelope"
```

---

## Task 4: `duration_bounds.py` — bornes réalistes sprint/pma

**Files:**
- Modify: `worker/src/garmin_sync/coach/duration_bounds.py:12-61` (`_BOUNDS_MIN`)
- Test: `worker/tests/coach/test_duration_bounds.py`

**Interfaces:**
- Consumes: `clamp_duration_to_bounds`, `duration_bounds_s` (existants, inchangés).
- Produces: bornes pour `(sport, "sprint", "peak")` et `(sport, "pma", "build"|"peak")`,
  pour `sport` ∈ `{swim, bike, run}` — consommées par `planner.py::_training_day_session`
  (Task 6).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `worker/tests/coach/test_duration_bounds.py`, ajouter :

```python
def test_bike_sprint_peak_bounds():
    assert duration_bounds_s("bike", "sprint", "peak") == (35 * 60, 45 * 60)


def test_bike_pma_build_bounds():
    assert duration_bounds_s("bike", "pma", "build") == (45 * 60, 65 * 60)


def test_bike_pma_peak_bounds():
    assert duration_bounds_s("bike", "pma", "peak") == (40 * 60, 60 * 60)


def test_run_sprint_peak_bounds():
    assert duration_bounds_s("run", "sprint", "peak") == (25 * 60, 35 * 60)


def test_run_pma_build_bounds():
    assert duration_bounds_s("run", "pma", "build") == (40 * 60, 55 * 60)


def test_swim_sprint_peak_bounds():
    assert duration_bounds_s("swim", "sprint", "peak") == (30 * 60, 40 * 60)


def test_swim_pma_build_bounds():
    assert duration_bounds_s("swim", "pma", "build") == (40 * 60, 55 * 60)


def test_sprint_taper_uses_peak_bounds():
    assert duration_bounds_s("bike", "sprint", "taper") == duration_bounds_s(
        "bike", "sprint", "peak"
    )


def test_clamp_caps_overlong_bike_sprint():
    assert clamp_duration_to_bounds("bike", "sprint", "peak", 90 * 60) == 45 * 60
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

```bash
cd worker && uv run pytest tests/coach/test_duration_bounds.py -v -k "sprint or pma"
```
Attendu : FAIL — `duration_bounds_s` retourne `None` pour ces combos absents de `_BOUNDS_MIN`.

- [ ] **Step 3: Ajouter les entrées à `_BOUNDS_MIN`**

Dans `worker/src/garmin_sync/coach/duration_bounds.py`, ajouter à `_BOUNDS_MIN` (respecter le
regroupement existant par discipline) :

```python
    # natation
    ("swim", "pma", "build"): (40, 55),
    ("swim", "pma", "peak"): (35, 50),
    ("swim", "sprint", "peak"): (30, 40),
    # vélo
    ("bike", "pma", "build"): (45, 65),
    ("bike", "pma", "peak"): (40, 60),
    ("bike", "sprint", "peak"): (35, 45),
    # course
    ("run", "pma", "build"): (40, 55),
    ("run", "pma", "peak"): (35, 50),
    ("run", "sprint", "peak"): (25, 35),
```

Insérer chaque paire dans le bloc correspondant à sa discipline (après les entrées `long` de
chaque bloc, avant le commentaire de la discipline suivante).

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

```bash
cd worker && uv run pytest tests/coach/test_duration_bounds.py -v
```
Attendu : PASS pour tous les tests du fichier.

- [ ] **Step 5: Commit**

```bash
git add worker/src/garmin_sync/coach/duration_bounds.py worker/tests/coach/test_duration_bounds.py
git commit -m "feat(coach): add sprint/pma duration bounds per sport/phase"
```

---

## Task 5: `openai_client.py` — prompt sprint/PMA/seuil + repère CSS natation

**Files:**
- Modify: `worker/src/garmin_sync/coach/openai_client.py:31-52` (`_SYSTEM_PROMPT`)
- Modify: `worker/src/garmin_sync/coach/openai_client.py:64-89` (`_athlete_lines`)
- Modify: `worker/src/garmin_sync/coach/sessions.py:53-59` (`_load_profile_and_race`)
- Test: `worker/tests/coach/test_openai_client.py`

**Interfaces:**
- Consumes: `athlete: dict[str, Any]` avec clé optionnelle `"css_per_100m_s"` (Task 1, colonne
  DB — mais ce dict est déjà passé en paramètre, aucune signature ne change).
- Produces: prompt système mentionnant `sprint`/`pma`/`threshold` reformulé ; ligne CSS dans le
  prompt utilisateur pour `sport == "swim"`.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `worker/tests/coach/test_openai_client.py`, ajouter :

```python
def test_athlete_lines_includes_css_for_swim_when_known():
    lines = _athlete_lines(athlete={"css_per_100m_s": 95}, sport="swim")
    text = "\n".join(lines)
    assert "CSS" in text
    assert "95" in text


def test_athlete_lines_css_unknown_for_swim():
    lines = _athlete_lines(athlete={}, sport="swim")
    text = "\n".join(lines)
    assert "CSS : non connue" in text


def test_athlete_lines_no_css_line_for_bike():
    lines = _athlete_lines(athlete={"css_per_100m_s": 95}, sport="bike")
    text = "\n".join(lines)
    assert "CSS" not in text
```

Ajouter aussi (proche de `test_prompt_includes_race_context`, réutilise `_get_client`/`_session`
mockés existants) :

```python
@patch("garmin_sync.coach.openai_client._get_client")
def test_system_prompt_documents_sprint_and_pma_rules(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.beta.chat.completions.parse.return_value = _resp(_workout_dict(300, 3000, 300))
    generate_workout_for_session(
        session=_endurance_session(), athlete=_athlete_full(), race_context=_race_context()
    )
    system_msg = mock_client.beta.chat.completions.parse.call_args.kwargs["messages"][0]["content"]
    assert '"pma"' in system_msg
    assert '"sprint"' in system_msg
    assert "VO2max" in system_msg or "plafond aérobie" in system_msg
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

```bash
cd worker && uv run pytest tests/coach/test_openai_client.py -v -k "css or sprint_and_pma"
```
Attendu : FAIL — pas de ligne CSS, pas de règles `pma`/`sprint` dans le prompt actuel.

- [ ] **Step 3: Mettre à jour `_SYSTEM_PROMPT`**

Dans `worker/src/garmin_sync/coach/openai_client.py`, remplacer `_SYSTEM_PROMPT` par :

```python
_SYSTEM_PROMPT = """Tu es un coach triathlon expert. Tu produis des séances d'entraînement
structurées au format JSON strict suivant le schema fourni. Tu adaptes les cibles physiologiques
au profil de l'athlète. Tu réponds uniquement en JSON valide, sans aucun texte
en dehors du schema.

Règles :
- Ne génère jamais de workout pour une séance "rest".
- La durée totale warmup + main + cooldown doit rester proche de la durée cible.
- Le corps de séance doit respecter la part minimale de la durée totale donnée dans
  les contraintes chiffrées de la demande.
- Échauffement et retour calme sont proportionnels : courts sur récupération/endurance courte,
  plus longs seulement pour seuil/PMA/sprint/intervalles.
- Évite les découpages artificiels type 45min avec 15min échauffement, 18min travail,
  12min retour calme.
- Séance "recovery" : Z1 seulement, durée courte, échauffement intégré ou minimal.
- Séance "endurance" : un bloc principal Z2-Z3 majoritaire.
- Séance "long" : un seul gros bloc continu (pas d'intervalles).
- Séance "intervals" : des sets répétés (work + rest).
- Séance "threshold" : 2-4 sets de 6-10min à intensité seuil (Z4), récupération 2-5min.
- Séance "pma" : répétitions de 1 à 3min à 110-130% du seuil (Z4-Z5), récupération
  égale au temps de travail — vise le plafond aérobie (VO2max).
- Séance "sprint" : répétitions très courtes de 5 à 15s à intensité maximale (Z5),
  récupération large (6 à 10 fois le temps de travail) — vise la force explosive et
  la vitesse de pointe, pas l'endurance.
- summary_md : 1-2 phrases FR conseil du jour, motivant mais bref.
- technical_focus : 1 phrase FR sur l'aspect technique spécifique au sport.
"""
```

- [ ] **Step 4: Ajouter la ligne CSS dans `_athlete_lines`**

Dans `worker/src/garmin_sync/coach/openai_client.py`, modifier `_athlete_lines` :

```python
def _athlete_lines(*, athlete: dict[str, Any], sport: str) -> list[str]:
    sports = athlete.get("sports_strengths") or {}
    swim = sports.get("swim", "?")
    bike = sports.get("bike", "?")
    run = sports.get("run", "?")
    fc = athlete.get("fc_max_bpm")
    ftp = athlete.get("ftp_watts")
    vma = athlete.get("vma_kmh")
    css = athlete.get("css_per_100m_s")

    lines = [
        "Athlète :",
        f"- FC max : {fc} bpm" if fc else "- FC max : non connue",
    ]
    if sport == "bike":
        lines.append(f"- FTP : {ftp} W" if ftp else "- FTP : non connue")
    if sport == "run":
        lines.append(f"- VMA : {vma} km/h" if vma else "- VMA : non connue")
    if sport == "swim":
        lines.append(f"- CSS : {css} s/100m" if css else "- CSS : non connue")
    lines.append(f"- Niveau (1-5) : swim={swim}, bike={bike}, run={run}")
    weak = [s for s in ("swim", "bike", "run") if isinstance(sports.get(s), int) and sports[s] <= 2]
    if weak:
        lines.append(
            "- Consigne intensité : pour les disciplines faibles "
            f"({', '.join(weak)}), privilégie l'endurance et la technique, "
            "limite l'intensité (pas d'intervalles seuil durs)."
        )
    return lines
```

- [ ] **Step 5: Lancer les tests pour vérifier le succès**

```bash
cd worker && uv run pytest tests/coach/test_openai_client.py -v
```
Attendu : PASS pour tous les tests du fichier.

- [ ] **Step 6: Propager `css_per_100m_s` dans la requête profil de `sessions.py`**

Dans `worker/src/garmin_sync/coach/sessions.py`, modifier `_load_profile_and_race` (ligne 55) :

```python
    profile_resp = (
        db.table("athlete_profiles")
        .select("ftp_watts, vma_kmh, fc_max_bpm, css_per_100m_s, sports_strengths")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
```

Pas de nouveau test dédié : `test_sessions.py` ne vérifie pas la chaîne `select(...)` littérale
(vérifié — `grep -n "ftp_watts, vma_kmh" worker/tests/coach/test_sessions.py` ne retourne rien),
donc ce changement ne casse aucun test existant. Vérifier avec la suite complète :

```bash
cd worker && uv run pytest tests/coach/test_sessions.py -v
```
Attendu : PASS (aucune régression).

- [ ] **Step 7: Commit**

```bash
git add worker/src/garmin_sync/coach/openai_client.py worker/src/garmin_sync/coach/sessions.py \
  worker/tests/coach/test_openai_client.py
git commit -m "feat(coach): document sprint/pma in LLM prompt, add swim CSS reference"
```

---

## Task 6: `planner.py` — périodisation sprint/pma par phase et niveau

**Files:**
- Modify: `worker/src/garmin_sync/coach/planner.py:69-95` (`_HARD_TYPES_BY_LEVEL`,
  `pick_session_types_for_phase`)
- Modify: `worker/src/garmin_sync/coach/planner.py:204-279` (`_SESSION_TYPE_WEIGHT`,
  `_TSS_PER_HOUR`, `_ELEVATION_SESSION_WEIGHT`)
- Test: `worker/tests/coach/test_planner.py`

**Interfaces:**
- Consumes: `duration_bounds_s`/`clamp_duration_to_bounds` (Task 4), `structure_caps_for_type`
  (Task 3, consommé indirectement via le workout généré plus tard dans le pipeline, pas dans
  `planner.py` directement).
- Produces: `pick_session_types_for_phase("build"|"peak"|"taper", max_level=N)` inclut
  `"pma"`/`"sprint"` selon le niveau — consommé par `_build_training_day_plan` (déjà générique,
  aucun changement requis là).

**⚠️ Cette tâche modifie le comportement de deux tests existants** (changement de
comportement volontaire et approuvé dans le spec : `"intervals"` n'est plus émis par le
planificateur en phase `peak`, remplacé par `"pma"`/`"sprint"`) :
- `test_pick_session_types_for_peak_phase` (ligne ~110-113)
- `test_advanced_peak_allows_intervals` (ligne ~576-578)

- [ ] **Step 1: Mettre à jour les tests existants qui deviennent incorrects**

Dans `worker/tests/coach/test_planner.py`, remplacer :

```python
def test_pick_session_types_for_peak_phase() -> None:
    types = pick_session_types_for_phase("peak")
    assert "intervals" in types
```

par :

```python
def test_pick_session_types_for_peak_phase() -> None:
    types = pick_session_types_for_phase("peak")
    assert "pma" in types
    assert "sprint" in types
```

Et remplacer :

```python
def test_advanced_peak_allows_intervals() -> None:
    types = pick_session_types_for_phase("peak", max_level=5)
    assert "intervals" in types
```

par :

```python
def test_advanced_peak_allows_pma_and_sprint() -> None:
    types = pick_session_types_for_phase("peak", max_level=5)
    assert "pma" in types
    assert "sprint" in types
```

- [ ] **Step 2: Écrire les nouveaux tests qui échouent**

Dans `worker/tests/coach/test_planner.py`, ajouter :

```python
def test_pick_session_types_for_build_phase_includes_pma_at_high_level() -> None:
    types = pick_session_types_for_phase("build", max_level=5)
    assert "pma" in types
    assert "threshold" in types


def test_build_phase_excludes_pma_at_level3() -> None:
    types = pick_session_types_for_phase("build", max_level=3)
    assert "pma" not in types
    assert "threshold" in types  # threshold reste accessible dès le niveau 3


def test_peak_phase_excludes_sprint_and_pma_for_low_level() -> None:
    types = pick_session_types_for_phase("peak", max_level=2)
    assert "sprint" not in types
    assert "pma" not in types
    assert "endurance" in types


def test_peak_phase_allows_sprint_not_pma_at_level3() -> None:
    types = pick_session_types_for_phase("peak", max_level=3)
    assert "sprint" in types
    assert "pma" not in types


def test_taper_phase_includes_sprint_at_default_level() -> None:
    types = pick_session_types_for_phase("taper")
    assert "sprint" in types
    assert "long" not in types


def test_beginner_build_has_no_hard_intervals() -> None:
    types = pick_session_types_for_phase("build", max_level=1)
    assert "threshold" not in types
    assert "intervals" not in types
    assert "pma" not in types
    assert "endurance" in types


def test_level3_build_allows_threshold_not_intervals() -> None:
    types = pick_session_types_for_phase("build", max_level=3)
    assert "threshold" in types
    assert "intervals" not in types
    assert "pma" not in types
```

(Les deux derniers tests remplacent les tests du même nom déjà présents — mise à jour inline,
pas de doublon : `test_beginner_build_has_no_hard_intervals` gagne l'assertion `pma` en plus,
`test_level3_build_allows_threshold_not_intervals` idem.)

- [ ] **Step 3: Lancer les tests pour vérifier l'échec**

```bash
cd worker && uv run pytest tests/coach/test_planner.py -v -k "pick_session_types or peak_phase or build_phase or taper_phase or beginner_build or level3_build"
```
Attendu : plusieurs FAIL — `"pma"`/`"sprint"` absents des listes actuelles.

- [ ] **Step 4: Mettre à jour `_HARD_TYPES_BY_LEVEL` et `pick_session_types_for_phase`**

Dans `worker/src/garmin_sync/coach/planner.py`, remplacer le bloc lignes 69-95 :

```python
_HARD_TYPES_BY_LEVEL: dict[int, set[str]] = {
    1: set(),
    2: set(),
    3: {"threshold", "sprint"},
    4: {"threshold", "sprint", "pma"},
    5: {"threshold", "sprint", "pma"},
}

# Types dont l'accès dépend du niveau athlète (filtrés par _HARD_TYPES_BY_LEVEL).
# "intervals" reste dans le schéma/caps pour compatibilité (séances déjà en DB) mais
# n'apparaît plus dans aucune liste `base` ci-dessous — gardé ici uniquement pour ne
# jamais le laisser passer si une future liste `base` le réintroduit par erreur.
_FILTERABLE_HARD_TYPES = {"threshold", "intervals", "sprint", "pma"}


def pick_session_types_for_phase(phase: Phase, *, max_level: int = 5) -> list[str]:
    """Return the canonical set of session types for a given phase.

    `max_level` (1-5) borne l'intensité : un niveau faible retire les types durs
    (threshold/pma/sprint) au profit d'endurance/recovery.
    """
    if phase == "base":
        base = ["endurance", "long", "recovery"]
    elif phase == "build":
        base = ["endurance", "threshold", "pma", "long"]
    elif phase == "peak":
        base = ["pma", "sprint", "endurance", "long"]
    else:  # taper
        base = ["endurance", "recovery", "sprint"]

    allowed_hard = _HARD_TYPES_BY_LEVEL.get(max_level, {"threshold", "sprint", "pma"})
    filtered = [t for t in base if t not in _FILTERABLE_HARD_TYPES or t in allowed_hard]
    return filtered or ["endurance"]
```

- [ ] **Step 5: Lancer les tests pour vérifier le succès (partiel)**

```bash
cd worker && uv run pytest tests/coach/test_planner.py -v -k "pick_session_types or peak_phase or build_phase or taper_phase or beginner_build or level3_build"
```
Attendu : PASS pour tous ces tests.

- [ ] **Step 6: Ajouter les entrées manquantes dans les tables de poids/TSS/dénivelé**

Dans `worker/src/garmin_sync/coach/planner.py`, modifier `_SESSION_TYPE_WEIGHT` (ligne ~204-210) :

```python
_SESSION_TYPE_WEIGHT: dict[str, float] = {
    "long": 1.5,
    "threshold": 1.2,
    "intervals": 1.2,
    "pma": 1.2,
    "sprint": 0.9,
    "endurance": 1.0,
    "recovery": 0.5,
}
```

Modifier `_TSS_PER_HOUR` (ligne ~221-240), ajouter une entrée par sport pour `pma`/`sprint`
juste après l'entrée `"intervals"` de chaque bloc :

```python
_TSS_PER_HOUR: dict[tuple[str, str], float] = {
    ("bike", "endurance"): 40.0,
    ("bike", "long"): 45.0,
    ("bike", "threshold"): 72.0,
    ("bike", "intervals"): 82.0,
    ("bike", "pma"): 88.0,
    ("bike", "sprint"): 65.0,
    ("bike", "recovery"): 22.0,
    ("run", "endurance"): 48.0,
    ("run", "long"): 52.0,
    ("run", "threshold"): 75.0,
    ("run", "intervals"): 90.0,
    ("run", "pma"): 95.0,
    ("run", "sprint"): 70.0,
    ("run", "recovery"): 30.0,
    ("swim", "endurance"): 50.0,
    ("swim", "long"): 55.0,
    ("swim", "threshold"): 72.0,
    ("swim", "intervals"): 85.0,
    ("swim", "pma"): 88.0,
    ("swim", "sprint"): 68.0,
    ("swim", "recovery"): 35.0,
    ("brick", "endurance"): 65.0,
    ("brick", "long"): 65.0,
}
```

Modifier `_ELEVATION_SESSION_WEIGHT` (ligne ~271-279) :

```python
_ELEVATION_SESSION_WEIGHT: dict[str, float] = {
    "long": 2.0,
    "endurance": 1.0,
    "threshold": 0.3,
    "intervals": 0.0,
    "pma": 0.0,
    "sprint": 0.0,
    "recovery": 0.0,
    "race": 1.0,
    "rest": 0.0,
}
```

- [ ] **Step 7: Écrire un test couvrant le calcul de séance de bout en bout pour pma/sprint**

Dans `worker/tests/coach/test_planner.py`, ajouter (proche de
`test_build_week_sessions_bike_longer_than_run_and_tss_consistent`) :

```python
def test_training_day_session_pma_uses_dedicated_tss_per_hour() -> None:
    from garmin_sync.coach.planner import _training_day_session, _tss_per_hour

    session = _training_day_session(
        day=date.today(),
        phase="peak",
        week_offset=0,
        stype="pma",
        sport="bike",
        tss_by_sport={"bike": 60.0},
        sport_weight_total={"bike": 1.0},
        weekly_elevation_by_sport={},
        sport_elevation_weight_total={},
    )
    assert session["session_type"] == "pma"
    expected_tss = round(
        session["target_duration_s"] / 3600 * _tss_per_hour("bike", "pma"), 2
    )
    assert session["target_tss"] == expected_tss
    # pma bike peak bounds: 40-60min (Task 4)
    assert 40 * 60 <= session["target_duration_s"] <= 60 * 60


def test_training_day_session_sprint_gets_no_elevation_target() -> None:
    from garmin_sync.coach.planner import _training_day_session

    session = _training_day_session(
        day=date.today(),
        phase="peak",
        week_offset=0,
        stype="sprint",
        sport="bike",
        tss_by_sport={"bike": 60.0},
        sport_weight_total={"bike": 1.0},
        weekly_elevation_by_sport={"bike": 200},
        sport_elevation_weight_total={"bike": 1.0},
    )
    assert not session.get("target_elevation_gain_m")
```

- [ ] **Step 8: Lancer la suite complète du planner**

```bash
cd worker && uv run pytest tests/coach/test_planner.py -v
```
Attendu : PASS pour tous les tests du fichier (anciens et nouveaux).

- [ ] **Step 9: Lancer toute la suite worker pour vérifier l'absence de régression globale**

```bash
cd worker && uv run pytest -v
```
Attendu : PASS complet (46+ tests, aucune régression sur les modules non touchés).

- [ ] **Step 10: Lint + types**

```bash
cd worker && uv run ruff format . && uv run ruff check . && uv run mypy src/
```
Attendu : aucune erreur.

- [ ] **Step 11: Commit**

```bash
git add worker/src/garmin_sync/coach/planner.py worker/tests/coach/test_planner.py
git commit -m "feat(coach): periodize sprint/pma session types by phase and level"
```

---

## Task 7: `lib/coach/workout-types.ts` — miroir TypeScript des champs cadence

**Files:**
- Modify: `lib/coach/workout-types.ts:3-12` (interface `IntervalTarget`)
- Test: `tests/unit/lib/coach/workout-types.test.ts`

**Interfaces:**
- Consumes: rien (fichier de types pur).
- Produces: `IntervalTarget.cadence_low?: number | null`, `IntervalTarget.cadence_high?: number | null`
  — miroir exact de la Task 2 côté Python.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `tests/unit/lib/coach/workout-types.test.ts`, ajouter dans le bloc `describe('workout-types')` :

```ts
  it('accepts optional cadence fields on IntervalTarget', () => {
    const target = { label: 'Z2', rpe: 5, cadence_low: 100, cadence_high: 110 } as const
    const b: IntervalBlock = { duration_s: 60, target, notes: null }
    expect(b.target.cadence_low).toBe(100)
    expect(b.target.cadence_high).toBe(110)
  })
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec (typecheck)**

```bash
pnpm typecheck
```
Attendu : erreur TS — `cadence_low`/`cadence_high` n'existent pas sur le type `IntervalTarget`.

- [ ] **Step 3: Ajouter les champs à l'interface**

Dans `lib/coach/workout-types.ts`, modifier `IntervalTarget` :

```ts
export interface IntervalTarget {
  label: Zone
  rpe: number // 1-10
  bpm_low?: number | null
  bpm_high?: number | null
  watts_low?: number | null
  watts_high?: number | null
  pace_low_kmh?: number | null
  pace_high_kmh?: number | null
  // Cadence : interprétation dépendante du sport (rpm vélo, foulées/min course,
  // coups de bras/min natation), jamais validée numériquement côté serveur.
  cadence_low?: number | null
  cadence_high?: number | null
}
```

- [ ] **Step 4: Lancer les vérifications pour confirmer le succès**

```bash
pnpm typecheck && pnpm vitest run tests/unit/lib/coach/workout-types.test.ts
```
Attendu : PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/coach/workout-types.ts tests/unit/lib/coach/workout-types.test.ts
git commit -m "feat(coach): mirror cadence fields in workout-types.ts"
```

---

## Task 8: `lib/onboarding/schemas.ts` — champ `css_per_100m_s`

**Files:**
- Modify: `lib/onboarding/schemas.ts:126-130` (`perfSchema`)
- Test: `tests/unit/onboarding/schemas.test.ts`

**Interfaces:**
- Produces: `perfSchema` accepte `css_per_100m_s?: number` (entier, 40-300), `PerfInput` inclut
  ce champ — consommé par la Task 9 (onboarding) et Task 10 (profil).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `tests/unit/onboarding/schemas.test.ts`, ajouter dans le bloc `describe('perfSchema')` :

```ts
  it('accepts css_per_100m_s within [40,300]', () => {
    expect(perfSchema.safeParse({ css_per_100m_s: 95 }).success).toBe(true)
  })

  it('rejects css_per_100m_s below 40', () => {
    expect(perfSchema.safeParse({ css_per_100m_s: 39 }).success).toBe(false)
  })

  it('rejects css_per_100m_s above 300', () => {
    expect(perfSchema.safeParse({ css_per_100m_s: 301 }).success).toBe(false)
  })
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

```bash
pnpm vitest run tests/unit/onboarding/schemas.test.ts
```
Attendu : FAIL — `css_per_100m_s` non reconnu par le schéma, `safeParse` avec ce champ inconnu
reste `success: true` (Zod ignore les clés en trop par défaut) mais le test "rejects" échoue
puisque aucune contrainte n'existe encore pour la borner.

- [ ] **Step 3: Ajouter le champ à `perfSchema`**

Dans `lib/onboarding/schemas.ts`, modifier `perfSchema` :

```ts
export const perfSchema = z.object({
  ftp_watts: z.number().int().min(50).max(600).optional(),
  vma_kmh: z.number().min(5).max(30).optional(),
  fc_max_bpm: z.number().int().min(100).max(230).optional(),
  css_per_100m_s: z.number().int().min(40).max(300).optional(),
})
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

```bash
pnpm vitest run tests/unit/onboarding/schemas.test.ts
```
Attendu : PASS pour tous les tests du fichier.

- [ ] **Step 5: Commit**

```bash
git add lib/onboarding/schemas.ts tests/unit/onboarding/schemas.test.ts
git commit -m "feat(onboarding): add css_per_100m_s to perfSchema"
```

---

## Task 9: Onboarding — champ CSS de bout en bout (formulaire + action + page)

**Files:**
- Modify: `app/(app)/onboarding/_components/step-perf-form.tsx`
- Modify: `app/(app)/onboarding/actions.ts:111-135` (`saveStepPerf`)
- Modify: `app/(app)/onboarding/page.tsx`
- Modify: `app/(app)/onboarding/_components/onboarding-wizard.tsx:30`
- Test: `tests/unit/onboarding/components/step-perf-form.test.tsx`
- Test: `tests/unit/onboarding/actions.test.ts`

**Interfaces:**
- Consumes: `PerfInput` (Task 8, inclut maintenant `css_per_100m_s`).
- Produces: le champ CSS est saisissable dans l'étape "perf" de l'onboarding, persisté dans
  `athlete_profiles.css_per_100m_s` (Task 1).

- [ ] **Step 1: Écrire le test qui échoue (formulaire)**

Dans `tests/unit/onboarding/components/step-perf-form.test.tsx`, ajouter dans le bloc
`describe('StepPerfForm')` :

```ts
  it('renders a CSS field and submits it', async () => {
    saveStepPerf.mockResolvedValue({ success: true, nextStep: 'dispo' })
    const onDone = vi.fn()
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(
      <StepPerfForm defaultValues={{ garmin_synced_at: '2026-05-15T10:00:00Z' }} onDone={onDone} />
    )
    const cssInput = screen.getByLabelText<HTMLInputElement>(/CSS/)
    fireEvent.change(cssInput, { target: { value: '95' } })
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(saveStepPerf).toHaveBeenCalledTimes(1)
    })
    const call = saveStepPerf.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.css_per_100m_s).toBe(95)
  })

  it('pre-fills CSS from defaultValues', async () => {
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(
      <StepPerfForm
        defaultValues={{ css_per_100m_s: 100, garmin_synced_at: '2026-05-15T10:00:00Z' }}
        onDone={vi.fn()}
      />
    )
    expect(screen.getByLabelText<HTMLInputElement>(/CSS/).value).toBe('100')
  })
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

```bash
pnpm vitest run tests/unit/onboarding/components/step-perf-form.test.tsx
```
Attendu : FAIL — `screen.getByLabelText(/CSS/)` ne trouve aucun élément (champ inexistant).

- [ ] **Step 3: Ajouter le champ CSS au formulaire**

Dans `app/(app)/onboarding/_components/step-perf-form.tsx`, ajouter l'état (après la ligne
`const [fcmax, setFcmax] = useState<string>(...)`) :

```tsx
  const [css, setCss] = useState<string>(defaultValues.css_per_100m_s?.toString() ?? '')
```

Modifier la soumission (`handleSubmit`) pour inclure le champ :

```tsx
    const result = await saveStepPerf({
      ftp_watts: ftp ? Number.parseInt(ftp, 10) : undefined,
      vma_kmh: vma ? Number.parseFloat(vma) : undefined,
      fc_max_bpm: fcmax ? Number.parseInt(fcmax, 10) : undefined,
      css_per_100m_s: css ? Number.parseInt(css, 10) : undefined,
    })
```

Ajouter le bloc JSX (après le bloc VMA, avant le bloc FC max — CSS est spécifique natation donc
placé logiquement à côté de VMA/FTP qui sont spécifiques à leur sport) :

```tsx
      <div className="space-y-2">
        <Label htmlFor="css">
          CSS (s/100m natation){' '}
          <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
        </Label>
        <Input
          id="css"
          type="number"
          min={40}
          max={300}
          value={css}
          onChange={(e) => {
            setCss(e.target.value)
          }}
          placeholder="ex: 95"
        />
        {errors.css_per_100m_s?.[0] && (
          <p className="text-destructive text-xs">{errors.css_per_100m_s[0]}</p>
        )}
      </div>
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

```bash
pnpm vitest run tests/unit/onboarding/components/step-perf-form.test.tsx
```
Attendu : PASS pour tous les tests du fichier (les tests existants ne référencent pas CSS donc
restent inchangés — le nouveau champ est optionnel et vide par défaut).

- [ ] **Step 5: Écrire le test qui échoue (Server Action)**

Dans `tests/unit/onboarding/actions.test.ts`, ajouter dans `describe('saveStepPerf')` :

```ts
  it('applies css_per_100m_s in the patch when provided', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    const chain = mkUpdateChain(null)
    fromMock.mockReturnValueOnce(chain)
    const { saveStepPerf } = await import('@/app/(app)/onboarding/actions')

    await saveStepPerf({ css_per_100m_s: 95 })
    expect(chain.update).toHaveBeenCalledWith({ css_per_100m_s: 95 })
  })
```

- [ ] **Step 6: Lancer le test pour vérifier l'échec**

```bash
pnpm vitest run tests/unit/onboarding/actions.test.ts
```
Attendu : FAIL — `saveStepPerf` actuel ignore `css_per_100m_s` (absent de `PerfInput` avant
Task 8, et non mappé dans le `patch` avant ce step).

- [ ] **Step 7: Mettre à jour `saveStepPerf`**

Dans `app/(app)/onboarding/actions.ts`, modifier `saveStepPerf` :

```ts
export async function saveStepPerf(input: PerfInput): Promise<StepResult> {
  const parsed = perfSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: z.flattenError(parsed.error).fieldErrors }
  }
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') return userIdOrErr

  const supabase = await createClient()
  const patch: Record<string, number | null> = {}
  if (parsed.data.ftp_watts !== undefined) patch.ftp_watts = parsed.data.ftp_watts
  if (parsed.data.vma_kmh !== undefined) patch.vma_kmh = parsed.data.vma_kmh
  if (parsed.data.fc_max_bpm !== undefined) patch.fc_max_bpm = parsed.data.fc_max_bpm
  if (parsed.data.css_per_100m_s !== undefined) patch.css_per_100m_s = parsed.data.css_per_100m_s

  if (Object.keys(patch).length > 0) {
    const { error } = await supabase
      .from('athlete_profiles')
      .update(patch)
      .eq('user_id', userIdOrErr)
    if (error) return { success: false, error: 'save_failed' }
  }

  revalidatePath(ONBOARDING_PATH)
  return { success: true, nextStep: nextStep('perf') }
}
```

- [ ] **Step 8: Lancer le test pour vérifier le succès**

```bash
pnpm vitest run tests/unit/onboarding/actions.test.ts
```
Attendu : PASS pour tous les tests du fichier.

- [ ] **Step 9: Propager le champ dans `page.tsx` et `onboarding-wizard.tsx`**

Dans `app/(app)/onboarding/page.tsx`, modifier l'interface `ProfileRow` (ajouter après
`vma_kmh: number | null`) :

```ts
  vma_kmh: number | null
  css_per_100m_s: number | null
```

Modifier `computeInitialStep` pour que CSS compte aussi comme un signal "perf" déjà rempli :

```ts
  const hasPerf =
    profile.ftp_watts !== null ||
    profile.vma_kmh !== null ||
    profile.fc_max_bpm !== null ||
    profile.css_per_100m_s !== null
```

Modifier l'objet `perf` dans `initial: WizardInitial` :

```ts
    perf: {
      ftp_watts: profile?.ftp_watts ?? undefined,
      vma_kmh: profile?.vma_kmh ?? undefined,
      fc_max_bpm: profile?.fc_max_bpm ?? undefined,
      css_per_100m_s: profile?.css_per_100m_s ?? undefined,
      garmin_synced_at: profile?.garmin_synced_at ?? null,
    },
```

Le `.select('*')` de la requête `athlete_profiles` (ligne 56) reste inchangé (`*` inclut déjà
la nouvelle colonne automatiquement).

Dans `app/(app)/onboarding/_components/onboarding-wizard.tsx`, modifier la ligne 30 :

```tsx
    if (
      initial.perf.ftp_watts ??
      initial.perf.vma_kmh ??
      initial.perf.fc_max_bpm ??
      initial.perf.css_per_100m_s
    )
      s.add('perf')
```

- [ ] **Step 10: Vérifier l'absence de régression sur le wizard**

```bash
pnpm vitest run tests/unit/onboarding/components/onboarding-wizard.test.tsx
```
Attendu : PASS (le test existant ne fournit pas `css_per_100m_s`, `undefined` se comporte comme
avant grâce au `??` en chaîne).

- [ ] **Step 11: Typecheck complet**

```bash
pnpm typecheck
```
Attendu : aucune erreur (tous les objets `PerfInput` littéraux du repo doivent rester valides —
`css_per_100m_s` est optionnel donc aucun site d'appel existant ne casse).

- [ ] **Step 12: Commit**

```bash
git add app/\(app\)/onboarding/_components/step-perf-form.tsx \
  app/\(app\)/onboarding/actions.ts \
  app/\(app\)/onboarding/page.tsx \
  app/\(app\)/onboarding/_components/onboarding-wizard.tsx \
  tests/unit/onboarding/components/step-perf-form.test.tsx \
  tests/unit/onboarding/actions.test.ts
git commit -m "feat(onboarding): add CSS (Critical Swim Speed) field to perf step"
```

---

## Task 10: Édition profil — champ CSS de bout en bout

**Files:**
- Modify: `app/(app)/profile/_components/perf-edit-form.tsx`
- Modify: `app/(app)/profile/page.tsx`
- Test: `tests/unit/profile/perf-edit-form.test.tsx`

**Interfaces:**
- Consumes: `PerfInput` (Task 8), `saveStepPerf` (Task 9, réutilisée telle quelle — ce
  formulaire appelle déjà l'action de l'onboarding).
- Produces: le champ CSS est visible (lecture seule) et modifiable dans `/profile`.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `tests/unit/profile/perf-edit-form.test.tsx`, modifier `baseInitial`/`emptyInitial` et
ajouter des assertions CSS :

```ts
const baseInitial: PerfInitial = {
  ftp_watts: 245,
  vma_kmh: 16.5,
  fc_max_bpm: 185,
  css_per_100m_s: 95,
  garmin_synced_at: '2026-05-15T10:00:00Z',
}

const emptyInitial: PerfInitial = {
  ftp_watts: undefined,
  vma_kmh: undefined,
  fc_max_bpm: undefined,
  css_per_100m_s: undefined,
  garmin_synced_at: null,
}
```

Modifier le test `'renders read-only summary with initial values'` pour ajouter :

```ts
    expect(screen.getByText(/95 s\/100m/)).toBeTruthy()
```

Modifier `'shows em-dashes and no sync banner when initial values are empty'` :

```ts
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBe(4)
```

Modifier `'switches to edit mode after clicking Modifier'` pour ajouter :

```ts
    expect(screen.getByLabelText(/CSS/)).toBeTruthy()
```

Modifier `'pre-fills input values from initial when entering edit mode'` pour ajouter :

```ts
    expect(screen.getByLabelText<HTMLInputElement>(/CSS/).value).toBe('95')
```

Modifier `'submits the form successfully and exits edit mode'` pour ajouter l'assertion :

```ts
    expect(call.css_per_100m_s).toBe(95)
```

Modifier `'submits with undefined fields when inputs are blank'` pour ajouter :

```ts
    expect(call.css_per_100m_s).toBeUndefined()
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

```bash
pnpm vitest run tests/unit/profile/perf-edit-form.test.tsx
```
Attendu : plusieurs FAIL — pas de champ CSS dans le composant actuel, `dashes.length` reste 3.

- [ ] **Step 3: Ajouter le champ CSS au composant**

Dans `app/(app)/profile/_components/perf-edit-form.tsx`, ajouter l'état (après
`const [fcmax, setFcmax] = useState<string>(...)`) :

```tsx
  const [css, setCss] = useState<string>(initial.css_per_100m_s?.toString() ?? '')
```

Modifier `handleCancel` :

```tsx
  function handleCancel() {
    setEdit(false)
    setFtp(initial.ftp_watts?.toString() ?? '')
    setVma(initial.vma_kmh?.toString() ?? '')
    setFcmax(initial.fc_max_bpm?.toString() ?? '')
    setCss(initial.css_per_100m_s?.toString() ?? '')
    setErrors({})
  }
```

Modifier le résumé lecture seule (bloc `<dl>`, ajouter une 4e colonne — passer `grid-cols-3` à
`grid-cols-4`) :

```tsx
        <dl className="text-muted-foreground grid grid-cols-4 gap-x-4 text-sm">
          <div>
            <dt className="text-xs tracking-wide uppercase">FTP</dt>
            <dd className="text-foreground">{ftp ? `${ftp} W` : '—'}</dd>
          </div>
          <div>
            <dt className="text-xs tracking-wide uppercase">VMA</dt>
            <dd className="text-foreground">{vma ? `${vma} km/h` : '—'}</dd>
          </div>
          <div>
            <dt className="text-xs tracking-wide uppercase">FC max</dt>
            <dd className="text-foreground">{fcmax ? `${fcmax} bpm` : '—'}</dd>
          </div>
          <div>
            <dt className="text-xs tracking-wide uppercase">CSS</dt>
            <dd className="text-foreground">{css ? `${css} s/100m` : '—'}</dd>
          </div>
        </dl>
```

Modifier `handleSave` :

```tsx
    const r = await saveStepPerf({
      ftp_watts: ftp ? Number.parseInt(ftp, 10) : undefined,
      vma_kmh: vma ? Number.parseFloat(vma) : undefined,
      fc_max_bpm: fcmax ? Number.parseInt(fcmax, 10) : undefined,
      css_per_100m_s: css ? Number.parseInt(css, 10) : undefined,
    })
```

Ajouter le bloc JSX d'édition (après le bloc FC max, avant les boutons `Enregistrer`/`Annuler`) :

```tsx
      <div className="space-y-2">
        <Label htmlFor="perf-css">CSS (s/100m natation)</Label>
        <Input
          id="perf-css"
          type="number"
          min={40}
          max={300}
          value={css}
          onChange={(e) => {
            setCss(e.target.value)
          }}
          placeholder="ex: 95"
        />
        {errors.css_per_100m_s?.[0] && (
          <p className="text-destructive text-xs">{errors.css_per_100m_s[0]}</p>
        )}
      </div>
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

```bash
pnpm vitest run tests/unit/profile/perf-edit-form.test.tsx
```
Attendu : PASS pour tous les tests du fichier.

- [ ] **Step 5: Propager le champ dans `page.tsx`**

Dans `app/(app)/profile/page.tsx`, modifier l'interface `AthleteProfileRow` (ajouter après
`vma_kmh: number | null`) :

```ts
  vma_kmh: number | null
  css_per_100m_s: number | null
```

Modifier la requête `select` (ligne 75) :

```ts
        .select(
          'first_name, dob, sex, city, country, consent_data_processing, ftp_watts, vma_kmh, fc_max_bpm, css_per_100m_s, garmin_synced_at, available_days, hours_per_week, sports_strengths'
        )
```

Modifier `perfInitial` :

```ts
  const perfInitial: PerfInput & { garmin_synced_at: string | null } = {
    ftp_watts: profile?.ftp_watts ?? undefined,
    vma_kmh: profile?.vma_kmh ?? undefined,
    fc_max_bpm: profile?.fc_max_bpm ?? undefined,
    css_per_100m_s: profile?.css_per_100m_s ?? undefined,
    garmin_synced_at: profile?.garmin_synced_at ?? null,
  }
```

- [ ] **Step 6: Typecheck + suite complète frontend**

```bash
pnpm typecheck && pnpm test
```
Attendu : aucune erreur, tous les tests unitaires passent.

- [ ] **Step 7: Commit**

```bash
git add app/\(app\)/profile/_components/perf-edit-form.tsx \
  app/\(app\)/profile/page.tsx \
  tests/unit/profile/perf-edit-form.test.tsx
git commit -m "feat(profile): add CSS (Critical Swim Speed) field to perf edit form"
```

---

## Task 11: `SessionType` (TS) — ajouter pma/sprint aux unions strictes et à la classification "hard session"

**Files:**
- Modify: `lib/dashboard/types.ts:3-10` (`SessionType`)
- Modify: `app/(app)/_components/sport-icon.tsx:31-39` (`SESSION_TYPE_LABEL`)
- Modify: `lib/coach/session-templates.ts:11-36` (`SessionType` locale + `TYPE_LABEL`)
- Modify: `lib/coach/activity-analysis.ts:668-670` (`hardSession`)
- Test: `tests/unit/lib/coach/activity-analysis.test.ts`

**Contexte (trouvé en relisant le code, absent du spec initial) :** `session_type` est une union
TS stricte à **deux endroits distincts** (`lib/dashboard/types.ts` et une définition locale
dupliquée dans `lib/coach/session-templates.ts`), chacune consommée par un `Record<SessionType,
string>` exhaustif (`SESSION_TYPE_LABEL`, `TYPE_LABEL`). Sans mise à jour, `pnpm typecheck`
échoue dès qu'une séance `pma`/`sprint` traverse ces types — c'est le comportement voulu (fail
au typecheck plutôt que silencieusement), mais il faut fournir les nouvelles branches.
`hardSession()` dans `lib/coach/activity-analysis.ts` classe `session_type` en "séance dure"
pour les suggestions d'ajustement post-activité (E9) — `pma`/`sprint` doivent y être inclus,
sinon une grosse séance PMA/sprint serait traitée comme "facile" par erreur dans cette logique.

**Interfaces:**
- Consumes: rien de nouveau.
- Produces: `SessionType` (les deux définitions) inclut `'pma' | 'sprint'` ; `hardSession()`
  classe ces deux types comme durs.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `tests/unit/lib/coach/activity-analysis.test.ts`, dans le bloc `describe('buildNextSessionAdjustment')`,
ajouter (à côté de `nextHardSession`) :

```ts
  const nextPmaSession: PlannedSession = {
    ...planned,
    id: 'next-pma',
    date: '2026-06-15',
    session_type: 'pma',
    target_duration_s: 2700,
    target_tss: 70,
  }

  const nextSprintSession: PlannedSession = {
    ...planned,
    id: 'next-sprint',
    date: '2026-06-15',
    session_type: 'sprint',
    target_duration_s: 2700,
    target_tss: 55,
  }
```

Puis, en s'inspirant du test existant qui utilise `nextHardSession` pour vérifier une
recommandation de prudence (chercher le test qui affirme sur `nextHardSession` dans ce fichier
et dupliquer son assertion clé pour les deux nouveaux cas — même `stableSummary`, même forme
d'assertion), ajouter :

```ts
  it('treats pma sessions as hard, same as intervals/threshold', () => {
    const result = buildNextSessionAdjustment(stableSummary, [nextPmaSession])
    const resultHard = buildNextSessionAdjustment(stableSummary, [nextHardSession])
    expect(result.action).toBe(resultHard.action)
  })

  it('treats sprint sessions as hard, same as intervals/threshold', () => {
    const result = buildNextSessionAdjustment(stableSummary, [nextSprintSession])
    const resultHard = buildNextSessionAdjustment(stableSummary, [nextHardSession])
    expect(result.action).toBe(resultHard.action)
  })
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

```bash
pnpm typecheck
```
Attendu : erreur TS — `session_type: 'pma'` n'est pas assignable à `SessionType`.

- [ ] **Step 3: Étendre `SessionType` dans `lib/dashboard/types.ts`**

```ts
export type SessionType =
  | 'endurance'
  | 'threshold'
  | 'intervals'
  | 'pma'
  | 'sprint'
  | 'long'
  | 'recovery'
  | 'race'
  | 'rest'
```

- [ ] **Step 4: Étendre `SESSION_TYPE_LABEL` dans `app/(app)/_components/sport-icon.tsx`**

```ts
export const SESSION_TYPE_LABEL: Record<SessionType, string> = {
  endurance: 'Endurance',
  threshold: 'Seuil',
  intervals: 'Intervalles',
  pma: 'PMA',
  sprint: 'Sprint',
  long: 'Sortie longue',
  recovery: 'Récupération',
  race: 'Course',
  rest: 'Repos',
}
```

- [ ] **Step 5: Étendre la `SessionType` locale et `TYPE_LABEL` dans `lib/coach/session-templates.ts`**

```ts
export type SessionType =
  | 'endurance'
  | 'threshold'
  | 'intervals'
  | 'pma'
  | 'sprint'
  | 'long'
  | 'recovery'
  | 'race'
  | 'rest'
```

```ts
const TYPE_LABEL: Record<SessionType, string> = {
  endurance: 'Endurance',
  threshold: 'Seuil',
  intervals: 'Fractionné',
  pma: 'PMA',
  sprint: 'Sprint',
  long: 'Sortie longue',
  recovery: 'Récupération',
  race: 'Course',
  rest: 'Repos',
}
```

- [ ] **Step 6: Étendre `hardSession()` dans `lib/coach/activity-analysis.ts`**

```ts
function hardSession(session: PlannedSession): boolean {
  return ['threshold', 'intervals', 'pma', 'sprint', 'long', 'race'].includes(session.session_type)
}
```

- [ ] **Step 7: Lancer les tests pour vérifier le succès**

```bash
pnpm typecheck && pnpm vitest run tests/unit/lib/coach/activity-analysis.test.ts
```
Attendu : PASS — le typecheck passe (toutes les branches des `Record` exhaustifs sont
couvertes), les deux nouveaux tests passent.

- [ ] **Step 8: Vérifier l'absence de régression sur les deux fichiers de test session-templates**

Le repo contient deux fichiers de test pour `session-templates.ts`
(`tests/unit/coach/session-templates.test.ts` ET `tests/unit/lib/coach/session-templates.test.ts`
— vérifié, ce ne sont pas des doublons, deux suites distinctes). Lancer les deux :

```bash
pnpm vitest run tests/unit/coach/session-templates.test.ts tests/unit/lib/coach/session-templates.test.ts
```
Attendu : PASS (aucune des deux ne référence une liste exhaustive de `SessionType` qui casserait
sur un ajout de variante — à confirmer par la lecture des fichiers si le typecheck de la Step 7
n'a rien remonté côté ces fichiers).

- [ ] **Step 9: Suite frontend complète**

```bash
pnpm lint && pnpm typecheck && pnpm test
```
Attendu : PASS.

- [ ] **Step 10: Commit**

```bash
git add lib/dashboard/types.ts app/\(app\)/_components/sport-icon.tsx \
  lib/coach/session-templates.ts lib/coach/activity-analysis.ts \
  tests/unit/lib/coach/activity-analysis.test.ts
git commit -m "feat(coach): recognize pma/sprint as valid+hard session types in frontend"
```

---

## Final Verification

- [ ] **Step 1: Suite complète worker**

```bash
cd worker && uv run pytest -v && uv run ruff format --check . && uv run ruff check . && uv run mypy src/
```
Attendu : tous les tests passent (46 tests d'origine + ~25 nouveaux), lint et types propres.

- [ ] **Step 2: Suite complète frontend**

```bash
rm -rf .next && pnpm lint && pnpm typecheck && pnpm test && pnpm build
```
Attendu : aucune erreur — le `rm -rf .next` évite le cache stale documenté dans `CLAUDE.md`
("`.next/types/` cache stale entre branches").

- [ ] **Step 3: Relire le spec et vérifier la couverture**

Relire `docs/superpowers/specs/2026-07-09-seances-ciblees-sprint-pma-design.md` section par
section et confirmer que chaque point a une tâche correspondante :
- Modèle de données (CSS + cadence) → Tasks 1, 2, 7, 8.
- Périodisation → Task 6.
- Génération LLM (caps, prompt, CSS) → Tasks 3, 5.
- Bornes de durée → Task 4.
- Frontend (onboarding + profil) → Tasks 9, 10.
- `session_type` union stricte côté frontend + classification "hard session" (gap identifié
  pendant la rédaction du plan, hors spec initial) → Task 11.
