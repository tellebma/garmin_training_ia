# E5 — LLM Session Generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformer chaque `planned_session` (E4) en structure JSON workout via OpenAI GPT-4o-mini, et rendre un texte FR markdown localement depuis cette structure.

**Architecture:** Worker Python expose `POST /coach/ensure-sessions?days=7` appelé par Server Action quand l'utilisateur ouvre `/today`. Le worker fetch les `planned_sessions` sans workout, appelle OpenAI structured output, valide Pydantic, upsert `workout` JSONB. Frontend templating Markdown FR vit côté Vercel pour zéro latence d'affichage.

**Tech Stack:** OpenAI Python SDK (structured outputs), Pydantic v2, FastAPI, Next.js Server Actions, Vitest, pytest.

**Spec:** [`../specs/2026-05-20-e5-llm-session-generation-design.md`](../specs/2026-05-20-e5-llm-session-generation-design.md).

**Branch:** `feat/e5-llm-sessions` (already created from main after E4+E7 merge).

---

## File Structure

```
garmin_training/
├── supabase/migrations/
│   └── 20260522000000_e5_session_workout.sql   ← NEW: workout jsonb column
├── worker/
│   ├── pyproject.toml                          ← MOD: add openai>=1.50.0
│   ├── .env.example                            ← MOD: add OPENAI_API_KEY
│   ├── src/garmin_sync/
│   │   ├── config.py                           ← MOD: load OPENAI_* env
│   │   ├── main.py                             ← MOD: 2 new endpoints
│   │   └── coach/
│   │       ├── workout_schema.py               ← NEW: Pydantic Workout
│   │       ├── openai_client.py                ← NEW: cached OpenAI wrapper
│   │       └── sessions.py                     ← NEW: ensure_sessions + regenerate
│   └── tests/coach/
│       ├── test_workout_schema.py              ← NEW
│       ├── test_openai_client.py               ← NEW
│       └── test_sessions.py                    ← NEW
├── lib/
│   ├── coach/
│   │   ├── workout-types.ts                    ← NEW: TS types mirroring Pydantic
│   │   └── session-templates.ts                ← NEW: 21 sport×type FR markdown templates
│   └── worker.ts                               ← MOD: ensureSessions + regenerateSession HTTP
├── app/
│   ├── actions/
│   │   └── sessions.ts                         ← NEW: Server Actions
│   └── (app)/
│       ├── today/page.tsx                      ← MOD: trigger ensureSessions + render workout
│       └── calendar/page.tsx                   ← MOD: render workout
├── tests/unit/
│   ├── lib/coach/
│   │   ├── workout-types.test.ts               ← NEW
│   │   └── session-templates.test.ts           ← NEW
│   └── actions/
│       └── sessions.test.ts                    ← NEW
└── docs/superpowers/specs/2026-05-20-e5-...md  ← already committed
```

---

## Task 1 — DB migration

**Files:**
- Create: `supabase/migrations/20260522000000_e5_session_workout.sql`

- [ ] **Step 1.1 — Write migration SQL**

```sql
-- 20260522000000_e5_session_workout.sql
-- E5: workout JSON structure produced by LLM, plus generation timestamp.

alter table public.planned_sessions
  add column if not exists workout jsonb,
  add column if not exists workout_generated_at timestamptz;

-- Partial index for the "needs generation" hot path
create index if not exists planned_sessions_workout_pending_idx
  on public.planned_sessions (user_id, date)
  where workout is null;

comment on column public.planned_sessions.workout is
  'LLM-generated session structure (warmup, main intervals, cooldown). Schema in worker/src/garmin_sync/coach/workout_schema.py';
comment on column public.planned_sessions.workout_generated_at is
  'Timestamp of last successful workout generation. NULL means pending.';
```

- [ ] **Step 1.2 — Apply via MCP Supabase**

Use the Supabase MCP (`mcp__supabase__apply_migration`) with project `peiyrqplymdlmlpsbqzu`:

```
name: e5_session_workout
query: <content of the migration file above>
```

Then verify with `mcp__supabase__list_tables` that `planned_sessions` has the new columns.

- [ ] **Step 1.3 — Commit**

```bash
git add supabase/migrations/20260522000000_e5_session_workout.sql
git commit -m "feat(e5): add workout jsonb column on planned_sessions"
```

---

## Task 2 — Worker dependencies + config

**Files:**
- Modify: `worker/pyproject.toml`
- Modify: `worker/.env.example`
- Modify: `worker/src/garmin_sync/config.py`
- Test: `worker/tests/test_config.py`

- [ ] **Step 2.1 — Add openai dependency**

In `worker/pyproject.toml`, under `[project] dependencies`, add `"openai>=1.50.0"`. Then:

```bash
cd worker && uv sync --all-groups
```

- [ ] **Step 2.2 — Add env vars to `.env.example`**

```
OPENAI_API_KEY=sk-replace-me
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_S=30
```

- [ ] **Step 2.3 — Write failing test for config**

In `worker/tests/test_config.py`, append:

```python
def test_settings_loads_openai_config(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_TIMEOUT_S", "30")
    get_settings.cache_clear()
    s = get_settings()
    assert s.openai_api_key == "sk-test"
    assert s.openai_model == "gpt-4o-mini"
    assert s.openai_timeout_s == 30


def test_settings_openai_defaults(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_TIMEOUT_S", raising=False)
    get_settings.cache_clear()
    s = get_settings()
    assert s.openai_model == "gpt-4o-mini"
    assert s.openai_timeout_s == 30
```

- [ ] **Step 2.4 — Run, expect FAIL**

```bash
cd worker && uv run pytest tests/test_config.py::test_settings_loads_openai_config -v
```

Expected: AttributeError on `openai_api_key`.

- [ ] **Step 2.5 — Add fields in `config.py`**

```python
class Settings(BaseSettings):
    # ... existing fields ...
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    openai_timeout_s: int = Field(default=30)
```

- [ ] **Step 2.6 — Re-run, expect PASS**

```bash
cd worker && uv run pytest tests/test_config.py -v
```

- [ ] **Step 2.7 — Commit**

```bash
git add worker/pyproject.toml worker/uv.lock worker/.env.example worker/src/garmin_sync/config.py worker/tests/test_config.py
git commit -m "feat(e5): add openai SDK + config (OPENAI_API_KEY, MODEL, TIMEOUT)"
```

---

## Task 3 — Pydantic Workout schema

**Files:**
- Create: `worker/src/garmin_sync/coach/workout_schema.py`
- Create: `worker/tests/coach/test_workout_schema.py`

- [ ] **Step 3.1 — Write failing tests**

```python
# worker/tests/coach/test_workout_schema.py
from garmin_sync.coach.workout_schema import (
    IntervalTarget,
    IntervalBlock,
    IntervalSet,
    Workout,
)
import pytest
from pydantic import ValidationError


def test_target_minimal_z_label_only():
    t = IntervalTarget(label="Z2", rpe=5)
    assert t.label == "Z2"
    assert t.bpm_low is None


def test_target_with_bpm_range():
    t = IntervalTarget(label="Z3", bpm_low=145, bpm_high=160, rpe=6)
    assert t.bpm_high == 160


def test_target_rpe_out_of_range_rejects():
    with pytest.raises(ValidationError):
        IntervalTarget(label="Z2", rpe=11)


def test_workout_minimal_structure():
    target = IntervalTarget(label="Z2", rpe=4)
    block = IntervalBlock(duration_s=600, target=target)
    w = Workout(
        warmup=block,
        main=[block],
        cooldown=block,
        summary_md="Test session",
    )
    assert w.summary_md == "Test session"
    assert len(w.main) == 1


def test_workout_intervals_set():
    target_z3 = IntervalTarget(label="Z3", rpe=6)
    target_z1 = IntervalTarget(label="Z1", rpe=2)
    work = IntervalBlock(duration_s=480, target=target_z3)
    rest = IntervalBlock(duration_s=120, target=target_z1)
    set_ = IntervalSet(reps=4, work=work, rest=rest)
    w = Workout(
        warmup=IntervalBlock(duration_s=600, target=target_z1),
        main=[set_],
        cooldown=IntervalBlock(duration_s=600, target=target_z1),
        summary_md="4x8min threshold",
    )
    assert isinstance(w.main[0], IntervalSet)
    assert w.main[0].reps == 4


def test_workout_reps_bounds():
    target = IntervalTarget(label="Z3", rpe=5)
    block = IntervalBlock(duration_s=120, target=target)
    with pytest.raises(ValidationError):
        IntervalSet(reps=0, work=block, rest=block)
    with pytest.raises(ValidationError):
        IntervalSet(reps=21, work=block, rest=block)
```

Also add a sibling `worker/tests/coach/__init__.py` if not already present (it should be, since E4 tests live there).

- [ ] **Step 3.2 — Run, expect FAIL (module not found)**

```bash
cd worker && uv run pytest tests/coach/test_workout_schema.py -v
```

- [ ] **Step 3.3 — Implement `workout_schema.py`**

```python
# worker/src/garmin_sync/coach/workout_schema.py
"""Pydantic models for a single LLM-generated workout.

Matches the TypeScript Workout type in `lib/coach/workout-types.ts` —
when you change one, change the other.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

Zone = Literal["Z1", "Z2", "Z3", "Z4", "Z5"]
Rpe = Annotated[int, Field(ge=1, le=10)]


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


class IntervalBlock(BaseModel):
    duration_s: int = Field(ge=1)
    target: IntervalTarget
    notes: str | None = None


class IntervalSet(BaseModel):
    """A repeated work/rest pattern (used for intervals/threshold sessions)."""

    reps: int = Field(ge=1, le=20)
    work: IntervalBlock
    rest: IntervalBlock


MainBlock = Union[IntervalBlock, IntervalSet]


class Workout(BaseModel):
    warmup: IntervalBlock
    main: list[MainBlock]
    cooldown: IntervalBlock
    summary_md: str
    technical_focus: str | None = None

    def total_duration_s(self) -> int:
        total = self.warmup.duration_s + self.cooldown.duration_s
        for block in self.main:
            if isinstance(block, IntervalSet):
                total += block.reps * (block.work.duration_s + block.rest.duration_s)
            else:
                total += block.duration_s
        return total
```

- [ ] **Step 3.4 — Re-run tests, expect PASS**

```bash
cd worker && uv run pytest tests/coach/test_workout_schema.py -v
```

- [ ] **Step 3.5 — Verify total_duration_s helper**

Add one more test:

```python
def test_workout_total_duration_includes_sets():
    target = IntervalTarget(label="Z2", rpe=4)
    warmup = IntervalBlock(duration_s=600, target=target)
    cooldown = IntervalBlock(duration_s=600, target=target)
    work = IntervalBlock(duration_s=300, target=target)
    rest = IntervalBlock(duration_s=120, target=target)
    main_set = IntervalSet(reps=5, work=work, rest=rest)
    w = Workout(warmup=warmup, main=[main_set], cooldown=cooldown, summary_md="x")
    # 600 + 5*(300+120) + 600 = 600 + 2100 + 600 = 3300
    assert w.total_duration_s() == 3300
```

Run, expect PASS.

- [ ] **Step 3.6 — Commit**

```bash
git add worker/src/garmin_sync/coach/workout_schema.py worker/tests/coach/test_workout_schema.py
git commit -m "feat(e5): Pydantic Workout schema (intervals + targets + sets)"
```

---

## Task 4 — OpenAI client wrapper

**Files:**
- Create: `worker/src/garmin_sync/coach/openai_client.py`
- Create: `worker/tests/coach/test_openai_client.py`

- [ ] **Step 4.1 — Write failing tests**

```python
# worker/tests/coach/test_openai_client.py
from unittest.mock import MagicMock, patch
import pytest
from garmin_sync.coach.openai_client import (
    OpenAIError,
    generate_workout_for_session,
)


def _athlete_full():
    return {
        "ftp_watts": 240,
        "vma_kmh": 17.0,
        "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }


def _race_context():
    return {"discipline": "triathlon", "total_elevation_gain_m": 350, "weeks_to_race": 12}


def _session():
    return {
        "sport": "run",
        "session_type": "threshold",
        "target_duration_s": 3600,
        "target_tss": 75,
        "phase": "build",
    }


@patch("garmin_sync.coach.openai_client._get_client")
def test_generate_workout_returns_validated_workout(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.beta.chat.completions.parse.return_value.choices = [
        MagicMock(
            message=MagicMock(
                parsed=MagicMock(model_dump=lambda: {
                    "warmup": {
                        "duration_s": 600,
                        "target": {"label": "Z1", "rpe": 2,
                                   "bpm_low": 130, "bpm_high": 145,
                                   "watts_low": None, "watts_high": None,
                                   "pace_low_kmh": None, "pace_high_kmh": None},
                        "notes": None,
                    },
                    "main": [{
                        "reps": 4,
                        "work": {
                            "duration_s": 480,
                            "target": {"label": "Z4", "rpe": 8,
                                       "bpm_low": 170, "bpm_high": 180,
                                       "watts_low": None, "watts_high": None,
                                       "pace_low_kmh": 14.0, "pace_high_kmh": 15.0},
                            "notes": None,
                        },
                        "rest": {
                            "duration_s": 120,
                            "target": {"label": "Z1", "rpe": 2,
                                       "bpm_low": 130, "bpm_high": 145,
                                       "watts_low": None, "watts_high": None,
                                       "pace_low_kmh": None, "pace_high_kmh": None},
                            "notes": None,
                        },
                    }],
                    "cooldown": {
                        "duration_s": 600,
                        "target": {"label": "Z1", "rpe": 2,
                                   "bpm_low": 130, "bpm_high": 145,
                                   "watts_low": None, "watts_high": None,
                                   "pace_low_kmh": None, "pace_high_kmh": None},
                        "notes": None,
                    },
                    "summary_md": "Séance seuil exigeante.",
                    "technical_focus": "Foulée tonique sur les répétitions.",
                })
            )
        )
    ]

    workout = generate_workout_for_session(
        session=_session(), athlete=_athlete_full(), race_context=_race_context()
    )
    assert workout.summary_md.startswith("Séance")
    assert len(workout.main) == 1


@patch("garmin_sync.coach.openai_client._get_client")
def test_generate_workout_raises_on_openai_error(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.beta.chat.completions.parse.side_effect = Exception("boom")
    with pytest.raises(OpenAIError):
        generate_workout_for_session(
            session=_session(), athlete=_athlete_full(), race_context=_race_context()
        )


@patch("garmin_sync.coach.openai_client._get_client")
def test_prompt_includes_race_context(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    parsed = MagicMock(model_dump=lambda: {
        "warmup": {"duration_s": 600, "target": {"label": "Z1", "rpe": 2}, "notes": None},
        "main": [{"duration_s": 1800, "target": {"label": "Z2", "rpe": 4}, "notes": None}],
        "cooldown": {"duration_s": 600, "target": {"label": "Z1", "rpe": 2}, "notes": None},
        "summary_md": "ok",
        "technical_focus": None,
    })
    mock_client.beta.chat.completions.parse.return_value.choices = [
        MagicMock(message=MagicMock(parsed=parsed))
    ]
    generate_workout_for_session(
        session=_session(), athlete=_athlete_full(), race_context=_race_context()
    )
    call_args = mock_client.beta.chat.completions.parse.call_args
    user_msg = call_args.kwargs["messages"][1]["content"]
    assert "triathlon" in user_msg
    assert "12 semaines" in user_msg
    assert "350m" in user_msg
```

- [ ] **Step 4.2 — Run, expect FAIL (module not found)**

```bash
cd worker && uv run pytest tests/coach/test_openai_client.py -v
```

- [ ] **Step 4.3 — Implement `openai_client.py`**

```python
# worker/src/garmin_sync/coach/openai_client.py
"""Thin OpenAI client wrapper using structured outputs (Pydantic-typed responses)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from openai import OpenAI

from garmin_sync.config import get_settings
from garmin_sync.coach.workout_schema import Workout


class OpenAIError(Exception):
    """Raised when the OpenAI API call or response is unusable."""


_SYSTEM_PROMPT = """Tu es un coach triathlon expert. Tu produis des séances d'entraînement structurées
au format JSON strict suivant le schema fourni. Tu adaptes les cibles physiologiques
au profil de l'athlète. Tu réponds uniquement en JSON valide, sans aucun texte
en dehors du schema.

Règles :
- Échauffement : 10-15min, progression Z1→Z2.
- Retour calme : 8-12min, Z1.
- Séance "long" : un seul gros bloc continu (pas d'intervalles).
- Séance "intervals" : des sets répétés (work + rest).
- Séance "threshold" : 1-2 sets longs (≥8min work, 2-3min rest).
- Séance "recovery" : Z1 seulement, durée courte.
- Séance "endurance" : un seul bloc Z2-Z3 continu.
- summary_md : 1-2 phrases FR conseil du jour, motivant mais bref.
- technical_focus : 1 phrase FR sur l'aspect technique spécifique au sport.
"""


@lru_cache(maxsize=1)
def _get_client() -> OpenAI:
    s = get_settings()
    if not s.openai_api_key:
        raise OpenAIError("OPENAI_API_KEY not configured")
    return OpenAI(api_key=s.openai_api_key, timeout=s.openai_timeout_s)


def _build_user_prompt(
    session: dict[str, Any],
    athlete: dict[str, Any],
    race_context: dict[str, Any],
) -> str:
    minutes = session["target_duration_s"] // 60
    sports = athlete.get("sports_strengths") or {}
    swim = sports.get("swim", "?")
    bike = sports.get("bike", "?")
    run = sports.get("run", "?")
    fc = athlete.get("fc_max_bpm")
    ftp = athlete.get("ftp_watts")
    vma = athlete.get("vma_kmh")

    lines = [
        f"Session : {session['sport']} {session['session_type']} en phase {session['phase']}, "
        f"durée cible {minutes}min, TSS {session['target_tss']}.",
        "",
        "Athlète :",
        f"- FC max : {fc} bpm" if fc else "- FC max : non connue",
    ]
    if session["sport"] == "bike":
        lines.append(f"- FTP : {ftp} W" if ftp else "- FTP : non connue")
    if session["sport"] == "run":
        lines.append(f"- VMA : {vma} km/h" if vma else "- VMA : non connue")
    lines.extend([
        f"- Niveau (1-5) : swim={swim}, bike={bike}, run={run}",
        "",
        f"Course objectif (dans {race_context['weeks_to_race']} semaines) :",
        f"- Discipline : {race_context['discipline']}",
        f"- Dénivelé total : {race_context['total_elevation_gain_m']}m",
    ])
    return "\n".join(lines)


def generate_workout_for_session(
    *,
    session: dict[str, Any],
    athlete: dict[str, Any],
    race_context: dict[str, Any],
) -> Workout:
    """Call OpenAI with structured output, return a validated Workout."""
    client = _get_client()
    settings = get_settings()
    try:
        resp = client.beta.chat.completions.parse(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(session, athlete, race_context)},
            ],
            response_format=Workout,
        )
    except Exception as e:
        raise OpenAIError(f"OpenAI call failed: {e}") from e
    parsed = resp.choices[0].message.parsed
    if parsed is None:
        raise OpenAIError("OpenAI returned no parsed payload")
    # `parsed` is already a Workout instance with `response_format=Workout`,
    # but defensively re-validate via model_dump round-trip.
    return Workout.model_validate(parsed.model_dump())
```

- [ ] **Step 4.4 — Re-run tests, expect PASS**

```bash
cd worker && uv run pytest tests/coach/test_openai_client.py -v
```

- [ ] **Step 4.5 — Commit**

```bash
git add worker/src/garmin_sync/coach/openai_client.py worker/tests/coach/test_openai_client.py
git commit -m "feat(e5): OpenAI client wrapper with structured outputs (parsed Workout)"
```

---

## Task 5 — Sessions orchestrator (ensure + regenerate)

**Files:**
- Create: `worker/src/garmin_sync/coach/sessions.py`
- Create: `worker/tests/coach/test_sessions.py`

- [ ] **Step 5.1 — Write failing tests**

```python
# worker/tests/coach/test_sessions.py
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
import pytest
from garmin_sync.coach.sessions import (
    ensure_sessions,
    regenerate_session,
    SessionNotFound,
)


def _mock_workout():
    return {
        "warmup": {"duration_s": 600, "target": {"label": "Z1", "rpe": 2}, "notes": None},
        "main": [{"duration_s": 1800, "target": {"label": "Z2", "rpe": 4}, "notes": None}],
        "cooldown": {"duration_s": 600, "target": {"label": "Z1", "rpe": 2}, "notes": None},
        "summary_md": "ok",
        "technical_focus": None,
    }


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_skips_already_generated(mock_db, mock_gen):
    db = MagicMock()
    mock_db.return_value = db
    # No pending sessions
    db.table.return_value.select.return_value.eq.return_value.is_.return_value.gte.return_value.lte.return_value.execute.return_value.data = []
    result = ensure_sessions(user_id="u1", days=7)
    assert result == {"generated_count": 0, "failed_count": 0, "skipped_count": 0}
    mock_gen.assert_not_called()


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_generates_for_each_pending(mock_db, mock_gen):
    db = MagicMock()
    mock_db.return_value = db
    db.table.return_value.select.return_value.eq.return_value.is_.return_value.gte.return_value.lte.return_value.execute.return_value.data = [
        {"id": "s1", "sport": "run", "session_type": "endurance",
         "target_duration_s": 3000, "target_tss": 50, "phase": "base", "date": "2026-05-21"},
        {"id": "s2", "sport": "bike", "session_type": "long",
         "target_duration_s": 7200, "target_tss": 120, "phase": "base", "date": "2026-05-22"},
    ]
    # Profile + race lookups
    profile_chain = db.table.return_value.select.return_value.eq.return_value
    profile_chain.single.return_value.execute.return_value.data = {
        "ftp_watts": 240, "vma_kmh": 17.0, "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }
    race_chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value
    race_chain.maybe_single.return_value.execute.return_value.data = {
        "discipline": "triathlon", "total_elevation_gain_m": 350, "race_date": "2026-08-15",
    }

    workout_obj = MagicMock(model_dump=lambda: _mock_workout())
    mock_gen.return_value = workout_obj

    result = ensure_sessions(user_id="u1", days=7)
    assert result["generated_count"] == 2
    assert mock_gen.call_count == 2


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_continues_on_error(mock_db, mock_gen, caplog):
    db = MagicMock()
    mock_db.return_value = db
    db.table.return_value.select.return_value.eq.return_value.is_.return_value.gte.return_value.lte.return_value.execute.return_value.data = [
        {"id": "s1", "sport": "run", "session_type": "endurance",
         "target_duration_s": 3000, "target_tss": 50, "phase": "base", "date": "2026-05-21"},
        {"id": "s2", "sport": "bike", "session_type": "long",
         "target_duration_s": 7200, "target_tss": 120, "phase": "base", "date": "2026-05-22"},
    ]
    profile_chain = db.table.return_value.select.return_value.eq.return_value
    profile_chain.single.return_value.execute.return_value.data = {
        "ftp_watts": 240, "vma_kmh": 17.0, "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }
    race_chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value
    race_chain.maybe_single.return_value.execute.return_value.data = None  # no active race

    workout_obj = MagicMock(model_dump=lambda: _mock_workout())
    mock_gen.side_effect = [Exception("boom"), workout_obj]

    result = ensure_sessions(user_id="u1", days=7)
    assert result["generated_count"] == 1
    assert result["failed_count"] == 1


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_regenerate_session_updates_existing(mock_db, mock_gen):
    db = MagicMock()
    mock_db.return_value = db
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "s1", "user_id": "u1", "sport": "run", "session_type": "intervals",
        "target_duration_s": 3600, "target_tss": 80, "phase": "peak", "date": "2026-05-25",
    }
    profile_chain = db.table.return_value.select.return_value.eq.return_value
    profile_chain.single.return_value.execute.return_value.data = {
        "ftp_watts": 240, "vma_kmh": 17.0, "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }
    race_chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value
    race_chain.maybe_single.return_value.execute.return_value.data = None
    mock_gen.return_value = MagicMock(model_dump=lambda: _mock_workout())

    result = regenerate_session(user_id="u1", session_id="s1")
    assert result["status"] == "ok"
    mock_gen.assert_called_once()


@patch("garmin_sync.coach.sessions.get_admin_client")
def test_regenerate_session_not_found_for_user(mock_db):
    db = MagicMock()
    mock_db.return_value = db
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None
    with pytest.raises(SessionNotFound):
        regenerate_session(user_id="u1", session_id="other-id")
```

- [ ] **Step 5.2 — Run, expect FAIL**

```bash
cd worker && uv run pytest tests/coach/test_sessions.py -v
```

- [ ] **Step 5.3 — Implement `sessions.py`**

```python
# worker/src/garmin_sync/coach/sessions.py
"""Orchestrator : fetch pending sessions, call LLM, persist workout."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from garmin_sync.coach.openai_client import OpenAIError, generate_workout_for_session
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)


class SessionNotFound(Exception):
    """Raised when a session_id does not exist for the given user."""


def _load_profile_and_race(db: Any, user_id: str) -> tuple[dict[str, Any], dict[str, Any] | None, int]:
    """Returns (athlete, race_context_or_None, weeks_to_race_or_0)."""
    profile = (
        db.table("athlete_profiles")
        .select("ftp_watts, vma_kmh, fc_max_bpm, sports_strengths")
        .eq("user_id", user_id)
        .single()
        .execute()
        .data
    ) or {}

    race = (
        db.table("race_goals")
        .select("discipline, total_elevation_gain_m, race_date")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .maybe_single()
        .execute()
        .data
    )

    weeks = 0
    if race and race.get("race_date"):
        race_date = date.fromisoformat(race["race_date"])
        weeks = max(0, (race_date - date.today()).days // 7)
    return profile, race, weeks


def _race_context(race: dict[str, Any] | None, weeks: int) -> dict[str, Any]:
    if not race:
        return {"discipline": "unknown", "total_elevation_gain_m": 0, "weeks_to_race": weeks}
    return {
        "discipline": race.get("discipline", "unknown"),
        "total_elevation_gain_m": race.get("total_elevation_gain_m") or 0,
        "weeks_to_race": weeks,
    }


def _generate_and_persist(
    db: Any,
    session: dict[str, Any],
    athlete: dict[str, Any],
    race_ctx: dict[str, Any],
) -> bool:
    try:
        workout = generate_workout_for_session(
            session=session, athlete=athlete, race_context=race_ctx
        )
    except OpenAIError as e:
        log.exception("openai failed for session=%s: %s", session["id"], e)
        return False
    db.table("planned_sessions").update(
        {
            "workout": workout.model_dump(),
            "workout_generated_at": datetime.utcnow().isoformat(),
        }
    ).eq("id", session["id"]).execute()
    return True


def ensure_sessions(*, user_id: str, days: int = 7) -> dict[str, int]:
    """Generate workouts for all planned_sessions where workout IS NULL in [today, today+days]."""
    db = get_admin_client()
    today = date.today()
    until = today + timedelta(days=days)

    pending = (
        db.table("planned_sessions")
        .select("id, sport, session_type, target_duration_s, target_tss, phase, date")
        .eq("user_id", user_id)
        .is_("workout", "null")
        .gte("date", today.isoformat())
        .lte("date", until.isoformat())
        .execute()
        .data
    ) or []

    if not pending:
        return {"generated_count": 0, "failed_count": 0, "skipped_count": 0}

    athlete, race, weeks = _load_profile_and_race(db, user_id)
    race_ctx = _race_context(race, weeks)

    generated = 0
    failed = 0
    for session in pending:
        if _generate_and_persist(db, session, athlete, race_ctx):
            generated += 1
        else:
            failed += 1
    return {"generated_count": generated, "failed_count": failed, "skipped_count": 0}


def regenerate_session(*, user_id: str, session_id: str) -> dict[str, Any]:
    """Force regenerate one session. Returns {status, workout}."""
    db = get_admin_client()
    session = (
        db.table("planned_sessions")
        .select("id, sport, session_type, target_duration_s, target_tss, phase, date")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .single()
        .execute()
        .data
    )
    if not session:
        raise SessionNotFound(f"session {session_id} not found for user {user_id}")

    athlete, race, weeks = _load_profile_and_race(db, user_id)
    race_ctx = _race_context(race, weeks)

    workout = generate_workout_for_session(
        session=session, athlete=athlete, race_context=race_ctx
    )
    db.table("planned_sessions").update(
        {
            "workout": workout.model_dump(),
            "workout_generated_at": datetime.utcnow().isoformat(),
        }
    ).eq("id", session_id).execute()
    return {"status": "ok", "workout": workout.model_dump()}
```

- [ ] **Step 5.4 — Re-run, expect PASS**

```bash
cd worker && uv run pytest tests/coach/test_sessions.py -v
```

- [ ] **Step 5.5 — Commit**

```bash
git add worker/src/garmin_sync/coach/sessions.py worker/tests/coach/test_sessions.py
git commit -m "feat(e5): sessions orchestrator (ensure_sessions + regenerate_session)"
```

---

## Task 6 — Worker endpoints

**Files:**
- Modify: `worker/src/garmin_sync/main.py`
- Modify: `worker/tests/test_main.py`

- [ ] **Step 6.1 — Write failing tests** (append to `worker/tests/test_main.py`)

```python
from unittest.mock import patch
from fastapi.testclient import TestClient
from garmin_sync.main import app


@patch("garmin_sync.coach.sessions.ensure_sessions")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_ensure_sessions_endpoint_ok(mock_jwt, mock_ensure):
    mock_jwt.return_value = "user-1"
    mock_ensure.return_value = {"generated_count": 3, "failed_count": 0, "skipped_count": 0}
    client = TestClient(app)
    r = client.post(
        "/coach/ensure-sessions",
        json={"days": 7},
        headers={"Authorization": "Bearer fake.jwt"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["generated_count"] == 3
    mock_ensure.assert_called_once_with(user_id="user-1", days=7)


@patch("garmin_sync.coach.sessions.ensure_sessions")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_ensure_sessions_default_days(mock_jwt, mock_ensure):
    mock_jwt.return_value = "user-1"
    mock_ensure.return_value = {"generated_count": 0, "failed_count": 0, "skipped_count": 0}
    client = TestClient(app)
    r = client.post(
        "/coach/ensure-sessions", json={}, headers={"Authorization": "Bearer fake.jwt"}
    )
    assert r.status_code == 200
    mock_ensure.assert_called_once_with(user_id="user-1", days=7)


@patch("garmin_sync.coach.sessions.regenerate_session")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_regenerate_session_endpoint_ok(mock_jwt, mock_regen):
    mock_jwt.return_value = "user-1"
    mock_regen.return_value = {"status": "ok", "workout": {"summary_md": "x"}}
    client = TestClient(app)
    r = client.post(
        "/coach/regenerate-session/sess-1",
        headers={"Authorization": "Bearer fake.jwt"},
    )
    assert r.status_code == 200
    mock_regen.assert_called_once_with(user_id="user-1", session_id="sess-1")


@patch("garmin_sync.coach.sessions.regenerate_session")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_regenerate_session_not_found(mock_jwt, mock_regen):
    from garmin_sync.coach.sessions import SessionNotFound

    mock_jwt.return_value = "user-1"
    mock_regen.side_effect = SessionNotFound("nope")
    client = TestClient(app)
    r = client.post(
        "/coach/regenerate-session/sess-1",
        headers={"Authorization": "Bearer fake.jwt"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "session_not_found"
```

- [ ] **Step 6.2 — Run, expect FAIL (endpoints missing)**

```bash
cd worker && uv run pytest tests/test_main.py -v -k "ensure_sessions or regenerate_session"
```

- [ ] **Step 6.3 — Add endpoints in `main.py`**

After the existing `/coach/generate-plan` endpoint:

```python
class EnsureSessionsRequest(BaseModel):
    days: int = 7


@app.post("/coach/ensure-sessions")
def coach_ensure_sessions(
    body: EnsureSessionsRequest,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    """Generate workout structures for planned_sessions where workout IS NULL in [today, today+days]."""
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.coach.sessions import ensure_sessions

        return ensure_sessions(user_id=user_id, days=body.days)
    except Exception as e:
        error_id = _new_error_id()
        log.exception("[%s] coach_ensure_sessions crashed for user=%s", error_id, user_id)
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }


@app.post("/coach/regenerate-session/{session_id}")
def coach_regenerate_session(
    session_id: str,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    """Force regenerate a workout for one session (user-triggered)."""
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.coach.sessions import SessionNotFound, regenerate_session

        return regenerate_session(user_id=user_id, session_id=session_id)
    except SessionNotFound:
        return {"status": "session_not_found"}
    except Exception as e:
        error_id = _new_error_id()
        log.exception(
            "[%s] coach_regenerate_session crashed for user=%s session=%s",
            error_id, user_id, session_id,
        )
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }
```

- [ ] **Step 6.4 — Re-run, expect PASS**

```bash
cd worker && uv run pytest tests/test_main.py -v
```

- [ ] **Step 6.5 — Full worker test suite + lint + format + mypy**

```bash
cd worker && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src/
```

All must pass.

- [ ] **Step 6.6 — Commit**

```bash
git add worker/src/garmin_sync/main.py worker/tests/test_main.py
git commit -m "feat(e5): worker endpoints POST /coach/ensure-sessions + /coach/regenerate-session"
```

---

## Task 7 — Frontend TypeScript types (mirror Pydantic)

**Files:**
- Create: `lib/coach/workout-types.ts`
- Create: `tests/unit/lib/coach/workout-types.test.ts`

- [ ] **Step 7.1 — Write failing tests**

```ts
// tests/unit/lib/coach/workout-types.test.ts
import { describe, expect, it } from 'vitest'
import {
  isIntervalSet,
  totalDurationS,
  type IntervalBlock,
  type IntervalSet,
  type Workout,
} from '@/lib/coach/workout-types'

const z1 = { label: 'Z1', rpe: 2 } as const
const block: IntervalBlock = { duration_s: 600, target: z1, notes: null }

describe('workout-types', () => {
  it('isIntervalSet returns true for sets, false for blocks', () => {
    const set: IntervalSet = { reps: 4, work: block, rest: block }
    expect(isIntervalSet(set)).toBe(true)
    expect(isIntervalSet(block)).toBe(false)
  })

  it('totalDurationS includes warmup + cooldown + simple blocks', () => {
    const w: Workout = {
      warmup: { duration_s: 600, target: z1, notes: null },
      main: [{ duration_s: 1800, target: z1, notes: null }],
      cooldown: { duration_s: 300, target: z1, notes: null },
      summary_md: 'ok',
      technical_focus: null,
    }
    expect(totalDurationS(w)).toBe(600 + 1800 + 300)
  })

  it('totalDurationS multiplies sets by reps', () => {
    const work: IntervalBlock = { duration_s: 300, target: z1, notes: null }
    const rest: IntervalBlock = { duration_s: 120, target: z1, notes: null }
    const w: Workout = {
      warmup: { duration_s: 600, target: z1, notes: null },
      main: [{ reps: 5, work, rest }],
      cooldown: { duration_s: 600, target: z1, notes: null },
      summary_md: 'ok',
      technical_focus: null,
    }
    // 600 + 5*(300+120) + 600 = 600 + 2100 + 600 = 3300
    expect(totalDurationS(w)).toBe(3300)
  })
})
```

- [ ] **Step 7.2 — Run, expect FAIL**

```bash
pnpm test tests/unit/lib/coach/workout-types.test.ts
```

- [ ] **Step 7.3 — Implement `workout-types.ts`**

```ts
// lib/coach/workout-types.ts
export type Zone = 'Z1' | 'Z2' | 'Z3' | 'Z4' | 'Z5'

export interface IntervalTarget {
  label: Zone
  rpe: number  // 1-10
  bpm_low?: number | null
  bpm_high?: number | null
  watts_low?: number | null
  watts_high?: number | null
  pace_low_kmh?: number | null
  pace_high_kmh?: number | null
}

export interface IntervalBlock {
  duration_s: number
  target: IntervalTarget
  notes?: string | null
}

export interface IntervalSet {
  reps: number
  work: IntervalBlock
  rest: IntervalBlock
}

export type MainBlock = IntervalBlock | IntervalSet

export interface Workout {
  warmup: IntervalBlock
  main: MainBlock[]
  cooldown: IntervalBlock
  summary_md: string
  technical_focus?: string | null
}

export function isIntervalSet(b: MainBlock): b is IntervalSet {
  return (b as IntervalSet).reps !== undefined
}

export function totalDurationS(w: Workout): number {
  let total = w.warmup.duration_s + w.cooldown.duration_s
  for (const block of w.main) {
    if (isIntervalSet(block)) {
      total += block.reps * (block.work.duration_s + block.rest.duration_s)
    } else {
      total += block.duration_s
    }
  }
  return total
}
```

- [ ] **Step 7.4 — Re-run, expect PASS**

```bash
pnpm test tests/unit/lib/coach/workout-types.test.ts
```

- [ ] **Step 7.5 — Commit**

```bash
git add lib/coach/workout-types.ts tests/unit/lib/coach/workout-types.test.ts
git commit -m "feat(e5): TypeScript Workout types mirroring Pydantic schema"
```

---

## Task 8 — Session-to-Markdown templates (frontend)

**Files:**
- Create: `lib/coach/session-templates.ts`
- Create: `tests/unit/lib/coach/session-templates.test.ts`

Note: this task does the **templating logic**. The exact wording of the FR strings should be reviewed by an expert sports agent; structure here is what matters.

- [ ] **Step 8.1 — Write failing tests**

```ts
// tests/unit/lib/coach/session-templates.test.ts
import { describe, expect, it } from 'vitest'
import { workoutToMarkdown } from '@/lib/coach/session-templates'
import type { Workout } from '@/lib/coach/workout-types'

const z1 = { label: 'Z1', rpe: 2, bpm_low: 130, bpm_high: 145 } as const
const z3 = { label: 'Z3', rpe: 6, bpm_low: 155, bpm_high: 170 } as const

function endurance(durationMin: number): Workout {
  return {
    warmup: { duration_s: 600, target: z1, notes: null },
    main: [{ duration_s: durationMin * 60 - 1200, target: z3, notes: null }],
    cooldown: { duration_s: 600, target: z1, notes: null },
    summary_md: 'Bonne séance endurance.',
    technical_focus: 'Cadence régulière.',
  }
}

describe('workoutToMarkdown', () => {
  it('renders endurance run with bpm targets and summary', () => {
    const md = workoutToMarkdown(endurance(60), 'run', 'endurance')
    expect(md).toContain('### Échauffement')
    expect(md).toContain('### Retour calme')
    expect(md).toContain('130-145 bpm')
    expect(md).toContain('Bonne séance endurance')
  })

  it('renders intervals run with sets', () => {
    const z4 = { label: 'Z4', rpe: 8, bpm_low: 170, bpm_high: 185 } as const
    const work = { duration_s: 240, target: z4, notes: null }
    const rest = { duration_s: 120, target: z1, notes: null }
    const w: Workout = {
      warmup: { duration_s: 600, target: z1, notes: null },
      main: [{ reps: 6, work, rest }],
      cooldown: { duration_s: 600, target: z1, notes: null },
      summary_md: 'Séance VMA.',
      technical_focus: 'Foulée tonique.',
    }
    const md = workoutToMarkdown(w, 'run', 'intervals')
    expect(md).toMatch(/6 (×|x) /)
    expect(md).toContain('4min')   // 240s = 4min
    expect(md).toContain('2min')   // 120s rest = 2min
  })

  it('falls back to Z-label when no bpm available', () => {
    const noTarget = { label: 'Z2', rpe: 4 } as const
    const w: Workout = {
      warmup: { duration_s: 600, target: noTarget, notes: null },
      main: [{ duration_s: 1800, target: noTarget, notes: null }],
      cooldown: { duration_s: 600, target: noTarget, notes: null },
      summary_md: 'ok',
      technical_focus: null,
    }
    const md = workoutToMarkdown(w, 'bike', 'endurance')
    expect(md).toContain('Z2')
    expect(md).not.toContain('bpm')
  })

  it('renders bike threshold session', () => {
    const z4 = { label: 'Z4', rpe: 8, watts_low: 210, watts_high: 240 } as const
    const work = { duration_s: 480, target: z4, notes: null }
    const rest = { duration_s: 180, target: z1, notes: null }
    const w: Workout = {
      warmup: { duration_s: 900, target: z1, notes: null },
      main: [{ reps: 3, work, rest }],
      cooldown: { duration_s: 900, target: z1, notes: null },
      summary_md: 'Seuil vélo.',
      technical_focus: 'Pédalage rond.',
    }
    const md = workoutToMarkdown(w, 'bike', 'threshold')
    expect(md).toContain('210-240 W')
  })
})
```

- [ ] **Step 8.2 — Run, expect FAIL**

```bash
pnpm test tests/unit/lib/coach/session-templates.test.ts
```

- [ ] **Step 8.3 — Implement `session-templates.ts`**

```ts
// lib/coach/session-templates.ts
import {
  isIntervalSet,
  type IntervalBlock,
  type IntervalSet,
  type IntervalTarget,
  type Workout,
} from '@/lib/coach/workout-types'

export type Sport = 'swim' | 'bike' | 'run' | 'brick' | 'rest'
export type SessionType =
  | 'endurance'
  | 'threshold'
  | 'intervals'
  | 'long'
  | 'recovery'
  | 'race'
  | 'rest'

const SPORT_LABEL: Record<Sport, string> = {
  swim: 'Natation',
  bike: 'Vélo',
  run: 'Course',
  brick: 'Enchaînement vélo→CAP',
  rest: 'Repos',
}

const TYPE_LABEL: Record<SessionType, string> = {
  endurance: 'Endurance',
  threshold: 'Seuil',
  intervals: 'Fractionné',
  long: 'Sortie longue',
  recovery: 'Récupération',
  race: 'Course',
  rest: 'Repos',
}

function fmtDuration(s: number): string {
  if (s < 60) return `${s}s`
  const m = Math.round(s / 60)
  if (m < 60) return `${m}min`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return rem === 0 ? `${h}h` : `${h}h${String(rem).padStart(2, '0')}`
}

function fmtTarget(t: IntervalTarget, sport: Sport): string {
  if (t.bpm_low !== undefined && t.bpm_low !== null && t.bpm_high) {
    return `${t.bpm_low}-${t.bpm_high} bpm`
  }
  if (sport === 'bike' && t.watts_low && t.watts_high) {
    return `${t.watts_low}-${t.watts_high} W`
  }
  if (sport === 'run' && t.pace_low_kmh && t.pace_high_kmh) {
    return `${t.pace_low_kmh.toFixed(1)}-${t.pace_high_kmh.toFixed(1)} km/h`
  }
  return t.label
}

function renderBlock(b: IntervalBlock, sport: Sport, indent = ''): string {
  const lines = [`${indent}- ${fmtDuration(b.duration_s)} @ ${fmtTarget(b.target, sport)}`]
  if (b.notes) lines.push(`${indent}  *${b.notes}*`)
  return lines.join('\n')
}

function renderSet(s: IntervalSet, sport: Sport): string {
  const repsLabel = `${s.reps} × `
  const workLine = `- ${repsLabel}${fmtDuration(s.work.duration_s)} @ ${fmtTarget(s.work.target, sport)}`
  const restLine = `  Récup ${fmtDuration(s.rest.duration_s)} @ ${fmtTarget(s.rest.target, sport)}`
  const lines = [workLine, restLine]
  if (s.work.notes) lines.push(`  *${s.work.notes}*`)
  return lines.join('\n')
}

export function workoutToMarkdown(w: Workout, sport: Sport, type: SessionType): string {
  const lines: string[] = []
  lines.push(`## ${SPORT_LABEL[sport]} — ${TYPE_LABEL[type]}`)
  lines.push('')
  lines.push('### Échauffement')
  lines.push(renderBlock(w.warmup, sport))
  lines.push('')
  lines.push('### Corps de séance')
  for (const block of w.main) {
    if (isIntervalSet(block)) {
      lines.push(renderSet(block, sport))
    } else {
      lines.push(renderBlock(block, sport))
    }
  }
  lines.push('')
  lines.push('### Retour calme')
  lines.push(renderBlock(w.cooldown, sport))
  lines.push('')
  lines.push(`*${w.summary_md}*`)
  if (w.technical_focus) {
    lines.push('')
    lines.push(`> Focus technique : ${w.technical_focus}`)
  }
  return lines.join('\n')
}
```

- [ ] **Step 8.4 — Re-run, expect PASS**

```bash
pnpm test tests/unit/lib/coach/session-templates.test.ts
```

- [ ] **Step 8.5 — Commit**

```bash
git add lib/coach/session-templates.ts tests/unit/lib/coach/session-templates.test.ts
git commit -m "feat(e5): session-templates renders FR markdown from Workout JSON"
```

---

## Task 9 — Server Action + worker HTTP client

**Files:**
- Modify: `lib/worker.ts`
- Create: `app/actions/sessions.ts`
- Create: `tests/unit/actions/sessions.test.ts`

- [ ] **Step 9.1 — Add HTTP methods in `lib/worker.ts`**

Look at the existing `callWorker` pattern. Append:

```ts
export async function workerEnsureSessions(jwt: string, days: number) {
  return callWorker('/coach/ensure-sessions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${jwt}` },
    body: JSON.stringify({ days }),
  })
}

export async function workerRegenerateSession(jwt: string, sessionId: string) {
  return callWorker(`/coach/regenerate-session/${sessionId}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${jwt}` },
  })
}
```

(Adapt to the actual signature of `callWorker` in this repo. The pattern is the same as `connectGarmin` in `app/actions/garmin-auth.ts`.)

- [ ] **Step 9.2 — Write failing test for Server Action**

```ts
// tests/unit/actions/sessions.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const workerEnsure = vi.fn()
const workerRegen = vi.fn()
const supabaseGetSession = vi.fn()

vi.mock('@/lib/worker', () => ({
  workerEnsureSessions: (jwt: string, days: number) => workerEnsure(jwt, days) as unknown,
  workerRegenerateSession: (jwt: string, id: string) => workerRegen(jwt, id) as unknown,
}))
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({
    auth: { getSession: () => supabaseGetSession() },
  }),
}))

describe('sessions Server Actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })
  afterEach(() => vi.restoreAllMocks())

  it('ensureGeneratedSessions calls worker with current user JWT', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerEnsure.mockResolvedValueOnce({ generated_count: 3 })
    const { ensureGeneratedSessions } = await import('@/app/actions/sessions')
    const result = await ensureGeneratedSessions(7)
    expect(workerEnsure).toHaveBeenCalledWith('jwt-1', 7)
    expect(result.success).toBe(true)
  })

  it('ensureGeneratedSessions returns error when unauthenticated', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: null } })
    const { ensureGeneratedSessions } = await import('@/app/actions/sessions')
    const result = await ensureGeneratedSessions(7)
    expect(result.success).toBe(false)
  })

  it('regenerateSession calls worker with session id', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerRegen.mockResolvedValueOnce({ status: 'ok', workout: { summary_md: 'x' } })
    const { regenerateSession } = await import('@/app/actions/sessions')
    const result = await regenerateSession('sess-1')
    expect(workerRegen).toHaveBeenCalledWith('jwt-1', 'sess-1')
    expect(result.success).toBe(true)
  })
})
```

- [ ] **Step 9.3 — Run, expect FAIL**

```bash
pnpm test tests/unit/actions/sessions.test.ts
```

- [ ] **Step 9.4 — Implement `app/actions/sessions.ts`**

```ts
// app/actions/sessions.ts
'use server'

import { createClient } from '@/lib/supabase/server'
import { workerEnsureSessions, workerRegenerateSession } from '@/lib/worker'

type Result =
  | { success: true; data: unknown }
  | { success: false; error: string }

async function getJwt(): Promise<string | null> {
  const supabase = await createClient()
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

export async function ensureGeneratedSessions(days = 7): Promise<Result> {
  const jwt = await getJwt()
  if (!jwt) return { success: false, error: 'unauthenticated' }
  try {
    const data = await workerEnsureSessions(jwt, days)
    return { success: true, data }
  } catch (e) {
    return { success: false, error: (e as Error).message }
  }
}

export async function regenerateSession(sessionId: string): Promise<Result> {
  const jwt = await getJwt()
  if (!jwt) return { success: false, error: 'unauthenticated' }
  try {
    const data = await workerRegenerateSession(jwt, sessionId)
    return { success: true, data }
  } catch (e) {
    return { success: false, error: (e as Error).message }
  }
}
```

- [ ] **Step 9.5 — Re-run, expect PASS**

```bash
pnpm test tests/unit/actions/sessions.test.ts
```

- [ ] **Step 9.6 — Commit**

```bash
git add lib/worker.ts app/actions/sessions.ts tests/unit/actions/sessions.test.ts
git commit -m "feat(e5): Server Actions ensureGeneratedSessions + regenerateSession"
```

---

## Task 10 — Display in `/today` page

**Files:**
- Modify: `app/(app)/today/page.tsx`

- [ ] **Step 10.1 — Trigger ensureGeneratedSessions on page load**

In `app/(app)/today/page.tsx`, near the top of the RSC body, after `requireOnboarded()`:

```tsx
import { ensureGeneratedSessions } from '@/app/actions/sessions'
// ... other imports

export default async function TodayPage() {
  const userId = await requireOnboarded()
  // Fire-and-forget: kick the worker but don't block the render
  void ensureGeneratedSessions(7).catch(() => undefined)
  // ... rest of the page
}
```

(If `today/page.tsx` currently fetches `planned_sessions`, ensure the fetch reads `workout` JSONB along with the rest.)

- [ ] **Step 10.2 — Render the workout markdown if present**

Below the existing session metadata (sport / type / target):

```tsx
import { workoutToMarkdown } from '@/lib/coach/session-templates'
import type { Workout } from '@/lib/coach/workout-types'

// inside the page, where `session` is rendered:
{session.workout ? (
  <pre className="prose-sm whitespace-pre-wrap rounded-md border p-4 text-sm">
    {workoutToMarkdown(session.workout as Workout, session.sport, session.session_type)}
  </pre>
) : (
  <div className="text-muted-foreground text-sm italic">
    Structure de séance en cours de génération… recharge la page dans quelques secondes.
  </div>
)}
```

Don't add a render emoji — the `No emoji in UI` CI gate will fail.

- [ ] **Step 10.3 — Run typecheck + tests + build**

```bash
pnpm typecheck && pnpm test && pnpm build
```

All must pass.

- [ ] **Step 10.4 — Manual verify in dev**

```bash
pnpm dev
```

Browse `/today`. The page should not crash. With no workout yet generated, you should see the "Structure de séance en cours…" placeholder.

- [ ] **Step 10.5 — Commit**

```bash
git add app/(app)/today/page.tsx
git commit -m "feat(e5): trigger LLM generation + render workout markdown on /today"
```

---

## Task 11 — Display in `/calendar` page + regenerate button

**Files:**
- Modify: `app/(app)/calendar/page.tsx`
- Modify: any client component used for the per-session card (e.g. `app/(app)/_components/session-card.tsx`)

- [ ] **Step 11.1 — Render workout markdown in calendar's session card**

In `session-card.tsx`, after the existing target metadata:

```tsx
{workout && (
  <div className="mt-3">
    <details className="text-sm">
      <summary className="cursor-pointer font-medium">Voir la séance détaillée</summary>
      <pre className="prose-sm mt-2 whitespace-pre-wrap rounded border p-3 text-xs">
        {workoutToMarkdown(workout, sport, sessionType)}
      </pre>
    </details>
  </div>
)}
```

- [ ] **Step 11.2 — Add Regenerate client component**

Create `app/(app)/_components/regenerate-session-button.tsx`:

```tsx
'use client'

import { useState, useTransition } from 'react'
import { Button } from '@/components/ui/button'
import { regenerateSession } from '@/app/actions/sessions'

interface Props {
  sessionId: string
}

export function RegenerateSessionButton({ sessionId }: Readonly<Props>) {
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  function handleClick() {
    setError(null)
    startTransition(async () => {
      const r = await regenerateSession(sessionId)
      if (!r.success) setError(r.error)
    })
  }

  return (
    <div>
      <Button variant="outline" size="sm" onClick={handleClick} disabled={pending}>
        {pending ? 'Régénération…' : 'Régénérer'}
      </Button>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  )
}
```

- [ ] **Step 11.3 — Wire button into session-card**

Add it next to the `Voir la séance détaillée` summary in `session-card.tsx`.

- [ ] **Step 11.4 — Test the button component**

```tsx
// tests/unit/components/regenerate-session-button.test.tsx
// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'

const regen = vi.fn()
vi.mock('@/app/actions/sessions', () => ({
  regenerateSession: (...args: unknown[]) => regen(...args) as unknown,
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => regen.mockReset())

describe('RegenerateSessionButton', () => {
  it('calls regenerateSession on click', async () => {
    regen.mockResolvedValueOnce({ success: true })
    const { RegenerateSessionButton } = await import(
      '@/app/(app)/_components/regenerate-session-button'
    )
    render(<RegenerateSessionButton sessionId="sess-1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Régénérer' }))
    await waitFor(() => {
      expect(regen).toHaveBeenCalledWith('sess-1')
    })
  })

  it('shows error when action fails', async () => {
    regen.mockResolvedValueOnce({ success: false, error: 'oops' })
    const { RegenerateSessionButton } = await import(
      '@/app/(app)/_components/regenerate-session-button'
    )
    render(<RegenerateSessionButton sessionId="sess-1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Régénérer' }))
    await waitFor(() => {
      expect(screen.getByText('oops')).toBeTruthy()
    })
  })
})
```

- [ ] **Step 11.5 — Run all tests + typecheck + lint + build**

```bash
pnpm test && pnpm typecheck && pnpm lint && pnpm build
```

- [ ] **Step 11.6 — Commit**

```bash
git add app/\(app\)/calendar/page.tsx app/\(app\)/_components/session-card.tsx app/\(app\)/_components/regenerate-session-button.tsx tests/unit/components/regenerate-session-button.test.tsx
git commit -m "feat(e5): calendar shows workout markdown + per-session regenerate button"
```

---

## Task 12 — End-to-end validation + deployment

**Files:** None (validation + ops)

- [ ] **Step 12.1 — Set OPENAI_API_KEY in worker `.env`**

On the UNRAID host, edit `/mnt/user/appdata/garmin-sync/.env` to add:

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_S=30
```

Restart the container:

```bash
ssh unraid 'docker restart garmin-sync'
ssh unraid 'docker logs garmin-sync --tail 30'
```

Verify health: `curl https://garmin-sync.tellebma.fr/health` → `{"status":"ok","env":"prod"}`.

- [ ] **Step 12.2 — Smoke test from prod app**

Open https://garmin-training-ia.vercel.app/today as the owner user (signed in). Watch worker logs:

```bash
ssh unraid 'docker logs garmin-sync --tail 50 --follow'
```

Expect a `POST /coach/ensure-sessions` to land. Check that 7 sessions (or however many are pending) come back generated.

In Supabase SQL editor, run:

```sql
select id, date, sport, session_type, workout->>'summary_md' as summary, workout_generated_at
from planned_sessions
where user_id = '<owner-id>' and workout is not null
order by date
limit 10;
```

- [ ] **Step 12.3 — Verify the page renders the markdown**

Reload `/today`. The workout structure should now be visible in markdown. Try the "Régénérer" button on a session in `/calendar` — confirm it produces a different `summary_md`.

- [ ] **Step 12.4 — Open PR**

```bash
gh pr create --title "feat(e5): LLM session generation (OpenAI GPT-4o-mini)" \
  --body "$(cat <<'EOF'
## Summary

Implements EPIC E5: each `planned_session` (produced by E4 Banister) now gets a structured workout (warmup / main intervals / cooldown) generated by OpenAI GPT-4o-mini and rendered locally as FR markdown.

- New migration: `workout jsonb` + `workout_generated_at timestamptz` on `planned_sessions`.
- Worker: `coach/sessions.py` + `openai_client.py` + 2 endpoints (`/coach/ensure-sessions`, `/coach/regenerate-session/:id`).
- Frontend: TS types mirror Pydantic; `lib/coach/session-templates.ts` renders FR markdown; Server Actions wire to worker; `/today` fires generation on page load; `/calendar` adds per-session Regenerate button.

## Test plan

- [ ] Worker pytest suite (incl. mocked OpenAI) — all pass
- [ ] Frontend vitest (incl. component + Server Action tests) — all pass
- [ ] `pnpm build` + `pnpm lint` + `pnpm typecheck` — green
- [ ] Sonar QG green (coverage ≥90%, 0 violations, duplication <3%)
- [ ] Manual: visit /today and /calendar as owner user, confirm structures appear
- [ ] Manual: Régénérer button replaces a workout with a fresh one

EOF
)"
```

- [ ] **Step 12.5 — Monitor CI to green, then merge**

```bash
gh pr checks <PR#>
# When all green:
gh pr merge <PR#> --squash --delete-branch
```

- [ ] **Step 12.6 — Update `CLAUDE.md`**

In the EPIC status table, change:

```
| E5 — Génération séances (LLM) | À planifier |
```

to:

```
| **E5 — Génération séances (LLM)** | ✅ Livré (OpenAI GPT-4o-mini, structures workout JSONB, templates FR) |
```

Commit + push:

```bash
git checkout main && git pull
git add CLAUDE.md
git commit -m "docs(e5): mark EPIC E5 as delivered"
git push
```

---

## Definition of Done

- [ ] Migration applied via Supabase MCP; both columns present
- [ ] Worker tests pass with ≥90% line coverage on `coach/sessions.py`, `coach/openai_client.py`, `coach/workout_schema.py`
- [ ] Frontend tests pass; `session-templates.ts` ≥95% coverage
- [ ] `/today` triggers generation on every visit, renders markdown when available
- [ ] `/calendar` shows the markdown via collapsible detail; Regenerate button works
- [ ] OPENAI_API_KEY deployed to UNRAID, worker container running
- [ ] PR merged on `main`, CI green (Sonar QG OK)
- [ ] `CLAUDE.md` updated; E5 status flipped to ✅

---

## Notes for the engineer

- **OpenAI structured output (`response_format=Workout`)** : OpenAI Python SDK 1.50+ supports passing a Pydantic class directly. The response has `.choices[0].message.parsed` as the validated Pydantic instance. If you hit `client.beta.chat.completions.parse` not found, upgrade `openai>=1.50.0`.
- **Sequential generation** : do NOT parallelize the loop in `ensure_sessions`. OpenAI free tier is 3 req/s; we generate ≤7 per call → ~5s total. If we ever scale to many users, add `asyncio.gather` + concurrency limit.
- **Templating wording** : the FR strings in `session-templates.ts` are good enough for MVP. If the user asks for sport-specific terminology improvements ("fartlek" vs "jeu d'allure"), consult an expert sports agent and replace the strings — the structure stays the same.
- **No emoji in UI** : CI has a `No emoji in UI` gate. The templates render `*summary*` and `> Focus` instead of icons. Do not add 🏃 / 🚴 / 🏊 — they will fail the build.
- **Coverage exclusion** : if the new client component `regenerate-session-button.tsx` is uncovered, add a smoke test (see Step 11.4). Don't blanket-exclude it.
- **`workout` may be null forever** for past sessions — the partial index ignores them. No backfill required.

---

## Self-Review summary

- **Spec coverage** :
  - § 1 Objectif → Tasks 3, 4, 5, 8 cover JSON+markdown pipeline ✅
  - § 2 Critères : ensure /today (Task 10), JSONB validé (Task 3), profil hybride (Task 4 prompt), specificité race (Task 4 prompt), template Python→FR (Task 8), régénérer (Task 11), erreur LLM null (Task 5 `_generate_and_persist`) ✅
  - § 3 Choix → all reflected in tasks ✅
  - § 4 Architecture → Tasks 5/6 worker, Task 10 RSC trigger ✅
  - § 5 Modèle de données → Task 1 ✅
  - § 6 Prompt → Task 4 `_build_user_prompt` + `_SYSTEM_PROMPT` ✅
  - § 7 Frontend templating → Task 8 ✅
  - § 8 Endpoints → Task 6 ✅
  - § 9 Erreurs → Task 5 `_generate_and_persist` + Task 6 fallback error_id ✅
  - § 10 Testing → Tasks 3/4/5/6/7/8/9/11 ✅
  - § 11 Coût → no implementation needed (informational)
  - § 12 Env vars → Task 2 + Task 12.1 ✅
  - § 13 Migrations + deploy → Task 1 + Task 12 ✅
  - § 14 Hors scope → respected (no HRV adjustment, no FIT export)
- **No placeholders** : every step has either code/SQL/command verbatim.
- **Type consistency** : `Workout` / `IntervalBlock` / `IntervalSet` / `IntervalTarget` field names match between `workout_schema.py` (Pydantic) and `workout-types.ts` (TypeScript). `Sport` and `SessionType` are TS-only in `session-templates.ts`; the worker uses the raw DB strings.
