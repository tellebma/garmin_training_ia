# Workout Envelope Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Éliminer les échecs prod `OpenAIError — unrealistic workout` en rendant l'enveloppe de validation des workouts mathématiquement satisfiable, en donnant au retry LLM la réponse précédente, et en ajoutant un backoff anti-spam sur les sessions en échec.

**Architecture:** Le worker Python (`worker/src/garmin_sync/coach/`) génère des séances via OpenAI structured outputs puis les valide contre une enveloppe numérique. Bug racine : les caps warmup/cooldown annoncés au LLM (fixes par type) sont incompatibles avec le ratio `main_min_ratio` exigé pour les durées cibles réelles (ex. endurance 60 min : caps annoncés 15+10 min mais ratio 80 % impose ≤ 12 min au total). On introduit une `SessionEnvelope` unique, calculée depuis la cible, consommée à la fois par le prompt et par la validation — cohérence garantie par construction. En plus : le retry ré-injecte la réponse assistant fautive, le system prompt ne contredit plus l'enveloppe (55 % codé en dur), et les sessions en échec récent sont différées 6 h.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, uv, Supabase Postgres (migration SQL).

## Global Constraints

- Répertoire de travail worker : `worker/` — toutes les commandes `uv run ...` se lancent depuis `worker/`.
- Quality gates avant chaque commit : `uv run ruff format . && uv run ruff check . && uv run mypy src/` (piège connu : ruff format DOIT passer, Sonar exige new_violations=0).
- Conventional Commits stricts, body lines ≤ 100 chars.
- Ne PAS modifier `lib/coach/workout-types.ts` (le schéma Workout lui-même ne change pas, seules les bornes de validation changent).
- Les messages d'erreur de validation gardent leurs formats existants (`main work below X%`, `exceeds cap`, `too far from target`, `too short`) — ils sont parsés nulle part mais loggés/alertés, on garde la continuité.
- Migration SQL : fichier `supabase/migrations/20260703000000_workout_generation_backoff.sql` (auto-appliquée par CI au merge sur main — E17).

## Contexte numérique (pour comprendre les valeurs de test)

Formules de l'enveloppe effective (Task 1) :

```
tol       = max(300, round(target * 0.10))
min_total = max(floor_s, target - tol)
budget    = int((1 - main_min_ratio) * min_total)      # budget total warmup+cooldown
warmup_max_eff   = min(warmup_cap_fixe,   int(budget * 0.6))
cooldown_max_eff = min(cooldown_cap_fixe, budget - warmup_max_eff)
```

Ratios ajustés : recovery 0.90 → **0.80**, endurance 0.80 → **0.75** (long/threshold/intervals/default inchangés : 0.80/0.60/0.50/0.55).

Valeurs de référence :

| session | target | tol | min_total | budget | warmup_eff | cooldown_eff |
|---|---|---|---|---|---|---|
| endurance | 3600 | 360 | 3240 | 810 | 486 | 324 |
| recovery | 2400 | 300 | 2100 | 419 | 251 | 168 |
| threshold | 3600 | 360 | 3240 | 1296 | 777 | 519 |
| endurance | 14400 | 1440 | 12960 | 3240 | 900 (cap fixe) | 600 (cap fixe) |

---

### Task 1: SessionEnvelope cohérente (workout_schema.py)

**Files:**
- Modify: `worker/src/garmin_sync/coach/workout_schema.py:80-156`
- Test: `worker/tests/coach/test_workout_schema.py`
- Test (fixtures impactées): `worker/tests/coach/test_openai_client.py`

**Interfaces:**
- Consumes: `StructureCaps`, `structure_caps_for_type`, `duration_tolerance_s` (existants, conservés).
- Produces: `SessionEnvelope` (dataclass frozen : `session_type: str`, `target_s: int`, `tolerance_s: int`, `floor_s: int`, `warmup_max_s: int`, `cooldown_max_s: int`, `main_min_ratio: float`) et `envelope_for_session(session: dict[str, object]) -> SessionEnvelope`. `describe_session_envelope` et `validate_workout_for_session` gardent leurs signatures publiques.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `worker/tests/coach/test_workout_schema.py`, ajouter l'import `envelope_for_session` à l'import existant depuis `garmin_sync.coach.workout_schema`, puis ajouter en fin de fichier :

```python
def test_envelope_for_session_endurance_effective_caps():
    env = envelope_for_session({"session_type": "endurance", "target_duration_s": 3600})
    # budget = int(0.25 * (3600 - 360)) = 810 ; warmup = int(810 * 0.6) = 486 ; cooldown = 324
    assert env.warmup_max_s == 486
    assert env.cooldown_max_s == 324
    assert env.main_min_ratio == 0.75
    assert env.tolerance_s == 360


def test_envelope_caps_bounded_by_fixed_type_caps():
    # Séance très longue : le budget dépasse les caps fixes, qui restent la borne.
    env = envelope_for_session({"session_type": "endurance", "target_duration_s": 14400})
    assert env.warmup_max_s == 900
    assert env.cooldown_max_s == 600


@pytest.mark.parametrize(
    ("session_type", "target_s"),
    [
        ("recovery", 2400),
        ("endurance", 3600),
        ("endurance", 2700),
        ("long", 7200),
        ("threshold", 3600),
        ("intervals", 3600),
        ("unknown", 3000),
    ],
)
def test_workout_following_announced_caps_passes_validation(session_type, target_s):
    """Anti-régression bug prod 2026-07-03 : un workout qui suit exactement les bornes
    annoncées au LLM (warmup/cooldown au max, total = cible) doit passer la validation."""
    session = {"session_type": session_type, "target_duration_s": target_s}
    env = envelope_for_session(session)
    workout = Workout(
        warmup=_block(env.warmup_max_s, "Z1", 2),
        main=[_block(target_s - env.warmup_max_s - env.cooldown_max_s)],
        cooldown=_block(env.cooldown_max_s, "Z1", 2),
        summary_md="x",
    )
    assert validate_workout_for_session(workout, session) is workout


def test_envelope_prompt_announces_combined_budget():
    text = describe_session_envelope({"session_type": "endurance", "target_duration_s": 3600})
    assert "8min" in text  # warmup 486s -> 8min
    assert "5min" in text  # cooldown 324s -> 5min
    assert "13min au total" in text  # budget combiné 810s -> 13min
    assert "75%" in text
```

Note : `_block` (helper dict existant ligne 145) et `pytest` sont déjà présents dans ce fichier.

- [ ] **Step 2: Vérifier que les nouveaux tests échouent**

Run: `cd worker && uv run pytest tests/coach/test_workout_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'envelope_for_session'`

- [ ] **Step 3: Implémenter SessionEnvelope dans workout_schema.py**

Remplacer les lignes 88-156 de `worker/src/garmin_sync/coach/workout_schema.py` (de `_CAPS_BY_TYPE` jusqu'à la fin du fichier) par :

```python
_CAPS_BY_TYPE: dict[str, StructureCaps] = {
    "recovery": StructureCaps(5 * 60, 5 * 60, 0.80, 20 * 60),
    "endurance": StructureCaps(15 * 60, 10 * 60, 0.75, 30 * 60),
    "long": StructureCaps(15 * 60, 10 * 60, 0.80, 50 * 60),
    "threshold": StructureCaps(20 * 60, 15 * 60, 0.60, 40 * 60),
    "intervals": StructureCaps(25 * 60, 15 * 60, 0.50, 40 * 60),
}
_DEFAULT_CAPS = StructureCaps(20 * 60, 15 * 60, 0.55, 25 * 60)

# Part du budget warmup+cooldown allouée au warmup (le reste va au cooldown).
_WARMUP_BUDGET_SHARE = 0.6


def structure_caps_for_type(session_type: str) -> StructureCaps:
    return _CAPS_BY_TYPE.get(session_type, _DEFAULT_CAPS)


def duration_tolerance_s(target_duration_s: int) -> int:
    """Allowed deviation between generated total and the planned target."""
    return max(300, round(target_duration_s * 0.10))


@dataclass(frozen=True)
class SessionEnvelope:
    """Bornes effectives d'une séance, cohérentes entre prompt LLM et validation.

    Les caps warmup/cooldown sont dérivés du budget (1 - main_min_ratio) calculé
    sur la durée totale MINIMALE acceptée : un workout qui respecte ces caps et la
    fenêtre de durée satisfait mécaniquement le ratio de corps de séance.
    """

    session_type: str
    target_s: int
    tolerance_s: int
    floor_s: int
    warmup_max_s: int
    cooldown_max_s: int
    main_min_ratio: float


def envelope_for_session(session: dict[str, object]) -> SessionEnvelope:
    stype = str(session.get("session_type") or "endurance")
    caps = structure_caps_for_type(stype)
    target = session.get("target_duration_s")
    target_s = target if isinstance(target, int) and target > 0 else 0
    tol = duration_tolerance_s(target_s)
    min_total = max(caps.floor_s, target_s - tol)
    budget_s = int((1 - caps.main_min_ratio) * min_total)
    warmup_max = min(caps.warmup_max_s, int(budget_s * _WARMUP_BUDGET_SHARE))
    cooldown_max = min(caps.cooldown_max_s, budget_s - warmup_max)
    return SessionEnvelope(
        session_type=stype,
        target_s=target_s,
        tolerance_s=tol,
        floor_s=caps.floor_s,
        warmup_max_s=warmup_max,
        cooldown_max_s=cooldown_max,
        main_min_ratio=caps.main_min_ratio,
    )


def describe_session_envelope(session: dict[str, object]) -> str:
    """Human-readable numeric envelope the workout MUST satisfy, for the LLM prompt.

    Construit depuis `envelope_for_session`, la même source que
    `validate_workout_for_session` : le modèle voit exactement les bornes contre
    lesquelles il sera vérifié.
    """
    env = envelope_for_session(session)
    lo_min = max(0, env.target_s - env.tolerance_s) // 60
    hi_min = (env.target_s + env.tolerance_s) // 60
    combined_min = (env.warmup_max_s + env.cooldown_max_s) // 60
    return (
        "Contraintes chiffrées à respecter impérativement (la séance sera rejetée sinon) :\n"
        f"- Durée totale entre {lo_min}min et {hi_min}min (cible {env.target_s // 60}min).\n"
        f"- Échauffement (warmup) ≤ {env.warmup_max_s // 60}min.\n"
        f"- Retour au calme (cooldown) ≤ {env.cooldown_max_s // 60}min.\n"
        f"- Échauffement + retour au calme ≤ {combined_min}min au total.\n"
        f"- Le corps de séance (main) doit représenter ≥ {env.main_min_ratio:.0%} "
        "de la durée totale."
    )


def validate_workout_for_session(workout: Workout, session: dict[str, object]) -> Workout:
    """Validate a generated workout against the planned session envelope."""
    target_duration = session.get("target_duration_s")
    if not isinstance(target_duration, int) or target_duration <= 0:
        raise ValueError("workout generation requires a positive target duration")

    env = envelope_for_session(session)
    total = workout.total_duration_s()

    if total < env.floor_s:
        raise ValueError(
            f"workout duration {total}s is too short for {env.session_type} "
            f"(floor {env.floor_s}s)"
        )
    if workout.warmup.duration_s > env.warmup_max_s:
        raise ValueError(f"warmup {workout.warmup.duration_s}s exceeds cap {env.warmup_max_s}s")
    if workout.cooldown.duration_s > env.cooldown_max_s:
        raise ValueError(
            f"cooldown {workout.cooldown.duration_s}s exceeds cap {env.cooldown_max_s}s"
        )
    if workout.main_duration_s() / total < env.main_min_ratio:
        raise ValueError(f"main work below {env.main_min_ratio:.0%} for {env.session_type}")
    if abs(total - env.target_s) > env.tolerance_s:
        raise ValueError(f"workout duration {total}s is too far from target {env.target_s}s")
    return workout
```

(`StructureCaps` lignes 80-86 et tout ce qui précède restent inchangés.)

- [ ] **Step 4: Mettre à jour les tests existants cassés par les nouvelles bornes**

Dans `worker/tests/coach/test_workout_schema.py` :

Remplacer `test_describe_session_envelope_states_numeric_bounds` par :

```python
def test_describe_session_envelope_states_numeric_bounds():
    text = describe_session_envelope({"session_type": "endurance", "target_duration_s": 3600})
    # warmup eff 486s, cooldown eff 324s, main >= 75%, fenêtre 54-66 min (±10%)
    assert "8min" in text
    assert "5min" in text
    assert "75%" in text
    assert "54" in text
    assert "66" in text
```

Remplacer `test_describe_session_envelope_recovery_tighter_caps` par :

```python
def test_describe_session_envelope_recovery_tighter_caps():
    # recovery 2400s : budget int(0.2*2100)=419 ; warmup int(419*0.6)=251 -> 4min ; cooldown 168 -> 2min
    text = describe_session_envelope({"session_type": "recovery", "target_duration_s": 2400})
    assert "4min" in text
    assert "2min" in text
    assert "80%" in text
```

Dans `test_structure_caps_endurance`, remplacer `assert caps.main_min_ratio == 0.80` par `assert caps.main_min_ratio == 0.75`.

Dans `worker/tests/coach/test_openai_client.py` (fixtures devenues invalides avec les caps effectifs) :

1. `test_generate_workout_returns_validated_workout` (session threshold 3600s : cooldown eff = 519s) : remplacer le dict `"cooldown"` (duration_s 600) par duration_s **480** (les autres champs du bloc inchangés).
2. `test_prompt_includes_race_context` et `test_prompt_includes_activity_review_context` (même session threshold) : dans le `parsed`, remplacer `"main": [{"duration_s": 2400, ...}]` par `2520` et `"cooldown": {"duration_s": 600, ...}` par `480` (total 600+2520+480=3600, ratio 0.70 ≥ 0.60).
3. `test_prompt_includes_numeric_envelope` : remplacer `_workout_dict(360, 2880, 360)` par `_workout_dict(300, 3000, 300)` et `assert "80%" in user_msg` par `assert "75%" in user_msg`.
4. `test_generate_workout_retries_with_feedback_then_succeeds` : remplacer `valid = _workout_dict(360, 2880, 360)` par `valid = _workout_dict(300, 3000, 300)` et `assert workout.warmup.duration_s == 360` par `== 300`.

- [ ] **Step 5: Lancer la suite complète du worker**

Run: `cd worker && uv run pytest -v`
Expected: PASS (tous). Si un autre test utilise des fixtures de workout devenues hors bornes, ajuster la fixture selon la même logique (warmup/cooldown sous les caps effectifs de la table de référence).

- [ ] **Step 6: Quality gates + commit**

```bash
cd worker && uv run ruff format . && uv run ruff check . && uv run mypy src/
git add worker/src/garmin_sync/coach/workout_schema.py worker/tests/coach/test_workout_schema.py worker/tests/coach/test_openai_client.py
git commit -m "fix(coach): make workout envelope self-consistent between prompt and validation

Les caps warmup/cooldown fixes annoncés au LLM étaient incompatibles avec
main_min_ratio pour les durées réelles (endurance 60min, recovery 40min),
rendant la validation quasi insatisfiable. SessionEnvelope dérive désormais
des caps effectifs du budget (1-ratio) — cohérence par construction.
Ratios assouplis : recovery 0.90->0.80, endurance 0.80->0.75."
```

---

### Task 2: Retry LLM avec réponse assistant + system prompt aligné (openai_client.py)

**Files:**
- Modify: `worker/src/garmin_sync/coach/openai_client.py`
- Test: `worker/tests/coach/test_openai_client.py`

**Interfaces:**
- Consumes: `validate_workout_for_session`, `describe_session_envelope` (Task 1, signatures inchangées).
- Produces: `OpenAIError.__init__(self, message: str, raw_payload: str | None = None)` avec attribut `self.raw_payload`. Signature de `generate_workout_for_session` inchangée.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `worker/tests/coach/test_openai_client.py`, ajouter après `test_generate_workout_retries_with_feedback_then_succeeds` :

```python
@patch("garmin_sync.coach.openai_client._get_client")
def test_retry_feeds_previous_assistant_response(mock_get_client):
    """Le retry doit inclure la réponse assistant fautive : sans elle, le message
    'la séance précédente est invalide' réfère à un contenu que le modèle ne voit pas."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    invalid = _workout_dict(1800, 1500, 300)
    valid = _workout_dict(300, 3000, 300)
    mock_client.beta.chat.completions.parse.side_effect = [_resp(invalid), _resp(valid)]

    generate_workout_for_session(
        session=_endurance_session(), athlete=_athlete_full(), race_context=_race_context()
    )

    retry_messages = mock_client.beta.chat.completions.parse.call_args_list[1].kwargs["messages"]
    roles = [m["role"] for m in retry_messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert "1800" in retry_messages[2]["content"]  # le workout fautif complet est visible


@patch("garmin_sync.coach.openai_client._get_client")
def test_api_failure_retry_has_no_assistant_message(mock_get_client):
    """Un échec réseau (pas de payload) ne doit pas injecter de message assistant vide."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    valid = _workout_dict(300, 3000, 300)
    mock_client.beta.chat.completions.parse.side_effect = [Exception("boom"), _resp(valid)]

    generate_workout_for_session(
        session=_endurance_session(), athlete=_athlete_full(), race_context=_race_context()
    )

    retry_messages = mock_client.beta.chat.completions.parse.call_args_list[1].kwargs["messages"]
    assert [m["role"] for m in retry_messages] == ["system", "user", "user"]
```

Et dans `test_prompt_includes_race_context`, remplacer :

```python
    assert "au moins 55%" in system_msg
```

par :

```python
    assert "55%" not in system_msg  # plus de ratio codé en dur : l'enveloppe par séance fait foi
```

- [ ] **Step 2: Vérifier que les nouveaux tests échouent**

Run: `cd worker && uv run pytest tests/coach/test_openai_client.py -v`
Expected: FAIL — `test_retry_feeds_previous_assistant_response` (roles sans "assistant"), `test_prompt_includes_race_context` ("55%" encore présent). `test_api_failure_retry_has_no_assistant_message` peut déjà passer (comportement actuel) — c'est un garde-fou de non-régression pour l'implémentation.

- [ ] **Step 3: Implémenter dans openai_client.py**

Ajouter `import json` en tête de fichier (après `from functools import lru_cache`, ordre stdlib).

Remplacer la classe `OpenAIError` par :

```python
class OpenAIError(Exception):
    """Raised when the OpenAI API call or response is unusable.

    ``raw_payload`` porte le JSON du workout rejeté par la validation, pour
    ré-injection en message assistant lors du retry correctif.
    """

    def __init__(self, message: str, raw_payload: str | None = None) -> None:
        super().__init__(message)
        self.raw_payload = raw_payload
```

Dans `_SYSTEM_PROMPT`, remplacer la ligne :

```
- Le corps de séance doit représenter au moins 55% de la durée totale.
```

par :

```
- Le corps de séance doit respecter la part minimale de la durée totale donnée dans
  les contraintes chiffrées de la demande.
```

Dans `_call_and_validate`, remplacer le bloc final (à partir de `parsed = ...`) par :

```python
    parsed = resp.choices[0].message.parsed
    if parsed is None:
        raise OpenAIError("OpenAI returned no parsed payload")
    payload = parsed.model_dump()
    try:
        workout = Workout.model_validate(payload)
        return validate_workout_for_session(workout, session)
    except ValueError as e:
        raise OpenAIError(
            f"OpenAI returned unrealistic workout: {e}",
            raw_payload=json.dumps(payload, ensure_ascii=False),
        ) from e
```

Dans la boucle de `generate_workout_for_session`, remplacer le corps du `except OpenAIError as e:` par :

```python
        except OpenAIError as e:
            last_error = e
            if e.raw_payload:
                messages.append({"role": "assistant", "content": e.raw_payload})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"La séance précédente est invalide : {e}. "
                        "Corrige uniquement ce point en respectant les contraintes chiffrées "
                        "déjà fournies, et renvoie le workout complet."
                    ),
                }
            )
```

- [ ] **Step 4: Lancer les tests**

Run: `cd worker && uv run pytest tests/coach/test_openai_client.py tests/coach/test_workout_schema.py -v`
Expected: PASS (tous).

- [ ] **Step 5: Quality gates + commit**

```bash
cd worker && uv run ruff format . && uv run ruff check . && uv run mypy src/
git add worker/src/garmin_sync/coach/openai_client.py worker/tests/coach/test_openai_client.py
git commit -m "fix(coach): feed rejected workout back to LLM on retry, drop hardcoded 55% rule

Le message correctif référençait 'la séance précédente' sans jamais inclure
la réponse assistant dans l'historique : le modèle re-devinait à l'aveugle
et oscillait entre erreur de ratio et erreur de durée. Le JSON rejeté est
désormais ré-injecté en message assistant. Le system prompt ne contredit
plus l'enveloppe chiffrée par séance."
```

---

### Task 3: Backoff anti-spam sur les échecs de génération (sessions.py + migration)

**Files:**
- Create: `supabase/migrations/20260703000000_workout_generation_backoff.sql`
- Modify: `worker/src/garmin_sync/coach/sessions.py`
- Test: `worker/tests/coach/test_sessions.py`

**Interfaces:**
- Consumes: `generate_workout_for_session`, `OpenAIError` (Task 2).
- Produces: colonne DB `planned_sessions.workout_generation_failed_at timestamptz` ; `ensure_sessions` retourne désormais `{"generated_count", "failed_count", "skipped_count", "deferred_count"}` (clé ajoutée, endpoint FastAPI retourne `dict[str, Any]`, rien d'autre à changer côté API).

- [ ] **Step 1: Créer la migration SQL**

Créer `supabase/migrations/20260703000000_workout_generation_backoff.sql` :

```sql
-- Backoff anti-spam sur la génération LLM des séances :
-- une session dont la génération vient d'échouer est différée (6h côté worker)
-- au lieu d'être retentée à chaque appel d'ensure_sessions.
alter table public.planned_sessions
  add column if not exists workout_generation_failed_at timestamptz;

comment on column public.planned_sessions.workout_generation_failed_at is
  'Dernier échec de génération LLM du workout ; NULL si jamais échoué ou succès depuis. Le worker diffère la régénération pendant 6h après un échec.';
```

- [ ] **Step 2: Écrire les tests qui échouent**

Dans `worker/tests/coach/test_sessions.py`, ajouter en fin de fichier :

```python
def _pending_session(session_id: str = "s1", **overrides) -> dict:
    base = {
        "id": session_id,
        "sport": "run",
        "session_type": "endurance",
        "target_duration_s": 3000,
        "target_tss": 50,
        "phase": "base",
        "date": "2026-07-03",
        "workout_generation_failed_at": None,
    }
    return {**base, **overrides}


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_defers_recently_failed(mock_db, mock_gen):
    from datetime import UTC, datetime, timedelta

    db = MagicMock()
    mock_db.return_value = db
    recent_fail = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    _planned_select_chain(db).data = [
        _pending_session("s1", workout_generation_failed_at=recent_fail)
    ]

    result = ensure_sessions(user_id="u1", days=7)

    assert result["deferred_count"] == 1
    assert result["generated_count"] == 0
    mock_gen.assert_not_called()


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_retries_after_backoff_expiry(mock_db, mock_gen):
    from datetime import UTC, datetime, timedelta

    db = MagicMock()
    mock_db.return_value = db
    old_fail = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
    _planned_select_chain(db).data = [
        _pending_session("s1", workout_generation_failed_at=old_fail)
    ]
    _profile_chain(db).data = {"sports_strengths": {"swim": 3, "bike": 3, "run": 3}}
    _race_chain(db).data = None
    mock_gen.return_value = MagicMock(model_dump=lambda: _mock_workout())

    result = ensure_sessions(user_id="u1", days=7)

    assert result["generated_count"] == 1
    assert result["deferred_count"] == 0


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_generation_failure_marks_backoff(mock_db, mock_gen):
    from garmin_sync.coach.openai_client import OpenAIError

    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [_pending_session("s1")]
    _profile_chain(db).data = {"sports_strengths": {"swim": 3, "bike": 3, "run": 3}}
    _race_chain(db).data = None
    mock_gen.side_effect = OpenAIError("boom")

    result = ensure_sessions(user_id="u1", days=7)

    assert result["failed_count"] == 1
    update_payloads = [c.args[0] for c in db.table.return_value.update.call_args_list]
    assert any(
        isinstance(p.get("workout_generation_failed_at"), str) for p in update_payloads
    )


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_generation_success_resets_backoff(mock_db, mock_gen):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [_pending_session("s1")]
    _profile_chain(db).data = {"sports_strengths": {"swim": 3, "bike": 3, "run": 3}}
    _race_chain(db).data = None
    mock_gen.return_value = MagicMock(model_dump=lambda: _mock_workout())

    ensure_sessions(user_id="u1", days=7)

    update_payloads = [c.args[0] for c in db.table.return_value.update.call_args_list]
    success = next(p for p in update_payloads if "workout" in p)
    assert success["workout_generation_failed_at"] is None
```

Et mettre à jour les asserts d'égalité stricte des retours existants (la clé `deferred_count` s'ajoute) :

- `test_ensure_sessions_skips_already_generated` :
  `assert result == {"generated_count": 0, "failed_count": 0, "skipped_count": 0, "deferred_count": 0}`
- `test_ensure_sessions_skips_rest_days` :
  `assert result == {"generated_count": 0, "failed_count": 0, "skipped_count": 1, "deferred_count": 0}`

- [ ] **Step 3: Vérifier que les tests échouent**

Run: `cd worker && uv run pytest tests/coach/test_sessions.py -v`
Expected: FAIL — `KeyError: 'deferred_count'` (nouveaux tests + les 2 asserts mis à jour).

- [ ] **Step 4: Implémenter dans sessions.py**

Ajouter après la ligne `log = logging.getLogger(__name__)` :

```python
# Après un échec de génération LLM, ne pas retenter la session avant ce délai :
# chaque tentative brûle openai_max_attempts appels et une alerte Discord.
_GENERATION_BACKOFF = timedelta(hours=6)


def _in_generation_backoff(session: dict[str, Any], now: datetime) -> bool:
    raw = session.get("workout_generation_failed_at")
    if not isinstance(raw, str) or not raw:
        return False
    try:
        failed_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return now - failed_at < _GENERATION_BACKOFF
```

Dans `_generate_and_persist`, après le `capture(...)` du bloc `except OpenAIError`, ajouter avant `return False` :

```python
        db.table("planned_sessions").update(
            {"workout_generation_failed_at": datetime.now(UTC).isoformat()}
        ).eq("id", session["id"]).execute()
```

Dans le même `_generate_and_persist`, ajouter la clé de reset à l'update de succès :

```python
    db.table("planned_sessions").update(
        {
            "workout": workout.model_dump(),
            "workout_generated_at": datetime.now(UTC).isoformat(),
            "workout_generation_failed_at": None,
        }
    ).eq("id", session["id"]).execute()
```

Dans `ensure_sessions` :

1. Dans le `.select(...)` de `pending_resp`, ajouter `workout_generation_failed_at` à la liste de colonnes :
   `"id, sport, session_type, target_duration_s, target_tss, "`
   `"target_elevation_gain_m, phase, date, workout_generation_failed_at"`
2. Remplacer le corps entre `pending = ...` et la boucle par :

```python
    if not pending:
        return {"generated_count": 0, "failed_count": 0, "skipped_count": 0, "deferred_count": 0}

    now = datetime.now(UTC)
    ready = [s for s in pending if not _in_generation_backoff(s, now)]
    deferred = len(pending) - len(ready)

    generatable = [session for session in ready if not _should_skip_workout_generation(session)]
    skipped = len(ready) - len(generatable)
    if not generatable:
        return {
            "generated_count": 0,
            "failed_count": 0,
            "skipped_count": skipped,
            "deferred_count": deferred,
        }
```

3. Le return final devient :

```python
    return {
        "generated_count": generated,
        "failed_count": failed,
        "skipped_count": skipped,
        "deferred_count": deferred,
    }
```

Dans `regenerate_session` (régénération manuelle : ignore le backoff, mais reset au succès), ajouter la clé au payload d'update :

```python
    db.table("planned_sessions").update(
        {
            "workout": workout.model_dump(),
            "workout_generated_at": datetime.now(UTC).isoformat(),
            "workout_generation_failed_at": None,
        }
    ).eq("id", session_id).execute()
```

- [ ] **Step 5: Lancer la suite complète**

Run: `cd worker && uv run pytest -v`
Expected: PASS (tous — vérifier notamment que `test_ensure_sessions_continues_on_error` et `test_ensure_sessions_reports_failure_to_sentry` passent toujours : l'update d'échec sur MagicMock est transparent).

- [ ] **Step 6: Quality gates + commit**

```bash
cd worker && uv run ruff format . && uv run ruff check . && uv run mypy src/
git add supabase/migrations/20260703000000_workout_generation_backoff.sql worker/src/garmin_sync/coach/sessions.py worker/tests/coach/test_sessions.py
git commit -m "feat(coach): defer regeneration 6h after LLM failure (anti-spam backoff)

Chaque passage d'ensure_sessions retentait les mêmes sessions en échec
(3 appels OpenAI + 1 alerte Discord par session toutes les ~2min).
Nouvelle colonne planned_sessions.workout_generation_failed_at + filtre
worker : une session en échec est différée 6h (deferred_count exposé).
regenerate_session (manuel) ignore le backoff et reset le marqueur."
```

---

### Task 4: Vérification finale + PR (orchestrateur, pas de sous-agent)

- [ ] **Step 1:** Suite complète + gates : `cd worker && uv run pytest -v && uv run ruff format --check . && uv run ruff check . && uv run mypy src/`
- [ ] **Step 2:** Push branche `fix/workout-envelope-consistency`, ouvrir la PR (titre `fix(coach): self-consistent workout envelope + LLM retry context + failure backoff`), corps : diagnostic (bug prod 2026-07-03), les 3 fixes, note déploiement : **l'image Docker Hub ne se reconstruit qu'au merge sur main, puis pull manuel sur UNRAID requis** ; la migration s'auto-applique via CI (E17). Les 4 sessions prod (740d38ac, ed231a1c, fa95b0c3, 7f90e2bc) se régénéreront seules au prochain ensure_sessions post-déploiement.
- [ ] **Step 3:** Board GitHub Projects #4 : créer l'item (EPIC Coaching, P0), le passer In Review avec la PR liée (fallback issue si scope `project` manquant sur le token).
