# E13 — Plan réaliste & individualisé — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre les séances générées réalistes (durées crédibles), exploiter le niveau par discipline (volume + intensité), traiter `available_days` comme un masque plafonné par un plancher de repos, et afficher un aperçu pédagogique des durées + un vrai jour de repos côté UI.

**Architecture :** Le moteur Banister (worker Python) est conservé. On ajoute (1) une conversion `available_days` → jours d'entraînement plafonnée, (2) un plancher de volume hebdo basé sur `hours_per_week`, (3) un recalage `_TSS_PER_HOUR`, (4) un clamp déterministe des durées sur une table `[discipline][type][phase]`, (5) une modulation continue du niveau sur volume + filtrage des types par niveau, (6) une validation post-LLM par plafonds absolus, (7) un flag `is_rest_day` dans le briefing. Côté front, un module TS pur miroir alimente un aperçu live et `/today` masque les blocs séance un jour de repos.

**Tech Stack :** Python 3.12 + pytest (worker `worker/src/garmin_sync/coach/`), TypeScript + Vitest + Next.js (frontend `lib/coach/`, `app/(app)/`).

**Conventions :**
- Phases (de `phases.py`) : `"base" | "build" | "peak" | "taper"`.
- Types de séance : `"endurance" | "long" | "threshold" | "intervals" | "recovery"` (+ `"rest" | "race"`).
- Sports : `"swim" | "bike" | "run" | "brick"`. Attention : `sports_strengths` utilise les clés `swim/bike/run` ; le planner utilise `bike`/`run`/`swim`/`brick`.
- Tests worker : `cd worker && uv run pytest <path> -v`. Tests front : `pnpm test <path>`.
- Commits : Conventional Commits, body ≤ 100 chars.

---

## File Structure

| Fichier | Responsabilité | Action |
|---|---|---|
| `worker/src/garmin_sync/coach/training_days.py` | **Nouveau.** Conversion dispo→entraînement : caps, plancher repos, niveau global, sélection des jours, assignation sport (cap course, no back-to-back). | Create |
| `worker/src/garmin_sync/coach/duration_bounds.py` | **Nouveau.** Table de bornes `[discipline][type][phase]` + `clamp_duration_to_bounds` + sélection dans la fourchette selon niveau. | Create |
| `worker/src/garmin_sync/coach/planner.py` | Plancher de volume hebdo, modulation niveau continue, filtrage types par niveau, intégration training_days + clamp. | Modify |
| `worker/src/garmin_sync/coach/workout_schema.py` | Plafonds échauffement/RAC + plancher corps + plancher durée absolu par type. | Modify |
| `worker/src/garmin_sync/coach/openai_client.py` | Consigne d'intensité selon le niveau. | Modify |
| `worker/src/garmin_sync/coach/briefing.py` | Flag `is_rest_day` dans le payload. | Modify |
| `lib/coach/duration-preview.ts` | **Nouveau.** Module TS pur miroir (bornes + caps + nb séances/repos). | Create |
| `app/(app)/profile/_components/dispo-edit-form.tsx` | Encart aperçu live. | Modify |
| `app/(app)/onboarding/_components/step-dispo-form.tsx` | Encart aperçu live. | Modify |
| `app/(app)/today/page.tsx` | Repos = message récup, masque blocs séance via `is_rest_day`. | Modify |

Tests créés/modifiés :
- `worker/tests/coach/test_training_days.py` (nouveau)
- `worker/tests/coach/test_duration_bounds.py` (nouveau)
- `worker/tests/coach/test_planner.py` (modifié)
- `worker/tests/coach/test_workout_schema.py` (modifié)
- `worker/tests/coach/test_briefing.py` (modifié)
- `tests/unit/lib/coach/duration-preview.test.ts` (nouveau)

---

## Task 1 : Module `duration_bounds.py` (bornes + clamp)

**Files:**
- Create: `worker/src/garmin_sync/coach/duration_bounds.py`
- Test: `worker/tests/coach/test_duration_bounds.py`

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# worker/tests/coach/test_duration_bounds.py
from garmin_sync.coach.duration_bounds import clamp_duration_to_bounds, duration_bounds_s


def test_bike_endurance_base_floor_is_90min():
    low, high = duration_bounds_s("bike", "endurance", "base")
    assert low == 90 * 60
    assert high == 180 * 60


def test_clamp_raises_short_bike_endurance_to_floor():
    # régression : 45min vélo endurance base -> ramené à >= 1h30
    assert clamp_duration_to_bounds("bike", "endurance", "base", 45 * 60) == 90 * 60


def test_clamp_caps_overlong_run_endurance():
    assert clamp_duration_to_bounds("run", "endurance", "base", 200 * 60) == 60 * 60


def test_clamp_keeps_value_inside_bounds():
    assert clamp_duration_to_bounds("run", "endurance", "base", 50 * 60) == 50 * 60


def test_unknown_combo_returns_value_unchanged():
    assert clamp_duration_to_bounds("brick", "intervals", "base", 30 * 60) == 30 * 60
```

- [ ] **Step 2 : Lancer le test (échec attendu)**

Run: `cd worker && uv run pytest tests/coach/test_duration_bounds.py -v`
Expected: FAIL (ModuleNotFoundError: duration_bounds).

- [ ] **Step 3 : Implémenter le module**

```python
# worker/src/garmin_sync/coach/duration_bounds.py
"""Réalisme des durées : bornes plancher/plafond par (discipline, type, phase).

Filet de sécurité déterministe par-dessus le calcul TSS du planner : aucune
séance ne sort en dehors de ces fourchettes (en minutes), calibrées sur les
normes coach triathlon amateur.
"""

from __future__ import annotations

# (low_min, high_min) en MINUTES totales, indexé [discipline][type][phase].
# phase ∈ base/build/peak/taper ; on mappe taper sur la colonne "peak" (volume réduit).
_BOUNDS_MIN: dict[tuple[str, str, str], tuple[int, int]] = {
    # natation
    ("swim", "recovery", "base"): (30, 40),
    ("swim", "endurance", "base"): (45, 60),
    ("swim", "threshold", "base"): (45, 60),
    ("swim", "intervals", "base"): (45, 60),
    ("swim", "long", "base"): (60, 75),
    ("swim", "endurance", "build"): (50, 70),
    ("swim", "threshold", "build"): (50, 70),
    ("swim", "intervals", "build"): (50, 65),
    ("swim", "long", "build"): (70, 90),
    ("swim", "endurance", "peak"): (40, 55),
    ("swim", "intervals", "peak"): (40, 55),
    ("swim", "long", "peak"): (50, 60),
    ("swim", "recovery", "peak"): (25, 35),
    # vélo
    ("bike", "recovery", "base"): (30, 45),
    ("bike", "endurance", "base"): (90, 180),
    ("bike", "threshold", "base"): (60, 90),
    ("bike", "intervals", "base"): (60, 75),
    ("bike", "long", "base"): (120, 210),
    ("bike", "endurance", "build"): (90, 150),
    ("bike", "threshold", "build"): (75, 120),
    ("bike", "intervals", "build"): (60, 90),
    ("bike", "long", "build"): (150, 240),
    ("bike", "endurance", "peak"): (60, 105),
    ("bike", "intervals", "peak"): (50, 70),
    ("bike", "long", "peak"): (90, 150),
    ("bike", "recovery", "peak"): (30, 40),
    # course
    ("run", "recovery", "base"): (30, 40),
    ("run", "endurance", "base"): (40, 60),
    ("run", "threshold", "base"): (40, 55),
    ("run", "intervals", "base"): (45, 60),
    ("run", "long", "base"): (60, 90),
    ("run", "endurance", "build"): (45, 70),
    ("run", "threshold", "build"): (50, 65),
    ("run", "intervals", "build"): (50, 65),
    ("run", "long", "build"): (75, 105),
    ("run", "endurance", "peak"): (35, 50),
    ("run", "intervals", "peak"): (40, 55),
    ("run", "long", "peak"): (50, 70),
    ("run", "recovery", "peak"): (25, 35),
}


def _phase_key(phase: str) -> str:
    """Taper partage les bornes réduites de peak."""
    return "peak" if phase == "taper" else phase


def duration_bounds_s(sport: str, stype: str, phase: str) -> tuple[int, int] | None:
    """Bornes (low, high) en SECONDES, ou None si le combo n'est pas borné."""
    bounds = _BOUNDS_MIN.get((sport, stype, _phase_key(phase)))
    if bounds is None:
        return None
    low, high = bounds
    return low * 60, high * 60


def clamp_duration_to_bounds(sport: str, stype: str, phase: str, duration_s: int) -> int:
    """Ramène duration_s dans la fourchette réaliste. Inchangé si non borné."""
    bounds = duration_bounds_s(sport, stype, phase)
    if bounds is None:
        return duration_s
    low, high = bounds
    return max(low, min(high, duration_s))
```

- [ ] **Step 4 : Lancer le test (succès attendu)**

Run: `cd worker && uv run pytest tests/coach/test_duration_bounds.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5 : Commit**

```bash
git add worker/src/garmin_sync/coach/duration_bounds.py worker/tests/coach/test_duration_bounds.py
git commit -m "feat(coach): add realistic duration bounds and clamp"
```

---

## Task 2 : Module `training_days.py` (conversion dispo→entraînement)

**Files:**
- Create: `worker/src/garmin_sync/coach/training_days.py`
- Test: `worker/tests/coach/test_training_days.py`

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# worker/tests/coach/test_training_days.py
from garmin_sync.coach.training_days import (
    athlete_level,
    cap_niveau,
    cap_volume,
    repos_min,
    training_days_count,
)


def test_cap_volume_by_hours():
    assert cap_volume(4) == 4
    assert cap_volume(6) == 5
    assert cap_volume(8) == 6
    assert cap_volume(10) == 6


def test_athlete_level_from_strengths():
    assert athlete_level({"swim": 1, "bike": 2, "run": 2}) == "beginner"
    assert athlete_level({"swim": 3, "bike": 3, "run": 3}) == "intermediate"
    assert athlete_level({"swim": 4, "bike": 5, "run": 4}) == "advanced"


def test_cap_niveau():
    assert cap_niveau("beginner") == 4
    assert cap_niveau("intermediate") == 5
    assert cap_niveau("advanced") == 6


def test_repos_min_beginner_floor_two():
    assert repos_min("beginner", "base") == 2
    assert repos_min("intermediate", "base") == 1
    assert repos_min("intermediate", "taper") == 2


def test_training_days_count_intermediate_7avail_8h():
    # N=7, H=8, intermédiaire, build -> 5 jours d'entraînement
    assert training_days_count(n_available=7, hours=8, level="intermediate", phase="build") == 5


def test_training_days_count_beginner_7avail_4h():
    # N=7, H=4, débutant, base -> 4 jours
    assert training_days_count(n_available=7, hours=4, level="beginner", phase="base") == 4


def test_training_days_count_never_below_one_rest():
    # N=7 -> au moins 1 repos garanti même chez l'avancé volume élevé
    assert training_days_count(n_available=7, hours=12, level="advanced", phase="build") <= 6
```

- [ ] **Step 2 : Lancer le test (échec attendu)**

Run: `cd worker && uv run pytest tests/coach/test_training_days.py -v`
Expected: FAIL (ModuleNotFoundError: training_days).

- [ ] **Step 3 : Implémenter le module**

```python
# worker/src/garmin_sync/coach/training_days.py
"""Disponibilité ≠ entraînement.

`available_days` est un masque de fenêtres possibles. On choisit un sous-ensemble
de jours d'entraînement plafonné par le volume, le niveau et un plancher de repos.
"""

from __future__ import annotations

Level = str  # "beginner" | "intermediate" | "advanced"


def athlete_level(sports_strengths: dict[str, int]) -> Level:
    """Niveau global dérivé de la moyenne des notes 1-5 par discipline."""
    scores = [sports_strengths.get(s, 3) for s in ("swim", "bike", "run")]
    mean = sum(scores) / len(scores)
    if mean < 2.5:
        return "beginner"
    if mean < 3.75:
        return "intermediate"
    return "advanced"


def cap_volume(hours: float | None) -> int:
    """Jours d'entraînement max selon le volume hebdo cible."""
    h = hours or 0
    if h < 5:
        return 4
    if h < 7:
        return 5
    return 6


def cap_niveau(level: Level) -> int:
    return {"beginner": 4, "intermediate": 5, "advanced": 6}[level]


def repos_min(level: Level, phase: str) -> int:
    """Plancher de jours OFF complet. Toujours >= 1."""
    level_floor = 2 if level == "beginner" else 1
    phase_floor = 2 if phase in ("taper", "deload") else 1
    return max(level_floor, phase_floor)


def training_days_count(*, n_available: int, hours: float | None, level: Level, phase: str) -> int:
    """Nombre effectif de jours d'entraînement (>= 0, garantit le plancher repos)."""
    return max(
        0,
        min(
            n_available,
            cap_volume(hours),
            cap_niveau(level),
            7 - repos_min(level, phase),
        ),
    )
```

- [ ] **Step 4 : Lancer le test (succès attendu)**

Run: `cd worker && uv run pytest tests/coach/test_training_days.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5 : Commit**

```bash
git add worker/src/garmin_sync/coach/training_days.py worker/tests/coach/test_training_days.py
git commit -m "feat(coach): convert availability to capped training days"
```

---

## Task 3 : Sélection des jours d'entraînement + assignation sport

**Files:**
- Modify: `worker/src/garmin_sync/coach/training_days.py`
- Test: `worker/tests/coach/test_training_days.py`

But : à partir des indices de jours dispo (0=lundi … 6=dimanche) et d'un nombre cible, choisir quels jours sont entraînés (espacés), et assigner les sports en respectant un cap course + jamais 2 jours course consécutifs.

- [ ] **Step 1 : Ajouter les tests qui échouent**

```python
# (ajouter à worker/tests/coach/test_training_days.py)
from garmin_sync.coach.training_days import assign_sports, select_training_days, run_cap


def test_select_spreads_days():
    # 7 dispo, 5 retenus -> on retire des jours pour espacer, repos inclus
    chosen = select_training_days(available_idx={0, 1, 2, 3, 4, 5, 6}, count=5)
    assert len(chosen) == 5
    assert chosen <= {0, 1, 2, 3, 4, 5, 6}


def test_select_count_zero_returns_empty():
    assert select_training_days(available_idx={0, 2, 4}, count=0) == set()


def test_select_count_ge_available_returns_all():
    assert select_training_days(available_idx={0, 2, 4}, count=9) == {0, 2, 4}


def test_run_cap_by_level():
    assert run_cap("beginner") == 2
    assert run_cap("intermediate") == 3
    assert run_cap("advanced") == 4


def test_assign_sports_no_back_to_back_run():
    # 3 sports, jours consécutifs -> pas deux "run" qui se suivent
    days = [0, 1, 2, 3, 4]
    assignment = assign_sports(
        training_idx=days, sports_in_race=["swim", "bike", "run"], level="intermediate"
    )
    ordered = [assignment[d] for d in days]
    for a, b in zip(ordered, ordered[1:]):
        assert not (a == "run" and b == "run")


def test_assign_sports_respects_run_cap():
    days = [0, 1, 2, 3, 4, 5]
    assignment = assign_sports(
        training_idx=days, sports_in_race=["run"], level="beginner"
    )
    assert sum(1 for s in assignment.values() if s == "run") <= run_cap("beginner")
```

- [ ] **Step 2 : Lancer (échec attendu)**

Run: `cd worker && uv run pytest tests/coach/test_training_days.py -v`
Expected: FAIL (ImportError: select_training_days/assign_sports/run_cap).

- [ ] **Step 3 : Implémenter**

```python
# (ajouter à worker/src/garmin_sync/coach/training_days.py)


def run_cap(level: Level) -> int:
    """Jours course max/semaine (impact traumatisant)."""
    return {"beginner": 2, "intermediate": 3, "advanced": 4}[level]


def select_training_days(*, available_idx: set[int], count: int) -> set[int]:
    """Choisit `count` jours parmi les dispo en les espaçant le plus possible."""
    days = sorted(available_idx)
    if count <= 0:
        return set()
    if count >= len(days):
        return set(days)
    # échantillonnage régulier sur la liste triée pour maximiser l'espacement
    step = len(days) / count
    picked = {days[min(len(days) - 1, round(i * step))] for i in range(count)}
    # ajuste si des collisions d'arrondi réduisent le compte
    i = 0
    while len(picked) < count and i < len(days):
        picked.add(days[i])
        i += 1
    return set(sorted(picked)[:count])


def assign_sports(
    *, training_idx: list[int], sports_in_race: list[str], level: Level
) -> dict[int, str]:
    """Assigne un sport à chaque jour d'entraînement.

    Règles : jamais deux jours "run" consécutifs, cap course par niveau, surplus
    reporté sur les autres sports (faible impact).
    """
    if not sports_in_race:
        return dict.fromkeys(sorted(training_idx), "run")
    ordered = sorted(training_idx)
    non_run = [s for s in sports_in_race if s != "run"] or sports_in_race
    cap = run_cap(level) if "run" in sports_in_race else 0
    assignment: dict[int, str] = {}
    run_used = 0
    rotation = 0
    prev: str | None = None
    for day in ordered:
        candidate = sports_in_race[rotation % len(sports_in_race)]
        rotation += 1
        blocked_run = candidate == "run" and (prev == "run" or run_used >= cap)
        if blocked_run:
            candidate = non_run[rotation % len(non_run)]
        if candidate == "run":
            run_used += 1
        assignment[day] = candidate
        prev = candidate
    return assignment
```

- [ ] **Step 4 : Lancer (succès attendu)**

Run: `cd worker && uv run pytest tests/coach/test_training_days.py -v`
Expected: PASS.

- [ ] **Step 5 : Commit**

```bash
git add worker/src/garmin_sync/coach/training_days.py worker/tests/coach/test_training_days.py
git commit -m "feat(coach): select spaced training days and assign sports with run cap"
```

---

## Task 4 : Modulation continue du niveau sur le volume

**Files:**
- Modify: `worker/src/garmin_sync/coach/planner.py:33-55`
- Test: `worker/tests/coach/test_planner.py`

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# (ajouter à worker/tests/coach/test_planner.py)
from garmin_sync.coach.planner import distribute_weekly_tss_by_sport


def test_weak_sport_gets_more_volume_than_strong_continuous():
    out = distribute_weekly_tss_by_sport(
        weekly_tss=300,
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 1, "bike": 5, "run": 3},
    )
    assert round(sum(out.values()), 1) == 300.0
    assert out["swim"] > out["run"] > out["bike"]


def test_level_2_and_1_differ():
    # l'échelle continue distingue 1 de 2 (vs anciens paliers identiques)
    a = distribute_weekly_tss_by_sport(
        weekly_tss=200, sports_in_race=["swim", "bike"], sports_strengths={"swim": 1, "bike": 3}
    )
    b = distribute_weekly_tss_by_sport(
        weekly_tss=200, sports_in_race=["swim", "bike"], sports_strengths={"swim": 2, "bike": 3}
    )
    assert a["swim"] > b["swim"]
```

- [ ] **Step 2 : Lancer (échec attendu)**

Run: `cd worker && uv run pytest tests/coach/test_planner.py -k "continuous or level_2" -v`
Expected: FAIL (anciens paliers : 1 et 2 donnent le même poids).

- [ ] **Step 3 : Remplacer la fonction**

Dans `planner.py`, remplacer le corps de `distribute_weekly_tss_by_sport` (lignes 45-55) :

```python
    weights: dict[str, float] = {}
    for s in sports_in_race:
        score = sports_strengths.get(s, 3)
        # modulation continue : niveau 1 -> 1.25, niveau 3 -> 1.0, niveau 5 -> 0.85.
        weights[s] = 1.25 - (score - 1) * 0.10
    total_w = sum(weights.values())
    return {s: round(weekly_tss * w / total_w, 2) for s, w in weights.items()}
```

Mettre à jour la docstring (lignes 39-44) :

```python
    """Distribute weekly TSS target between sports.

    Niveau par discipline (1-5) module la part : faible (1) ~+25%, fort (5) ~-15%,
    interpolation linéaire. Normalisé pour que la somme égale weekly_tss.
    """
```

- [ ] **Step 4 : Lancer (succès attendu)**

Run: `cd worker && uv run pytest tests/coach/test_planner.py -v`
Expected: PASS (vérifier qu'aucun test existant ne casse ; si un test attendait les anciens paliers 1.20/0.90, l'ajuster aux nouvelles valeurs).

- [ ] **Step 5 : Commit**

```bash
git add worker/src/garmin_sync/coach/planner.py worker/tests/coach/test_planner.py
git commit -m "feat(coach): make per-sport level volume modulation continuous"
```

---

## Task 5 : Filtrage des types de séance par niveau

**Files:**
- Modify: `worker/src/garmin_sync/coach/planner.py:58-67`
- Test: `worker/tests/coach/test_planner.py`

`pick_session_types_for_phase` prend désormais le niveau de la discipline dominante du jour. Pour rester simple et testable, on ajoute un paramètre `max_level` (le niveau le plus bas parmi les sports entraînés, qui borne l'intensité globale du set de types).

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# (ajouter à worker/tests/coach/test_planner.py)
from garmin_sync.coach.planner import pick_session_types_for_phase


def test_beginner_build_has_no_hard_intervals():
    types = pick_session_types_for_phase("build", max_level=1)
    assert "threshold" not in types
    assert "intervals" not in types
    assert "endurance" in types


def test_level3_build_allows_threshold_not_intervals():
    types = pick_session_types_for_phase("build", max_level=3)
    assert "threshold" in types
    assert "intervals" not in types


def test_advanced_peak_allows_intervals():
    types = pick_session_types_for_phase("peak", max_level=5)
    assert "intervals" in types
```

- [ ] **Step 2 : Lancer (échec attendu)**

Run: `cd worker && uv run pytest tests/coach/test_planner.py -k "level" -v`
Expected: FAIL (signature ne prend pas `max_level`).

- [ ] **Step 3 : Modifier la fonction**

Remplacer `pick_session_types_for_phase` (lignes 58-67) :

```python
_HARD_TYPES_BY_LEVEL: dict[int, set[str]] = {
    1: set(),
    2: set(),
    3: {"threshold"},
    4: {"threshold", "intervals"},
    5: {"threshold", "intervals"},
}


def pick_session_types_for_phase(phase: Phase, *, max_level: int = 5) -> list[str]:
    """Return the canonical set of session types for a given phase.

    `max_level` (1-5) borne l'intensité : un niveau faible retire les types durs
    (threshold/intervals) au profit d'endurance/recovery.
    """
    if phase == "base":
        base = ["endurance", "long", "recovery"]
    elif phase == "build":
        base = ["endurance", "threshold", "long"]
    elif phase == "peak":
        base = ["intervals", "endurance", "long"]
    else:  # taper
        base = ["endurance", "recovery"]

    allowed_hard = _HARD_TYPES_BY_LEVEL.get(max_level, {"threshold", "intervals"})
    filtered = [t for t in base if t not in {"threshold", "intervals"} or t in allowed_hard]
    return filtered or ["endurance"]
```

- [ ] **Step 4 : Lancer (succès attendu)**

Run: `cd worker && uv run pytest tests/coach/test_planner.py -v`
Expected: PASS (les appels existants sans `max_level` gardent le défaut 5 → comportement inchangé).

- [ ] **Step 5 : Commit**

```bash
git add worker/src/garmin_sync/coach/planner.py worker/tests/coach/test_planner.py
git commit -m "feat(coach): gate hard session types by athlete level"
```

---

## Task 6 : Recalage `_TSS_PER_HOUR` + plancher de volume hebdo

**Files:**
- Modify: `worker/src/garmin_sync/coach/planner.py:159-178` et `:570-574`
- Test: `worker/tests/coach/test_planner.py`

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# (ajouter à worker/tests/coach/test_planner.py)
from garmin_sync.coach.planner import weekly_tss_floor_from_hours


def test_weekly_tss_floor_scales_with_hours():
    # 8h/sem -> plancher ~ 8 * 45 = 360 TSS (Z2 dominant)
    assert weekly_tss_floor_from_hours(8) == 360
    assert weekly_tss_floor_from_hours(None) == 0
```

- [ ] **Step 2 : Lancer (échec attendu)**

Run: `cd worker && uv run pytest tests/coach/test_planner.py -k floor -v`
Expected: FAIL (fonction inexistante).

- [ ] **Step 3 : Recaler la table + ajouter le plancher**

Dans `planner.py`, abaisser les valeurs endurance de `_TSS_PER_HOUR` (lignes 160-174) :

```python
    ("bike", "endurance"): 40.0,
    ("bike", "long"): 45.0,
    ("bike", "threshold"): 72.0,
    ("bike", "intervals"): 82.0,
    ("bike", "recovery"): 22.0,
    ("run", "endurance"): 48.0,
    ("run", "long"): 52.0,
    ("run", "threshold"): 75.0,
    ("run", "intervals"): 90.0,
    ("run", "recovery"): 30.0,
    ("swim", "endurance"): 50.0,
    ("swim", "long"): 55.0,
    ("swim", "threshold"): 72.0,
    ("swim", "intervals"): 85.0,
    ("swim", "recovery"): 35.0,
```

Ajouter après `_tss_per_hour` (après ligne 182) :

```python
# TSS/h moyen pondéré d'une semaine type (Z2 dominant) pour ancrer le volume
# sur les heures déclarées, indépendamment du CTL lissé.
_AVG_WEEKLY_TSS_PER_HOUR = 45.0


def weekly_tss_floor_from_hours(hours_per_week: float | None) -> int:
    """Volume hebdo plancher dérivé des heures déclarées (avant ramp)."""
    if not hours_per_week:
        return 0
    return round(hours_per_week * _AVG_WEEKLY_TSS_PER_HOUR)
```

Modifier la boucle de génération (lignes 570-574) :

```python
    for offset, phase in phases:
        ramp = _ramp_rate_for_week(offset, phase)
        base_weekly = max(today_state.ctl * 7, weekly_tss_floor_from_hours(profile.get("hours_per_week")))
        weekly_tss = base_weekly * ramp
        if offset == 0:
            weekly_tss *= first_week_tss_multiplier
```

- [ ] **Step 4 : Lancer (succès attendu)**

Run: `cd worker && uv run pytest tests/coach/test_planner.py -v`
Expected: PASS. Ajuster tout test existant qui assertait des durées/TSS précis liés aux anciennes valeurs.

- [ ] **Step 5 : Commit**

```bash
git add worker/src/garmin_sync/coach/planner.py worker/tests/coach/test_planner.py
git commit -m "feat(coach): floor weekly volume on declared hours and recalibrate TSS/h"
```

---

## Task 7 : Intégrer training_days + clamp dans la génération de semaine

**Files:**
- Modify: `worker/src/garmin_sync/coach/planner.py` (`_training_day_session`, `_build_week_sessions`, `generate_plan`)
- Test: `worker/tests/coach/test_planner.py`

C'est la tâche d'intégration : `_build_week_sessions` reçoit `hours_per_week` + `level`, calcule les jours d'entraînement effectifs, marque le reste en repos, assigne les sports via `assign_sports`, et clampe chaque durée.

- [ ] **Step 1 : Écrire le test d'intégration qui échoue**

```python
# (ajouter à worker/tests/coach/test_planner.py)
from garmin_sync.coach.planner import _build_week_sessions
from datetime import date


def _count(sessions, stype):
    return sum(1 for s in sessions if s["session_type"] == stype)


def test_build_week_caps_training_days_when_all_available():
    sessions = _build_week_sessions(
        week_offset=0,
        phase="build",
        week_start=date(2026, 6, 22),  # lundi
        weekly_tss=400,
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        hours_per_week=8,
        is_last_week=False,
        race_date=date(2026, 9, 1),
        race_sport="run",
    )
    assert len(sessions) == 7  # une ligne par jour
    rest = _count(sessions, "rest")
    assert rest >= 1  # plancher repos garanti même si dispo 7j
    training = [s for s in sessions if s["session_type"] not in ("rest", "race")]
    assert len(training) == 5  # intermédiaire / 8h / build


def test_build_week_clamps_bike_endurance_duration():
    sessions = _build_week_sessions(
        week_offset=0,
        phase="base",
        week_start=date(2026, 6, 22),
        weekly_tss=120,  # faible -> durées qui seraient trop courtes sans clamp
        sports_in_race=["bike"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        available_days=["mon", "wed", "fri"],
        hours_per_week=6,
        is_last_week=False,
        race_date=date(2026, 9, 1),
        race_sport="bike",
    )
    bike_end = [s for s in sessions if s["sport"] == "bike" and s["session_type"] == "endurance"]
    assert bike_end, "au moins une endurance vélo"
    assert all(s["target_duration_s"] >= 90 * 60 for s in bike_end)
```

- [ ] **Step 2 : Lancer (échec attendu)**

Run: `cd worker && uv run pytest tests/coach/test_planner.py -k "caps_training or clamps_bike" -v`
Expected: FAIL (`_build_week_sessions` n'a pas les paramètres `hours_per_week` ; pas de cap ni clamp).

- [ ] **Step 3 : Modifier le planner**

3a. Importer les helpers en tête de `planner.py` (après ligne 18) :

```python
from garmin_sync.coach.duration_bounds import clamp_duration_to_bounds
from garmin_sync.coach.training_days import (
    assign_sports,
    athlete_level,
    select_training_days,
    training_days_count,
)
```

3b. Dans `_training_day_session`, clamper la durée et accepter un `sport` imposé. Ajouter le paramètre `sport: str` à la signature (remplaçant le calcul `sport = sports_in_race[...]`), et après le calcul `duration_s` (ligne 268) :

```python
    duration_s = int(per_day_tss * 3600 / _tss_per_hour(sport, stype))
    duration_s = clamp_duration_to_bounds(sport, stype, phase, duration_s)
```

Supprimer la ligne `sport = sports_in_race[day_idx % len(sports_in_race)] if sports_in_race else "run"` (ligne 263) puisque `sport` est désormais passé en argument.

3c. Modifier `_build_week_sessions` : ajouter les paramètres `hours_per_week: float | None` et calculer le niveau + les jours d'entraînement. Remplacer la logique de la boucle (lignes 393-444) :

```python
    level = athlete_level(sports_strengths)
    max_level = min(sports_strengths.get(s, 3) for s in sports_in_race) if sports_in_race else 3
    types_for_phase = pick_session_types_for_phase(phase, max_level=max_level)

    available_idx = {DAY_NAME_TO_INDEX[d] for d in available_days if d in DAY_NAME_TO_INDEX}
    is_deload = (week_offset + 1) % 4 == 0
    phase_for_rest = "deload" if is_deload and phase != "taper" else phase
    count = training_days_count(
        n_available=len(available_idx), hours=hours_per_week, level=level, phase=phase_for_rest
    )
    training_idx = select_training_days(available_idx=available_idx, count=count)
    sport_by_day = assign_sports(
        training_idx=sorted(training_idx), sports_in_race=sports_in_race, level=level
    )

    # recompute des poids de session sur les seuls jours d'entraînement retenus
    # (les helpers _precompute_* doivent itérer sur training_idx, pas available_idx)
```

> Note d'implémentation : `_precompute_sport_weights` et `_precompute_elevation_weights` doivent recevoir `training_idx` (set des jours retenus) au lieu de `available_idx`, et `_pick_session_type`/assignation doivent utiliser `sport_by_day[day_idx]`. Adapter leurs signatures (`available_idx` → `training_idx`) et la boucle finale :

```python
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_idx = day.weekday()
        if is_last_week and day == race_date:
            sessions.append(_race_day_session(day=day, race_sport=race_sport, week_offset=week_offset))
            continue
        if day_idx not in training_idx:
            sessions.append(_rest_day_session(day=day, phase=phase, week_offset=week_offset))
            continue
        sessions.append(
            _training_day_session(
                day=day,
                day_idx=day_idx,
                phase=phase,
                week_offset=week_offset,
                types_for_phase=types_for_phase,
                sport=sport_by_day[day_idx],
                tss_by_sport=tss_by_sport,
                used_types=used_types,
                sport_weight_total=sport_weight_total,
                weekly_elevation_by_sport=weekly_elevation_by_sport,
                sport_elevation_weight_total=sport_elev_weight_total,
            )
        )
    return sessions
```

> Les `_precompute_*` partagent l'assignation : passer `sport_by_day` pour que la somme des poids par sport reste cohérente. Mettre à jour leurs corps pour itérer `for day_idx in sorted(training_idx)` et utiliser `sport_by_day[day_idx]`.

3d. Dans `generate_plan`, passer `hours_per_week` à `_build_week_sessions` (vers ligne 576) :

```python
        sessions = _build_week_sessions(
            week_offset=offset,
            phase=phase,
            week_start=week_start + timedelta(weeks=offset),
            weekly_tss=weekly_tss,
            sports_in_race=sports_in_race,
            sports_strengths=sports_strengths,
            available_days=available_days,
            hours_per_week=profile.get("hours_per_week"),
            is_last_week=is_last,
            race_date=race_date,
            race_sport=race_sport,
            weekly_elevation_by_sport=weekly_elevation_by_sport,
        )
```

- [ ] **Step 4 : Lancer toute la suite planner (succès attendu)**

Run: `cd worker && uv run pytest tests/coach/test_planner.py -v`
Expected: PASS. Corriger les tests existants dont les hypothèses (assignation sport par modulo, nombre de jours = nb dispo) ont changé.

- [ ] **Step 5 : Lint + types + commit**

```bash
cd worker && uv run ruff check . && uv run mypy src/
git add worker/src/garmin_sync/coach/planner.py worker/tests/coach/test_planner.py
git commit -m "feat(coach): cap training days, assign sports and clamp durations in plan"
```

---

## Task 8 : Validation post-LLM par plafonds absolus

**Files:**
- Modify: `worker/src/garmin_sync/coach/workout_schema.py`
- Test: `worker/tests/coach/test_workout_schema.py`

`validate_workout_for_session` reçoit déjà `session` (donc `session_type`). On remplace le plancher relatif unique par : plancher de durée absolu par type + plafonds échauffement/RAC + plancher corps par type.

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
# (ajouter à worker/tests/coach/test_workout_schema.py)
import pytest
from garmin_sync.coach.workout_schema import (
    Workout,
    validate_workout_for_session,
    structure_caps_for_type,
)


def _block(dur_s, zone="Z2", rpe=4):
    return {"duration_s": dur_s, "target": {"label": zone, "rpe": rpe}}


def test_structure_caps_endurance():
    caps = structure_caps_for_type("endurance")
    assert caps.warmup_max_s == 15 * 60
    assert caps.cooldown_max_s == 10 * 60
    assert caps.main_min_ratio == 0.80


def test_long_session_rejects_huge_warmup():
    # endurance 2h avec 30min d'échauffement -> rejet (plafond 15min)
    wk = Workout(
        warmup=_block(30 * 60),
        main=[_block(80 * 60)],
        cooldown=_block(10 * 60),
        summary_md="x",
    )
    with pytest.raises(ValueError, match="warmup"):
        validate_workout_for_session(wk, {"target_duration_s": 120 * 60, "session_type": "endurance"})


def test_absolute_floor_rejects_too_short_endurance():
    wk = Workout(warmup=_block(60), main=[_block(15 * 60)], cooldown=_block(60), summary_md="x")
    with pytest.raises(ValueError, match="too short"):
        validate_workout_for_session(wk, {"target_duration_s": 17 * 60, "session_type": "endurance"})
```

- [ ] **Step 2 : Lancer (échec attendu)**

Run: `cd worker && uv run pytest tests/coach/test_workout_schema.py -k "caps or warmup or floor" -v`
Expected: FAIL (`structure_caps_for_type` inexistante ; pas de plafonds).

- [ ] **Step 3 : Implémenter**

Remplacer le validateur `_check_realistic_structure` par une version sans le seuil fixe 0.55 (le ratio devient type-dépendant, donc déplacé dans `validate_workout_for_session`). Garder juste la garde « main non vide / total positif » :

```python
    @model_validator(mode="after")
    def _check_non_empty(self) -> Workout:
        if not self.main:
            raise ValueError("workout must contain at least one main block")
        if self.total_duration_s() <= 0:
            raise ValueError("workout total duration must be positive")
        return self
```

Ajouter en bas du fichier :

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class StructureCaps:
    warmup_max_s: int
    cooldown_max_s: int
    main_min_ratio: float
    floor_s: int


_CAPS_BY_TYPE: dict[str, StructureCaps] = {
    "recovery": StructureCaps(5 * 60, 5 * 60, 0.90, 20 * 60),
    "endurance": StructureCaps(15 * 60, 10 * 60, 0.80, 30 * 60),
    "long": StructureCaps(15 * 60, 10 * 60, 0.80, 50 * 60),
    "threshold": StructureCaps(20 * 60, 15 * 60, 0.60, 40 * 60),
    "intervals": StructureCaps(25 * 60, 15 * 60, 0.50, 40 * 60),
}
_DEFAULT_CAPS = StructureCaps(20 * 60, 15 * 60, 0.55, 25 * 60)


def structure_caps_for_type(session_type: str) -> StructureCaps:
    return _CAPS_BY_TYPE.get(session_type, _DEFAULT_CAPS)
```

Réécrire `validate_workout_for_session` :

```python
def validate_workout_for_session(workout: Workout, session: dict[str, object]) -> Workout:
    """Validate a generated workout against the planned session envelope."""
    target_duration = session.get("target_duration_s")
    if not isinstance(target_duration, int) or target_duration <= 0:
        raise ValueError("workout generation requires a positive target duration")

    stype = str(session.get("session_type") or "endurance")
    caps = structure_caps_for_type(stype)
    total = workout.total_duration_s()

    if total < caps.floor_s:
        raise ValueError(f"workout duration {total}s is too short for {stype} (floor {caps.floor_s}s)")
    if workout.warmup.duration_s > caps.warmup_max_s:
        raise ValueError(f"warmup {workout.warmup.duration_s}s exceeds cap {caps.warmup_max_s}s")
    if workout.cooldown.duration_s > caps.cooldown_max_s:
        raise ValueError(f"cooldown {workout.cooldown.duration_s}s exceeds cap {caps.cooldown_max_s}s")
    if workout.main_duration_s() / total < caps.main_min_ratio:
        raise ValueError(f"main work below {caps.main_min_ratio:.0%} for {stype}")

    tolerance_s = max(300, round(target_duration * 0.10))
    if abs(total - target_duration) > tolerance_s:
        raise ValueError(f"workout duration {total}s is too far from target {target_duration}s")
    return workout
```

- [ ] **Step 4 : Lancer (succès attendu)**

Run: `cd worker && uv run pytest tests/coach/test_workout_schema.py -v`
Expected: PASS. Adapter les tests existants qui s'appuyaient sur le message « at least 55% » (le ratio est désormais par type).

- [ ] **Step 5 : Commit**

```bash
git add worker/src/garmin_sync/coach/workout_schema.py worker/tests/coach/test_workout_schema.py
git commit -m "feat(coach): validate workouts with type-based caps and duration floor"
```

---

## Task 9 : Consigne d'intensité par niveau dans le prompt LLM

**Files:**
- Modify: `worker/src/garmin_sync/coach/openai_client.py`
- Test: `worker/tests/coach/test_openai_client.py`

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# (ajouter à worker/tests/coach/test_openai_client.py)
from garmin_sync.coach.openai_client import _athlete_lines


def test_athlete_lines_warns_low_level_intensity():
    lines = _athlete_lines({"sports_strengths": {"swim": 1, "bike": 3, "run": 2}})
    text = "\n".join(lines)
    assert "1-5" in text
    # consigne ajoutée pour brider l'intensité des disciplines faibles
    assert "intensité" in text.lower()
```

- [ ] **Step 2 : Lancer (échec attendu)**

Run: `cd worker && uv run pytest tests/coach/test_openai_client.py -k intensity -v`
Expected: FAIL (pas de consigne intensité).

- [ ] **Step 3 : Modifier `_athlete_lines`**

Après la ligne qui ajoute `- Niveau (1-5) : swim=..., bike=..., run=...` (ligne ~67), ajouter une consigne conditionnelle :

```python
        weak = [s for s in ("swim", "bike", "run") if int(strengths.get(s, 3)) <= 2]
        if weak:
            lines.append(
                "- Consigne intensité : pour les disciplines faibles "
                f"({', '.join(weak)}), privilégie l'endurance et la technique, "
                "limite l'intensité (pas d'intervalles seuil durs)."
            )
```

> Adapter le nom de la variable locale (`strengths`) à celui utilisé dans la fonction. Si la fonction lit `athlete.get("sports_strengths")`, définir `strengths = athlete.get("sports_strengths") or {}` en amont.

- [ ] **Step 4 : Lancer (succès attendu)**

Run: `cd worker && uv run pytest tests/coach/test_openai_client.py -v`
Expected: PASS.

- [ ] **Step 5 : Commit**

```bash
git add worker/src/garmin_sync/coach/openai_client.py worker/tests/coach/test_openai_client.py
git commit -m "feat(coach): instruct LLM to cap intensity for weak disciplines"
```

---

## Task 10 : Flag `is_rest_day` dans le briefing

**Files:**
- Modify: `worker/src/garmin_sync/coach/briefing.py` (`DailyBriefing.to_dict`, `compute_briefing`)
- Test: `worker/tests/coach/test_briefing.py`

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# (ajouter à worker/tests/coach/test_briefing.py)
def test_briefing_to_dict_exposes_is_rest_day():
    # construire un DailyBriefing minimal avec suggested_session de type rest
    from garmin_sync.coach.briefing import DailyBriefing  # + autres imports nécessaires
    # ... monter un briefing avec planned session_type="rest"
    # assert payload["is_rest_day"] is True
```

> Note : compléter ce test en s'appuyant sur les fixtures existantes de `test_briefing.py`
> (réutiliser le builder de `DailyBriefing` déjà présent dans le fichier de test).

- [ ] **Step 2 : Lancer (échec attendu)**

Run: `cd worker && uv run pytest tests/coach/test_briefing.py -k rest_day -v`
Expected: FAIL (`is_rest_day` absent du payload).

- [ ] **Step 3 : Ajouter le flag**

Dans la dataclass `DailyBriefing` (vers ligne 107), ajouter un champ `is_rest_day: bool = False`. Dans `to_dict` (ligne 122+), ajouter `"is_rest_day": self.is_rest_day,`. Dans `compute_briefing` (retour ligne 768), calculer la valeur depuis la séance planifiée du jour :

```python
    planned_today = _load_planned_session(db, user_id, today)
    is_rest_day = str((planned_today or {}).get("session_type") or "") == "rest"
    return DailyBriefing(
        ...,
        is_rest_day=is_rest_day,
    )
```

> Vérifier le nom exact de la variable de séance planifiée déjà chargée dans `compute_briefing` (réutiliser l'existante plutôt que recharger).

- [ ] **Step 4 : Lancer (succès attendu)**

Run: `cd worker && uv run pytest tests/coach/test_briefing.py -v`
Expected: PASS.

- [ ] **Step 5 : Commit**

```bash
git add worker/src/garmin_sync/coach/briefing.py worker/tests/coach/test_briefing.py
git commit -m "feat(coach): expose is_rest_day flag in daily briefing payload"
```

---

## Task 11 : Module front `duration-preview.ts` (miroir)

**Files:**
- Create: `lib/coach/duration-preview.ts`
- Test: `tests/unit/lib/coach/duration-preview.test.ts`

- [ ] **Step 1 : Écrire le test qui échoue**

```typescript
// tests/unit/lib/coach/duration-preview.test.ts
import { describe, expect, it } from 'vitest'
import { previewPlan, trainingDaysCount } from '@/lib/coach/duration-preview'

describe('duration-preview', () => {
  it('caps training days for 7 available / 8h intermediate', () => {
    expect(
      trainingDaysCount({ nAvailable: 7, hours: 8, strengths: { swim: 3, bike: 3, run: 3 } })
    ).toBe(5)
  })

  it('previews bike endurance within realistic bounds', () => {
    const p = previewPlan({
      nAvailable: 4,
      hours: 8,
      strengths: { swim: 2, bike: 4, run: 2 },
    })
    expect(p.trainingDays).toBe(5 > 4 ? 4 : 5) // capé par nAvailable=4
    const bike = p.disciplines.find((d) => d.sport === 'bike')!
    expect(bike.enduranceMinLabel).toContain('h')
  })

  it('reports rest days', () => {
    const p = previewPlan({ nAvailable: 7, hours: 8, strengths: { swim: 3, bike: 3, run: 3 } })
    expect(p.restDays).toBeGreaterThanOrEqual(1)
  })
})
```

- [ ] **Step 2 : Lancer (échec attendu)**

Run: `pnpm test tests/unit/lib/coach/duration-preview.test.ts`
Expected: FAIL (module inexistant).

- [ ] **Step 3 : Implémenter le module (miroir du worker)**

```typescript
// lib/coach/duration-preview.ts
// MIROIR du worker : garde ces tables alignées avec
// worker/src/garmin_sync/coach/{training_days,duration_bounds}.py.

export type Strengths = { swim: number; bike: number; run: number }
type Level = 'beginner' | 'intermediate' | 'advanced'

export function athleteLevel(s: Strengths): Level {
  const mean = (s.swim + s.bike + s.run) / 3
  if (mean < 2.5) return 'beginner'
  if (mean < 3.75) return 'intermediate'
  return 'advanced'
}

function capVolume(hours: number): number {
  if (hours < 5) return 4
  if (hours < 7) return 5
  return 6
}

const CAP_NIVEAU: Record<Level, number> = { beginner: 4, intermediate: 5, advanced: 6 }
const REPOS_LEVEL: Record<Level, number> = { beginner: 2, intermediate: 1, advanced: 1 }

export function trainingDaysCount(args: {
  nAvailable: number
  hours: number
  strengths: Strengths
}): number {
  const level = athleteLevel(args.strengths)
  const reposMin = REPOS_LEVEL[level]
  return Math.max(
    0,
    Math.min(args.nAvailable, capVolume(args.hours), CAP_NIVEAU[level], 7 - reposMin)
  )
}

// Bornes endurance (minutes) en phase "base", miroir partiel de duration_bounds.py.
const ENDURANCE_BOUNDS_MIN: Record<keyof Strengths, [number, number]> = {
  bike: [90, 180],
  run: [40, 60],
  swim: [45, 60],
}

function fmt(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  if (h === 0) return `${m}min`
  return m === 0 ? `${h}h` : `${h}h${String(m).padStart(2, '0')}`
}

export type DisciplinePreview = {
  sport: keyof Strengths
  enduranceMinLabel: string
}

export function previewPlan(args: { nAvailable: number; hours: number; strengths: Strengths }) {
  const trainingDays = trainingDaysCount(args)
  const restDays = Math.max(0, args.nAvailable - trainingDays) + (7 - args.nAvailable)
  const disciplines: DisciplinePreview[] = (['swim', 'bike', 'run'] as const).map((sport) => {
    const [lo, hi] = ENDURANCE_BOUNDS_MIN[sport]
    const level = args.strengths[sport]
    // niveau faible -> bas de fourchette ; fort -> haut de fourchette
    const ratio = (level - 1) / 4
    const low = Math.round(lo + (hi - lo) * Math.max(0, ratio - 0.15))
    const high = Math.round(lo + (hi - lo) * Math.min(1, ratio + 0.15))
    return { sport, enduranceMinLabel: `${fmt(low)}–${fmt(high)}` }
  })
  return { trainingDays, restDays, disciplines }
}
```

- [ ] **Step 4 : Lancer (succès attendu)**

Run: `pnpm test tests/unit/lib/coach/duration-preview.test.ts`
Expected: PASS.

- [ ] **Step 5 : Commit**

```bash
git add lib/coach/duration-preview.ts tests/unit/lib/coach/duration-preview.test.ts
git commit -m "feat(coach): add client duration preview mirror module"
```

---

## Task 12 : Encart aperçu live sur les formulaires dispo

**Files:**
- Modify: `app/(app)/profile/_components/dispo-edit-form.tsx`
- Modify: `app/(app)/onboarding/_components/step-dispo-form.tsx`

- [ ] **Step 1 : Ajouter l'encart dans `dispo-edit-form.tsx`**

Importer en tête :

```typescript
import { previewPlan } from '@/lib/coach/duration-preview'
```

Dans le rendu du mode édition (avant les boutons, après le `<fieldset>`), insérer :

```tsx
{(() => {
  const hoursNum = hours ? Number.parseInt(hours, 10) : 0
  const nAvailable = days.length || 0
  if (!hoursNum || !nAvailable) return null
  const p = previewPlan({ nAvailable, hours: hoursNum, strengths: { swim, bike, run } })
  const icon: Record<string, string> = { swim: '🏊', bike: '🚴', run: '🏃' }
  return (
    <div className="bg-muted/40 space-y-1 rounded-md border p-3 text-sm">
      <p className="font-medium">Aperçu de tes séances types</p>
      <p className="text-muted-foreground text-xs">
        Tu te déclares dispo {nAvailable} jour(s) ; je programme {p.trainingDays} séance(s) +{' '}
        {p.restDays} repos.
      </p>
      <ul className="text-muted-foreground space-y-0.5 text-xs">
        {p.disciplines.map((d) => (
          <li key={d.sport}>
            {icon[d.sport]} {d.sport} endurance ~{d.enduranceMinLabel}
          </li>
        ))}
      </ul>
    </div>
  )
})()}
```

- [ ] **Step 2 : Vérifier le rendu**

Run: `pnpm lint && pnpm typecheck`
Expected: pas d'erreur.

- [ ] **Step 3 : Reproduire l'encart dans `step-dispo-form.tsx`**

Lire d'abord le fichier (`app/(app)/onboarding/_components/step-dispo-form.tsx`) pour repérer les noms d'états (`swim/bike/run`, jours, heures), puis insérer le même bloc d'aperçu juste avant le bouton de soumission, en adaptant les noms de variables locales.

- [ ] **Step 4 : Vérifier**

Run: `pnpm lint && pnpm typecheck && pnpm build`
Expected: build OK.

- [ ] **Step 5 : Commit**

```bash
git add app/\(app\)/profile/_components/dispo-edit-form.tsx app/\(app\)/onboarding/_components/step-dispo-form.tsx
git commit -m "feat(profile): live session-duration preview on availability forms"
```

---

## Task 13 : Repos = repos sur `/today`

**Files:**
- Modify: `app/(app)/today/page.tsx`

But : quand le briefing renvoie `is_rest_day`, ne pas afficher les blocs orientés séance (recommandation coach, feedback dernière séance, ajustement prochaine séance) ; afficher un message de récupération. Les métriques de récup restent visibles.

- [ ] **Step 1 : Lire la zone de rendu du briefing**

Lire `app/(app)/today/page.tsx` (au-delà de la ligne 134) pour repérer où `briefingResult`/`briefing` est rendu et quels composants affichent `coach_recommendation` / `last_session_feedback` / `next_session_adjustment`.

- [ ] **Step 2 : Conditionner l'affichage**

Récupérer le flag (le payload briefing est un objet ; ajouter au type côté front si typé) :

```tsx
const isRestDay = Boolean((briefing as { is_rest_day?: boolean } | null)?.is_rest_day)
```

Envelopper les blocs orientés séance dans `{!isRestDay && ( ... )}`, et ajouter pour le repos :

```tsx
{isRestDay && (
  <div className="rounded-lg border p-4 text-sm">
    <p className="font-medium">Jour de repos 🛌</p>
    <p className="text-muted-foreground">
      Pas de séance aujourd'hui. La récupération fait partie de l'entraînement :
      c'est là que ton corps assimile la charge. Écoute tes sensations et reviens frais demain.
    </p>
  </div>
)}
```

> La section séance (`renderSessionSection`) gère déjà l'empty state repos ; ne pas la dupliquer. Conserver l'affichage des métriques récup (HRV, sommeil, Body Battery) hors de la condition.

- [ ] **Step 3 : Vérifier**

Run: `pnpm lint && pnpm typecheck && pnpm build`
Expected: build OK.

- [ ] **Step 4 : Commit**

```bash
git add app/\(app\)/today/page.tsx
git commit -m "feat(today): show recovery message and hide session blocks on rest days"
```

---

## Task 14 : Vérification finale + non-régression

**Files:** (aucune modif, vérification)

- [ ] **Step 1 : Suite worker complète**

Run: `cd worker && uv run pytest -v`
Expected: tous verts. Corriger toute régression résiduelle (tests qui assument l'ancienne assignation sport par modulo, anciennes durées, ancien message 55%).

- [ ] **Step 2 : Lint + types worker**

Run: `cd worker && uv run ruff check . && uv run mypy src/`
Expected: clean.

- [ ] **Step 3 : Suite frontend**

Run: `pnpm test && pnpm lint && pnpm typecheck && pnpm build`
Expected: tous verts.

- [ ] **Step 4 : Vérifier la couverture**

S'assurer que les nouveaux modules (`duration_bounds.py`, `training_days.py`, `duration-preview.ts`) sont couverts (fonctions pures → viser 100%). Le gate SonarQube exige 95% sur le code neuf.

- [ ] **Step 5 : Commit éventuel des ajustements de tests**

```bash
git add -A
git commit -m "test(coach): fix regressions from E13 plan engine changes"
```

---

## Self-Review — couverture du spec

| Exigence spec | Tâche(s) |
|---|---|
| E13.1 correction `weekly_tss = ctl × 7` | Task 6 (plancher heures) + Task 7 |
| E13.1 recalage `_TSS_PER_HOUR` | Task 6 |
| E13.1 table de bornes + clamp | Task 1 + Task 7 |
| E13.1 plafonds échauffement/RAC + plancher corps | Task 8 |
| E13.2 modulation volume continue 1-5 | Task 4 |
| E13.2 filtrage intensité/types par niveau | Task 5 (+ Task 9 prompt) |
| E13.4 repos = repos (flag + UI) | Task 10 + Task 13 |
| E13.5 aperçu live durées | Task 11 + Task 12 |
| E13.6 conversion dispo→entraînement + plancher repos | Task 2 + Task 7 |
| E13.6 cap course + no back-to-back | Task 3 + Task 7 |
| Tests & non-régression | toutes + Task 14 |

Aucune exigence du spec sans tâche associée.
```
