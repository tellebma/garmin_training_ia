# E18 — Console admin & ouverture au public — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `/admin` route (owner-only) that surfaces adoption + AI cost (finops),
lets the owner flip global feature flags (IA kill switch, maintenance mode, temporary
open registration), and manage the registration allowlist — all without touching
Supabase by hand.

**Architecture:** Four phases, each independently mergeable/shippable: (0) a shared
`admins` table + `is_admin_caller()` guard reused everywhere ; (A) finops — usage
instrumentation in the worker + a ground-truth daily pull from OpenAI's Costs API ; (B)
a generic `feature_flags` table with three seeded flags ; (C) allowlist CRUD RPCs ; (D)
the `/admin` page assembling A/B/C, each panel loading independently (own `Suspense` +
skeleton, never a shared blocking `Promise.all`).

**Tech Stack:** Next.js App Router (Server Components + Server Actions), Supabase
Postgres (RLS deny-all + `security definer` RPCs), Python worker (FastAPI, `httpx`,
`openai` SDK, `supabase-py` service-role client), recharts, shadcn/ui.

## Global Constraints

- Spec of record: `docs/superpowers/specs/2026-07-08-e18-console-admin-ouverture-publique-design.md`.
- Every new table gets **RLS enabled, zero policies** (deny-all) — access only via
  `security definer` RPCs, exactly like `allowed_emails` (see
  `supabase/migrations/20260519000000_eauth_password_set_allowlist.sql`).
- Admin gate is the `admins` table (Task 1) + `is_admin_caller()` — **never** a hardcoded
  email, **never** a column on `athlete_profiles` (it already has user-editable RLS
  policies).
- This project has **no local Supabase stack** — migrations are written as SQL files in
  `supabase/migrations/` and applied to the shared remote dev project
  (`peiyrqplymdlmlpsbqzu`) via `mcp__supabase__apply_migration` during development; CI
  (`supabase-migrations.yml`) re-applies idempotently on merge to `main`. There is no
  pgTAP/DB test framework — SQL correctness is verified by applying the migration to the
  dev project and running `mcp__supabase__execute_sql` sanity queries (documented per
  task), plus unit tests on the TypeScript/Python code that *calls* the RPCs (mocked
  `.rpc()`/`.table()`, same pattern as `tests/unit/auth/register-action.test.ts`).
- Frontend data widgets: **one Server Component per widget, own `<Suspense>` + skeleton,
  mounted in parallel** — never added to a page's central blocking `Promise.all` (see
  `app/(app)/today/page.tsx`'s `BriefingLoader` for the reference pattern). This applies
  to every panel built in Phase D.
- Worker instrumentation must be **best-effort**: a failure writing `llm_usage` or
  pulling OpenAI's Costs API must never break session generation or the Garmin sync
  cron (existing pattern: `_run_post_sync_recomputes` in `cron.py`, `notify_discord_error`
  in `alerting.py`).
- Conventional commits, body lines ≤ 100 chars. Work happens in a dedicated git
  worktree (`git worktree add ../garmin_training-e18-admin -b feat/e18-admin-console`),
  never in the main checkout — see `superpowers:using-git-worktrees`.
- Frontend quality gates: `pnpm lint && pnpm typecheck && pnpm build && pnpm test`.
  Worker quality gates: `cd worker && uv run ruff check . && uv run mypy src/ && uv run pytest -v`.

---

## Phase 0 — Shared admin gate

### Task 1: `admins` table + `is_admin_caller()` RPC

**Files:**
- Create: `supabase/migrations/20260708010000_e18_admin_table.sql`

**Interfaces:**
- Produces: SQL function `public.is_admin_caller() returns boolean`, callable via
  `supabase.rpc('is_admin_caller')` from any authenticated session (`grant execute ...
  to authenticated`). Every later RPC in this plan calls it internally as its first
  line and raises `'not authorized'` if it returns `false`.

- [ ] **Step 1: Write the migration**

```sql
-- 20260708010000_e18_admin_table.sql
-- E18 — admin gate: dedicated table (never a column on athlete_profiles, which
-- already has user-editable RLS policies; never a hardcoded email in SQL).

create table public.admins (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  note       text,
  created_at timestamptz not null default now()
);

alter table public.admins enable row level security;
-- Pas de policies : RLS deny-all. Accès uniquement via RPCs security definer.

-- Seed : l'owner devient admin au déploiement de la migration.
insert into public.admins (user_id, note)
select id, 'owner'
from auth.users
where lower(email) = 'pdmtc.bellet@gmail.com'
on conflict (user_id) do nothing;

create or replace function public.is_admin_caller()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (select 1 from public.admins where user_id = auth.uid())
$$;

grant execute on function public.is_admin_caller() to authenticated;
```

- [ ] **Step 2: Apply to the dev project**

Use `mcp__supabase__apply_migration` with `name: "e18_admin_table"` and the SQL above
(project id `peiyrqplymdlmlpsbqzu`).

- [ ] **Step 3: Verify via `execute_sql`**

Run (replace with the owner's real `auth.users.id`, findable via
`select id, email from auth.users where email = 'pdmtc.bellet@gmail.com';`):

```sql
select public.is_admin_caller(); -- run as postgres: not meaningful (no auth.uid() outside a request)
select * from public.admins;     -- expect exactly one row, the owner
```

Expected: one row in `admins` with the owner's `user_id`.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260708010000_e18_admin_table.sql
git commit -m "feat(db): E18 — table admins + is_admin_caller() RPC"
```

---

## Phase A — Finops

### Task 2: `llm_usage` table

**Files:**
- Create: `supabase/migrations/20260708020000_e18_llm_usage.sql`

**Interfaces:**
- Produces: table `public.llm_usage` — worker writes rows directly via the
  service-role client (`db.table("llm_usage").insert(...)`), no RPC needed for writes
  (service role bypasses RLS by design, same as every other worker write).

- [ ] **Step 1: Write the migration**

```sql
-- 20260708020000_e18_llm_usage.sql
create table public.llm_usage (
  id                bigserial primary key,
  user_id           uuid references auth.users(id) on delete set null,
  created_at        timestamptz not null default now(),
  feature           text not null,        -- 'session_workout' in V1 (see spec §0.1)
  model             text not null,        -- e.g. 'gpt-4o-mini'
  prompt_tokens     integer not null check (prompt_tokens >= 0),
  completion_tokens integer not null check (completion_tokens >= 0),
  total_tokens      integer not null check (total_tokens >= 0),
  cost_usd          numeric(10,6) not null check (cost_usd >= 0)
);

create index llm_usage_created_idx on public.llm_usage (created_at desc);
create index llm_usage_feature_created_idx on public.llm_usage (feature, created_at desc);

alter table public.llm_usage enable row level security;
-- Pas de policies : RLS deny-all. Lecture uniquement via admin_overview() (Task 8).
```

- [ ] **Step 2: Apply + verify**

Apply via `mcp__supabase__apply_migration` (name `e18_llm_usage`). Verify:
`select count(*) from public.llm_usage;` → `0`.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260708020000_e18_llm_usage.sql
git commit -m "feat(db): E18 — table llm_usage (finops instrumentation)"
```

### Task 3: Worker — `openai_client.py` returns usage alongside the workout

**Files:**
- Modify: `worker/src/garmin_sync/coach/openai_client.py`
- Test: `worker/tests/coach/test_openai_client.py`

**Interfaces:**
- Produces: `LlmUsage` dataclass (`model: str`, `prompt_tokens: int`,
  `completion_tokens: int`) and `WorkoutResult` dataclass (`workout: Workout`,
  `usage: LlmUsage`). `generate_workout_for_session(...)` now returns `WorkoutResult`
  instead of `Workout`. Consumed by Task 4 (`sessions.py`).
- Consumes: nothing new — same `Workout`, `OpenAIError`, `validate_workout_for_session`
  already imported.

- [ ] **Step 1: Write the failing test**

Add to `worker/tests/coach/test_openai_client.py` (the existing
`test_generate_workout_returns_validated_workout` mock already builds
`mock_client.beta.chat.completions.parse.return_value` — add a `usage` attribute and
assert on the new return shape):

```python
@patch("garmin_sync.coach.openai_client._get_client")
def test_generate_workout_returns_usage_alongside_workout(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_resp = mock_client.beta.chat.completions.parse.return_value
    mock_resp.choices = [
        MagicMock(message=MagicMock(parsed=MagicMock(model_dump=lambda: _workout_dict())))
    ]
    mock_resp.usage = MagicMock(prompt_tokens=1200, completion_tokens=340)

    result = generate_workout_for_session(
        session=_session(), athlete=_athlete_full(), race_context=_race_context()
    )

    assert result.workout.total_duration_s() > 0
    assert result.usage.model == "gpt-4o-mini"
    assert result.usage.prompt_tokens == 1200
    assert result.usage.completion_tokens == 340
```

This references a `_workout_dict()` helper — add it next to the existing `_session()` /
`_race_context()` fixtures in the same test file, extracted from the inline dict already
used in `test_generate_workout_returns_validated_workout` (the big literal starting at
`"warmup": {...}` in the file you already read) so both tests share it:

```python
def _workout_dict():
    return {
        "warmup": {
            "duration_s": 600,
            "target": {
                "label": "Z1", "rpe": 2, "bpm_low": 130, "bpm_high": 145,
                "watts_low": None, "watts_high": None,
                "pace_low_kmh": None, "pace_high_kmh": None,
            },
            "notes": None,
        },
        "main": [
            {
                "duration_s": 1800,
                "target": {
                    "label": "Z2", "rpe": 4, "bpm_low": 150, "bpm_high": 165,
                    "watts_low": None, "watts_high": None,
                    "pace_low_kmh": None, "pace_high_kmh": None,
                },
                "repeat": 1,
                "notes": None,
            }
        ],
        "cooldown": {
            "duration_s": 300,
            "target": {
                "label": "Z1", "rpe": 2, "bpm_low": 130, "bpm_high": 145,
                "watts_low": None, "watts_high": None,
                "pace_low_kmh": None, "pace_high_kmh": None,
            },
            "notes": None,
        },
        "summary_md": "Séance d'endurance de base.",
        "technical_focus": "Reste relâché.",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker && uv run pytest tests/coach/test_openai_client.py::test_generate_workout_returns_usage_alongside_workout -v`
Expected: FAIL — `AttributeError: 'Workout' object has no attribute 'workout'` (current
code returns a bare `Workout`, not something with `.workout`/`.usage`).

- [ ] **Step 3: Implement**

In `worker/src/garmin_sync/coach/openai_client.py`, add near the top (after imports):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class LlmUsage:
    model: str
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class WorkoutResult:
    workout: Workout
    usage: LlmUsage
```

Replace `_call_and_validate` (lines 133-150) with:

```python
def _call_and_validate(
    client: Any, model: str, messages: list[dict[str, str]], session: dict[str, Any]
) -> tuple[Workout, LlmUsage]:
    """One LLM round-trip + validation. Raises OpenAIError on any failure."""
    try:
        resp = client.beta.chat.completions.parse(
            model=model, messages=messages, response_format=Workout
        )
    except Exception as e:
        raise OpenAIError(f"OpenAI call failed: {e}") from e
    usage = LlmUsage(
        model=model,
        prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
        completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
    )
    parsed = resp.choices[0].message.parsed
    if parsed is None:
        raise OpenAIError("OpenAI returned no parsed payload")
    try:
        workout = Workout.model_validate(parsed.model_dump())
        return validate_workout_for_session(workout, session), usage
    except ValueError as e:
        raise OpenAIError(f"OpenAI returned unrealistic workout: {e}") from e
```

Replace the body of `generate_workout_for_session` (lines 153-188) — signature and
docstring stay, only the loop body and return type change:

```python
def generate_workout_for_session(
    *,
    session: dict[str, Any],
    athlete: dict[str, Any],
    race_context: dict[str, Any],
) -> WorkoutResult:
    """Call OpenAI with structured output, retrying with corrective feedback.

    A small model regularly returns a workout that breaks the numeric envelope
    (warmup cap, main-work ratio, total duration). Instead of failing the whole
    session on the first bad draw, re-prompt with the exact validation error so
    the model can self-correct, up to ``openai_max_attempts`` times.

    Only the final, successful attempt's token usage is returned — failed
    attempts also cost tokens but are not summed here (finops V1 is an
    estimate, not a to-the-cent reconciliation; see the openai_billing_snapshot
    ground-truth comparison for the real invoiced amount).
    """
    client = _get_client()
    settings = get_settings()
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(session, athlete, race_context)},
    ]
    last_error: OpenAIError | None = None
    for _ in range(settings.openai_max_attempts):
        try:
            workout, usage = _call_and_validate(client, settings.openai_model, messages, session)
            return WorkoutResult(workout=workout, usage=usage)
        except OpenAIError as e:
            last_error = e
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
    raise last_error or OpenAIError("workout generation failed")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker && uv run pytest tests/coach/test_openai_client.py -v`
Expected: all tests PASS, including `test_generate_workout_returns_validated_workout`
which must be updated in the same pass — it currently asserts on a bare `Workout`:
change its final assertions from `workout = generate_workout_for_session(...)` /
`assert workout.total_duration_s() ...` to `result = generate_workout_for_session(...)`
/ `assert result.workout.total_duration_s() ...`.

- [ ] **Step 5: Commit**

```bash
cd worker && git add src/garmin_sync/coach/openai_client.py tests/coach/test_openai_client.py
git commit -m "feat(worker): openai_client returns token usage alongside the workout"
```

### Task 4: Worker — `record_llm_usage` + wire into `sessions.py`

**Files:**
- Create: `worker/src/garmin_sync/coach/llm_pricing.py`
- Create: `worker/src/garmin_sync/coach/llm_usage.py`
- Modify: `worker/src/garmin_sync/coach/sessions.py:139-165` (`_generate_and_persist`),
  `:168-208` (`ensure_sessions`), `:211-245` (`regenerate_session`)
- Test: `worker/tests/coach/test_llm_pricing.py`
- Test: `worker/tests/coach/test_llm_usage.py`
- Test: `worker/tests/coach/test_sessions.py`

**Interfaces:**
- Consumes: `WorkoutResult`/`LlmUsage` from Task 3; `get_admin_client()` from
  `supabase_client.py`; `capture()` from `observability.py`.
- Produces: `compute_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) ->
  float` and `MODEL_PRICING: dict[str, dict[str, float]]` (`llm_pricing.py`);
  `record_llm_usage(*, user_id: str, feature: str, model: str, prompt_tokens: int,
  completion_tokens: int) -> None` (`llm_usage.py`, best-effort, never raises).

- [ ] **Step 1: Write the failing tests — pricing**

`worker/tests/coach/test_llm_pricing.py`:

```python
from garmin_sync.coach.llm_pricing import compute_cost_usd


def test_compute_cost_usd_known_model():
    cost = compute_cost_usd("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == 0.15 + 0.60


def test_compute_cost_usd_unknown_model_returns_zero():
    assert compute_cost_usd("some-future-model", prompt_tokens=1000, completion_tokens=1000) == 0.0


def test_compute_cost_usd_zero_tokens():
    assert compute_cost_usd("gpt-4o-mini", prompt_tokens=0, completion_tokens=0) == 0.0
```

- [ ] **Step 2: Run — verify it fails**

Run: `cd worker && uv run pytest tests/coach/test_llm_pricing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'garmin_sync.coach.llm_pricing'`.

- [ ] **Step 3: Implement pricing**

`worker/src/garmin_sync/coach/llm_pricing.py`:

```python
"""Versioned USD/1M-token pricing per OpenAI model — updated by hand on price changes."""

from __future__ import annotations

MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60},
}


def compute_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Returns 0.0 for an unknown model rather than raising — cost tracking must
    never block generation on a pricing table that hasn't caught up yet."""
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return 0.0
    return (prompt_tokens / 1_000_000) * pricing["input_per_1m"] + (
        completion_tokens / 1_000_000
    ) * pricing["output_per_1m"]
```

- [ ] **Step 4: Run — verify pricing tests pass**

Run: `cd worker && uv run pytest tests/coach/test_llm_pricing.py -v` → PASS.

- [ ] **Step 5: Write the failing tests — record_llm_usage**

`worker/tests/coach/test_llm_usage.py`:

```python
from unittest.mock import MagicMock, patch

from garmin_sync.coach.llm_usage import record_llm_usage


@patch("garmin_sync.coach.llm_usage.get_admin_client")
def test_record_llm_usage_writes_expected_row(mock_get_client):
    mock_db = MagicMock()
    mock_get_client.return_value = mock_db

    record_llm_usage(
        user_id="u1",
        feature="session_workout",
        model="gpt-4o-mini",
        prompt_tokens=1000,
        completion_tokens=200,
    )

    mock_db.table.assert_called_once_with("llm_usage")
    insert_call = mock_db.table.return_value.insert
    payload = insert_call.call_args.args[0]
    assert payload["user_id"] == "u1"
    assert payload["feature"] == "session_workout"
    assert payload["model"] == "gpt-4o-mini"
    assert payload["prompt_tokens"] == 1000
    assert payload["completion_tokens"] == 200
    assert payload["total_tokens"] == 1200
    assert payload["cost_usd"] > 0


@patch("garmin_sync.coach.llm_usage.capture")
@patch("garmin_sync.coach.llm_usage.get_admin_client")
def test_record_llm_usage_swallows_write_failure(mock_get_client, mock_capture):
    mock_get_client.side_effect = RuntimeError("db down")

    # must not raise
    record_llm_usage(
        user_id="u1", feature="session_workout", model="gpt-4o-mini",
        prompt_tokens=10, completion_tokens=5,
    )

    mock_capture.assert_called_once()
    assert mock_capture.call_args.kwargs["where"] == "record_llm_usage"
```

- [ ] **Step 6: Run — verify it fails**

Run: `cd worker && uv run pytest tests/coach/test_llm_usage.py -v`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 7: Implement `record_llm_usage`**

`worker/src/garmin_sync/coach/llm_usage.py`:

```python
"""Persists LLM token usage for finops (E18). Best-effort — never raises."""

from __future__ import annotations

import logging

from garmin_sync.coach.llm_pricing import compute_cost_usd
from garmin_sync.observability import capture
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger("garmin_sync")


def record_llm_usage(
    *,
    user_id: str,
    feature: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    try:
        db = get_admin_client()
        db.table("llm_usage").insert(
            {
                "user_id": user_id,
                "feature": feature,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "cost_usd": compute_cost_usd(model, prompt_tokens, completion_tokens),
            }
        ).execute()
    except Exception as exc:
        log.exception("record_llm_usage failed user=%s feature=%s", user_id, feature)
        capture(exc, where="record_llm_usage", user_id=user_id, feature=feature)
```

- [ ] **Step 8: Run — verify usage tests pass**

Run: `cd worker && uv run pytest tests/coach/test_llm_usage.py -v` → PASS.

- [ ] **Step 9: Wire into `sessions.py` — update existing tests + add new ones**

`generate_workout_for_session` now returns `WorkoutResult` instead of a bare workout
object, so **every existing test in `test_sessions.py` that sets `mock_gen.return_value`
or `mock_gen.side_effect` to a successful result must be updated**, not just have new
tests added. Add this import and helper near the top of
`worker/tests/coach/test_sessions.py` (after the existing `from garmin_sync.coach.sessions
import (...)` block):

```python
from garmin_sync.coach.openai_client import LlmUsage, WorkoutResult


def _workout_result(workout_dict=None):
    return WorkoutResult(
        workout=MagicMock(model_dump=lambda: workout_dict or _mock_workout()),
        usage=LlmUsage(model="gpt-4o-mini", prompt_tokens=100, completion_tokens=50),
    )
```

Then apply these exact edits to the four existing tests whose success path reaches a
real generation (leave every other test — the ones that only exercise skip/error/
not-found paths — untouched):

1. `test_ensure_sessions_generates_for_each_pending` (currently line 49): add
   `@patch("garmin_sync.coach.sessions.record_llm_usage")` as a new **topmost**
   decorator, add `mock_record` as the new last parameter, replace the
   `workout_obj = MagicMock(...)` / `mock_gen.return_value = workout_obj` lines with
   `mock_gen.return_value = _workout_result()`, and add
   `assert mock_record.call_count == 2` at the end:

```python
@patch("garmin_sync.coach.sessions.record_llm_usage")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_generates_for_each_pending(mock_db, mock_gen, mock_record):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [
        {
            "id": "s1", "sport": "run", "session_type": "endurance",
            "target_duration_s": 3000, "target_tss": 50, "phase": "base",
            "date": "2026-05-21",
        },
        {
            "id": "s2", "sport": "bike", "session_type": "long",
            "target_duration_s": 7200, "target_tss": 120, "phase": "base",
            "date": "2026-05-22",
        },
    ]
    _profile_chain(db).data = {
        "ftp_watts": 240, "vma_kmh": 17.0, "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }
    _race_chain(db).data = {
        "discipline": "triathlon", "total_elevation_gain_m": 350, "race_date": "2026-08-15",
    }

    mock_gen.return_value = _workout_result()

    result = ensure_sessions(user_id="u1", days=7)
    assert result["generated_count"] == 2
    assert mock_gen.call_count == 2
    assert mock_record.call_count == 2
```

2. `test_ensure_sessions_continues_on_error` (currently line 117): same decorator
   addition, and change `mock_gen.side_effect = [OpenAIError("boom"), workout_obj]` to
   `mock_gen.side_effect = [OpenAIError("boom"), _workout_result()]`; add
   `mock_record.assert_called_once()` at the end (only the second, successful attempt
   records usage):

```python
@patch("garmin_sync.coach.sessions.record_llm_usage")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_continues_on_error(mock_db, mock_gen, mock_record):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [
        {
            "id": "s1", "sport": "run", "session_type": "endurance",
            "target_duration_s": 3000, "target_tss": 50, "phase": "base",
            "date": "2026-05-21",
        },
        {
            "id": "s2", "sport": "bike", "session_type": "long",
            "target_duration_s": 7200, "target_tss": 120, "phase": "base",
            "date": "2026-05-22",
        },
    ]
    _profile_chain(db).data = {
        "ftp_watts": 240, "vma_kmh": 17.0, "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }
    _race_chain(db).data = None

    from garmin_sync.coach.openai_client import OpenAIError

    mock_gen.side_effect = [OpenAIError("boom"), _workout_result()]

    result = ensure_sessions(user_id="u1", days=7)
    assert result["generated_count"] == 1
    assert result["failed_count"] == 1
    mock_record.assert_called_once()
```

3. `test_ensure_sessions_passes_activity_review_to_generation` (currently line 204):
   add the `record_llm_usage` patch as the new topmost decorator (so `mock_record`
   becomes the 4th parameter, after the existing `mock_review`), and replace
   `mock_gen.return_value = MagicMock(model_dump=lambda: _mock_workout())` with
   `mock_gen.return_value = _workout_result()`. Everything else in this test (the
   `call_kwargs = mock_gen.call_args.kwargs` assertions) is unaffected since those read
   the *arguments* `generate_workout_for_session` was called with, not its return value.

```python
@patch("garmin_sync.coach.sessions.record_llm_usage")
@patch("garmin_sync.coach.sessions._load_activity_review")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_passes_activity_review_to_generation(mock_db, mock_gen, mock_review, mock_record):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [
        {
            "id": "s1", "sport": "run", "session_type": "intervals",
            "target_duration_s": 3000, "target_tss": 50, "phase": "base",
            "date": "2026-05-21",
        }
    ]
    _profile_chain(db).data = {
        "ftp_watts": 240, "vma_kmh": 17.0, "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }
    _race_chain(db).data = {
        "discipline": "triathlon", "total_elevation_gain_m": 350, "race_date": "2026-08-15",
    }
    mock_review.return_value = ActivityReview(
        lookback_days=90,
        activities_7d=2,
        activities_28d=6,
        tss_7d=220,
        avg_weekly_tss_prev_21d=120,
        elevation_gain_7d=800,
        avg_weekly_elevation_prev_21d=300,
        sport_counts_28d={"run": 4, "bike": 2},
        days_since_last_activity=1,
        insights=[
            ActivityInsight(
                "load_spike", "risk",
                "Charge récente nettement au-dessus de la tendance.", -10,
            )
        ],
    )
    mock_gen.return_value = _workout_result()

    result = ensure_sessions(user_id="u1", days=7)

    assert result["generated_count"] == 1
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs["race_context"]["activity_review"]["activities_7d"] == 2
    assert "coach_context" in call_kwargs["session"]
    assert "Charge récente" in call_kwargs["session"]["coach_context"]
    assert "Ajustement coach proposé" in call_kwargs["session"]["coach_context"]
    assert "baisse l'intensité" in call_kwargs["session"]["coach_context"]
    mock_record.assert_called_once()
```

4. `test_regenerate_session_updates_existing` (currently line 264): add the
   `record_llm_usage` patch as the new topmost decorator, replace
   `mock_gen.return_value = MagicMock(model_dump=lambda: _mock_workout())` with
   `mock_gen.return_value = _workout_result()`, and assert the recorded usage:

```python
@patch("garmin_sync.coach.sessions.record_llm_usage")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_regenerate_session_updates_existing(mock_db, mock_gen, mock_record):
    db = MagicMock()
    mock_db.return_value = db
    session_lookup = db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value  # noqa: E501
    session_lookup.data = {
        "id": "s1", "user_id": "u1", "sport": "run", "session_type": "intervals",
        "target_duration_s": 3600, "target_tss": 80, "phase": "peak", "date": "2026-05-25",
    }
    _profile_chain(db).data = {
        "ftp_watts": 240, "vma_kmh": 17.0, "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }
    _race_chain(db).data = None
    mock_gen.return_value = _workout_result()

    result = regenerate_session(user_id="u1", session_id="s1")
    assert result["status"] == "ok"
    mock_gen.assert_called_once()
    mock_record.assert_called_once_with(
        user_id="u1", feature="session_workout", model="gpt-4o-mini",
        prompt_tokens=100, completion_tokens=50,
    )
```

- [ ] **Step 10: Run — verify it fails**

Run: `cd worker && uv run pytest tests/coach/test_sessions.py -v`
Expected: FAIL — `_generate_and_persist`/`regenerate_session` don't call
`record_llm_usage` yet (`mock_record.assert_called_*` assertions fail), and the four
updated tests are exercising the still-unwired production code.

- [ ] **Step 11: Implement wiring**

In `worker/src/garmin_sync/coach/sessions.py`, add imports:

```python
from garmin_sync.coach.llm_usage import record_llm_usage
```

Change `_generate_and_persist` (add a `user_id` parameter, since the `session` dict has
no `user_id` column selected — `ensure_sessions` already has it in scope):

```python
def _generate_and_persist(
    db: Any,
    session: dict[str, Any],
    athlete: dict[str, Any],
    race_ctx: dict[str, Any],
    user_id: str,
) -> bool:
    try:
        result = generate_workout_for_session(
            session=session, athlete=athlete, race_context=race_ctx
        )
    except OpenAIError as e:
        log.exception("openai failed for session=%s: %s", session["id"], e)
        capture(
            e,
            where="ensure_sessions",
            session_id=session["id"],
            sport=session.get("sport"),
            session_type=session.get("session_type"),
        )
        return False
    db.table("planned_sessions").update(
        {
            "workout": result.workout.model_dump(),
            "workout_generated_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", session["id"]).execute()
    record_llm_usage(
        user_id=user_id,
        feature="session_workout",
        model=result.usage.model,
        prompt_tokens=result.usage.prompt_tokens,
        completion_tokens=result.usage.completion_tokens,
    )
    return True
```

Update the one call site inside `ensure_sessions` (in the `for session in generatable:`
loop):

```python
        if _generate_and_persist(db, session_for_generation, athlete, race_ctx, user_id):
```

Update `regenerate_session` (unpack `WorkoutResult` and record usage before returning):

```python
    result = generate_workout_for_session(
        session=session_for_generation, athlete=athlete, race_context=race_ctx
    )
    db.table("planned_sessions").update(
        {
            "workout": result.workout.model_dump(),
            "workout_generated_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", session_id).execute()
    record_llm_usage(
        user_id=user_id,
        feature="session_workout",
        model=result.usage.model,
        prompt_tokens=result.usage.prompt_tokens,
        completion_tokens=result.usage.completion_tokens,
    )
    return {"status": "ok", "workout": result.workout.model_dump()}
```

- [ ] **Step 12: Run full coach test suite**

Run: `cd worker && uv run pytest tests/coach/ -v`
Expected: all PASS.

- [ ] **Step 13: Commit**

```bash
cd worker && git add src/garmin_sync/coach/llm_pricing.py src/garmin_sync/coach/llm_usage.py \
  src/garmin_sync/coach/sessions.py tests/coach/test_llm_pricing.py \
  tests/coach/test_llm_usage.py tests/coach/test_sessions.py
git commit -m "feat(worker): record LLM token usage + cost after each session generation"
```

### Task 5: `openai_billing_snapshot` table

**Files:**
- Create: `supabase/migrations/20260708030000_e18_openai_billing_snapshot.sql`

**Interfaces:**
- Produces: table `public.openai_billing_snapshot`, written by the worker's
  `billing_sync.py` (Task 7) via the service-role client (upsert by `billing_date`).

- [ ] **Step 1: Write the migration**

```sql
-- 20260708030000_e18_openai_billing_snapshot.sql
create table public.openai_billing_snapshot (
  billing_date date primary key,
  cost_usd     numeric(10,6) not null check (cost_usd >= 0),
  fetched_at   timestamptz not null default now()
);

alter table public.openai_billing_snapshot enable row level security;
-- Pas de policies : RLS deny-all. Lecture uniquement via admin_overview() (Task 8).
```

- [ ] **Step 2: Apply + verify**

Apply via `mcp__supabase__apply_migration` (name `e18_openai_billing_snapshot`). Verify:
`select count(*) from public.openai_billing_snapshot;` → `0`.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260708030000_e18_openai_billing_snapshot.sql
git commit -m "feat(db): E18 — table openai_billing_snapshot (ground-truth cost)"
```

### Task 6: Worker config — `OPENAI_ADMIN_API_KEY`

**Files:**
- Modify: `worker/src/garmin_sync/config.py:31` (right after `openai_api_key`)
- Modify: `worker/.env.example` (add the new var, documented)
- Test: `worker/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.openai_admin_api_key: SecretStr` (default empty, same pattern as
  `openai_api_key`), accessed via `get_settings().openai_admin_api_key.get_secret_value()`.

- [ ] **Step 1: Write the failing test**

Add to `worker/tests/test_config.py`, mirroring the existing
`test_settings_loads_openai_config` (which sets `OPENAI_API_KEY` via `monkeypatch` and
reads it back through `get_settings()`):

```python
def test_settings_loads_openai_admin_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_ADMIN_API_KEY", "sk-admin-test")
    get_settings.cache_clear()
    s = get_settings()
    assert s.openai_admin_api_key.get_secret_value() == "sk-admin-test"


def test_settings_openai_admin_api_key_defaults_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_ADMIN_API_KEY", raising=False)
    get_settings.cache_clear()
    s = get_settings()
    assert s.openai_admin_api_key.get_secret_value() == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd worker && uv run pytest tests/test_config.py -k openai_admin_api_key -v`
Expected: FAIL — `ValidationError`/`AttributeError`, `openai_admin_api_key` doesn't exist
on `Settings` yet.

- [ ] **Step 3: Implement**

Add right after line 31 (`openai_api_key: SecretStr = Field(default=SecretStr(""))`) in
`worker/src/garmin_sync/config.py`:

```python
    openai_admin_api_key: SecretStr = Field(default=SecretStr(""))
```

- [ ] **Step 4: Document in `.env.example`**

Add a line near the existing `OPENAI_API_KEY` entry in `worker/.env.example`:

```
# Organization admin key (different from OPENAI_API_KEY) — read-only access to the
# Costs API, used by billing_sync.py for ground-truth finops. Never exposed to the front.
OPENAI_ADMIN_API_KEY=
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd worker && uv run pytest tests/test_config.py -v` → all PASS (including the two
new tests and every pre-existing one — the new field has a default, so it can't break
`test_settings_loads_from_env`'s construction of a bare `Settings()`).

- [ ] **Step 6: Commit**

```bash
cd worker && git add src/garmin_sync/config.py .env.example tests/test_config.py
git commit -m "feat(worker): add OPENAI_ADMIN_API_KEY setting for Costs API access"
```

### Task 7: Worker — `billing_sync.py` (ground-truth OpenAI cost pull)

**Files:**
- Create: `worker/src/garmin_sync/billing_sync.py`
- Modify: `worker/src/garmin_sync/cron.py` (add `run_billing_sync_cron` + `_MODES` entry)
- Test: `worker/tests/test_billing_sync.py`

**Interfaces:**
- Consumes: `get_settings().openai_admin_api_key` (Task 6), `get_admin_client()`
  (`supabase_client.py`), `capture()` (`observability.py`).
- Produces: `run_billing_sync_cron() -> dict[str, Any]` added to `cron.py`'s `_MODES`
  under key `"billing"` (invoked as `python -m garmin_sync.cron billing`).

- [ ] **Step 1: Write the failing tests**

`worker/tests/test_billing_sync.py` — mirrors `worker/tests/test_alerting.py`'s
`patch.object(module, "httpx")` style:

```python
from unittest.mock import MagicMock, patch

from garmin_sync import billing_sync


def _settings():
    m = MagicMock()
    m.openai_admin_api_key.get_secret_value.return_value = "sk-admin-test"
    return m


def _openai_response(buckets):
    return MagicMock(
        status_code=200,
        json=lambda: {"data": buckets},
        raise_for_status=lambda: None,
    )


@patch("garmin_sync.billing_sync.get_admin_client")
@patch("garmin_sync.billing_sync.get_settings", return_value=_settings())
@patch.object(billing_sync, "httpx")
def test_billing_sync_upserts_daily_cost(mock_httpx, _mock_settings, mock_get_client):
    mock_httpx.get.return_value = _openai_response(
        [
            {"start_time": 1735689600, "results": [{"amount": {"value": 0.42}}]},
        ]
    )
    mock_db = MagicMock()
    mock_get_client.return_value = mock_db

    result = billing_sync.run_billing_sync_cron()

    mock_db.table.assert_called_with("openai_billing_snapshot")
    upsert_call = mock_db.table.return_value.upsert
    assert upsert_call.called
    rows = upsert_call.call_args.args[0]
    assert any(row["cost_usd"] == 0.42 for row in rows)
    assert result["status"] == "ok"


@patch("garmin_sync.billing_sync.get_admin_client")
@patch("garmin_sync.billing_sync.get_settings", return_value=_settings())
@patch.object(billing_sync, "httpx")
@patch("garmin_sync.billing_sync.capture")
def test_billing_sync_swallows_openai_failure(mock_capture, mock_httpx, _mock_settings, mock_get_client):
    mock_httpx.get.side_effect = RuntimeError("network down")

    result = billing_sync.run_billing_sync_cron()

    mock_capture.assert_called_once()
    assert result["status"] == "error"
    mock_get_client.return_value.table.assert_not_called()


@patch("garmin_sync.billing_sync.get_settings")
def test_billing_sync_skips_when_key_unset(mock_get_settings):
    m = MagicMock()
    m.openai_admin_api_key.get_secret_value.return_value = ""
    mock_get_settings.return_value = m

    result = billing_sync.run_billing_sync_cron()

    assert result["status"] == "skipped_no_key"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd worker && uv run pytest tests/test_billing_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'garmin_sync.billing_sync'`.

- [ ] **Step 3: Implement**

`worker/src/garmin_sync/billing_sync.py`:

```python
"""Daily ground-truth pull of OpenAI's real invoiced cost (E18 finops).

Best-effort, mirrors alerting.py's style: never raises into the cron caller.
Re-pulls the last few days on every run (upsert by billing_date) because
OpenAI's Costs API has ~24-48h of billing delay — a day fetched "final" at
05:00 UTC can still be revised the next run.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from garmin_sync.config import get_settings
from garmin_sync.observability import capture
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger("garmin_sync")

_COSTS_URL = "https://api.openai.com/v1/organization/costs"
_LOOKBACK_DAYS = 4
_TIMEOUT_S = 15.0


def _fetch_daily_costs(api_key: str, start_time: int) -> list[dict[str, Any]]:
    response = httpx.get(
        _COSTS_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        params={"start_time": start_time, "bucket_width": "1d", "limit": _LOOKBACK_DAYS + 1},
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    return response.json().get("data", [])


def _bucket_to_row(bucket: dict[str, Any]) -> dict[str, Any]:
    billing_date = datetime.fromtimestamp(bucket["start_time"], tz=UTC).date().isoformat()
    total = sum(r.get("amount", {}).get("value", 0.0) for r in bucket.get("results", []))
    return {"billing_date": billing_date, "cost_usd": round(total, 6)}


def run_billing_sync_cron() -> dict[str, Any]:
    settings = get_settings()
    api_key = settings.openai_admin_api_key.get_secret_value()
    if not api_key:
        return {"status": "skipped_no_key"}

    start_time = int((datetime.now(UTC) - timedelta(days=_LOOKBACK_DAYS)).timestamp())
    try:
        buckets = _fetch_daily_costs(api_key, start_time)
        rows = [_bucket_to_row(b) for b in buckets]
        if rows:
            db = get_admin_client()
            db.table("openai_billing_snapshot").upsert(rows, on_conflict="billing_date").execute()
        return {"status": "ok", "days_upserted": len(rows)}
    except Exception as exc:
        log.exception("billing_sync failed")
        capture(exc, where="billing_sync")
        return {"status": "error"}
```

- [ ] **Step 4: Run to verify tests pass**

Run: `cd worker && uv run pytest tests/test_billing_sync.py -v` → PASS.

- [ ] **Step 5: Wire into `cron.py`**

In `worker/src/garmin_sync/cron.py`, add near the other cron functions (after
`run_profile_sync_cron`, before `_MODES`):

```python
def run_billing_sync_cron() -> dict[str, Any]:
    """Daily ground-truth OpenAI cost pull (E18 finops). ~05:00 UTC, alongside full sync."""
    from garmin_sync.billing_sync import run_billing_sync_cron as _run

    return _run()
```

Update `_MODES`:

```python
_MODES = {
    "full": run_daily_cron,
    "sleep": run_sleep_cron,
    "activities": run_activities_cron,
    "profile": run_profile_sync_cron,
    "billing": run_billing_sync_cron,
}
```

- [ ] **Step 6: Run worker test suite**

Run: `cd worker && uv run pytest -v` → all PASS.
Run: `cd worker && uv run ruff check . && uv run mypy src/` → clean.

- [ ] **Step 7: Commit**

```bash
cd worker && git add src/garmin_sync/billing_sync.py src/garmin_sync/cron.py \
  tests/test_billing_sync.py
git commit -m "feat(worker): daily ground-truth OpenAI cost pull (billing_sync cron)"
```

> **Infra note (not code, flag to the owner):** this adds a 5th cron mode. The actual
> scheduling (UNRAID User Scripts / systemd timer) is external to this repo — add a
> `docker exec garmin-sync python -m garmin_sync.cron billing` entry alongside the
> existing daily trigger when deploying this phase.

### Task 8: `admin_overview()` RPC

**Files:**
- Create: `supabase/migrations/20260708040000_e18_admin_overview.sql`

**Interfaces:**
- Produces: RPC `admin_overview()` (`security definer`, guarded by `is_admin_caller()`),
  `grant execute ... to authenticated`. Consumed by Task 9 (`FinopsPanel`).

- [ ] **Step 1: Write the migration**

```sql
-- 20260708040000_e18_admin_overview.sql
create or replace function public.admin_overview()
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  result jsonb;
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;

  select jsonb_build_object(
    'users', jsonb_build_object(
      'total', (select count(*) from public.athlete_profiles),
      'active_7d', (
        select count(distinct user_id) from (
          select user_id from public.activities where start_time > now() - interval '7 days'
          union
          select user_id from public.garmin_credentials where last_sync_at > now() - interval '7 days'
        ) active
      )
    ),
    'activities', jsonb_build_object(
      'total', (select count(*) from public.activities),
      'last_7d', (select count(*) from public.activities where start_time > now() - interval '7 days')
    ),
    'llm_estimated', jsonb_build_object(
      'total_tokens_7d', (
        select coalesce(sum(total_tokens), 0) from public.llm_usage
        where created_at > now() - interval '7 days'
      ),
      'cost_usd_7d', (
        select coalesce(sum(cost_usd), 0) from public.llm_usage
        where created_at > now() - interval '7 days'
      )
    ),
    'llm_billed', jsonb_build_object(
      'cost_usd_7d', (
        select coalesce(sum(cost_usd), 0) from public.openai_billing_snapshot
        where billing_date > (current_date - interval '7 days')
      )
    ),
    'sync_health', jsonb_build_object(
      'ok', (select count(*) from public.garmin_credentials where last_sync_status = 'ok'),
      'failed', (
        select count(*) from public.garmin_credentials
        where last_sync_status is not null and last_sync_status != 'ok'
      )
    ),
    'cost_per_day_7d', (
      select coalesce(jsonb_agg(jsonb_build_object('date', d.date, 'cost_usd', coalesce(u.cost_usd, 0))), '[]'::jsonb)
      from (
        select (current_date - i)::date as date from generate_series(0, 6) as i
      ) d
      left join (
        select created_at::date as date, sum(cost_usd) as cost_usd
        from public.llm_usage
        where created_at > now() - interval '7 days'
        group by created_at::date
      ) u on u.date = d.date
      order by d.date
    )
  ) into result;

  return result;
end;
$$;

grant execute on function public.admin_overview() to authenticated;
```

- [ ] **Step 2: Apply + verify**

Apply via `mcp__supabase__apply_migration` (name `e18_admin_overview`). Verify as a
non-admin fails and as the owner succeeds:

```sql
-- As postgres (bypasses RLS/RPC caller check — sanity-check the shape only):
select public.admin_overview(); -- will raise 'not authorized' since auth.uid() is null outside a request; that's expected here — real verification happens from the frontend in Task 9/18 once logged in as the owner.
```

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260708040000_e18_admin_overview.sql
git commit -m "feat(db): E18 — admin_overview() RPC (users/activities/cost estimé+facturé)"
```

### Task 9: Frontend — `FinopsPanel` + `CostPerDayChart`

**Files:**
- Create: `lib/admin/types.ts`
- Create: `app/(app)/admin/_components/charts/cost-per-day-chart.tsx`
- Create: `app/(app)/admin/_components/finops-panel.tsx`
- Create: `app/(app)/admin/_components/skeletons/finops-panel-skeleton.tsx`
- Test: `tests/unit/admin/finops-panel.test.tsx` (if component tests are RTL-based —
  check `tests/unit/onboarding/components/onboarding-wizard.test.tsx` for the exact
  RTL setup used in this repo and mirror it)

**Interfaces:**
- Produces: `AdminOverview` type (`lib/admin/types.ts`); `<FinopsPanel />` async Server
  Component (no props — calls `admin_overview()` itself); consumed directly by Task 18
  (page assembly), each wrapped in its own `<Suspense>`.

- [ ] **Step 1: Define the DTO type**

`lib/admin/types.ts`:

```typescript
export interface CostPerDayPoint {
  date: string
  cost_usd: number
}

export interface AdminOverview {
  users: { total: number; active_7d: number }
  activities: { total: number; last_7d: number }
  llm_estimated: { total_tokens_7d: number; cost_usd_7d: number }
  llm_billed: { cost_usd_7d: number }
  sync_health: { ok: number; failed: number }
  cost_per_day_7d: CostPerDayPoint[]
}
```

- [ ] **Step 2: Chart component**

`app/(app)/admin/_components/charts/cost-per-day-chart.tsx` (copied structure from
`app/(app)/_components/charts/banister-chart.tsx`, one series instead of three):

```tsx
'use client'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CostPerDayPoint } from '@/lib/admin/types'

interface CostPerDayChartProps {
  readonly data: CostPerDayPoint[]
  readonly height?: number
}

export function CostPerDayChart({ data, height = 200 }: CostPerDayChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10 }}
          interval="preserveStartEnd"
          tickFormatter={(s: string) => s.slice(5)}
        />
        <YAxis tick={{ fontSize: 10 }} />
        <Tooltip
          contentStyle={{
            background: 'var(--card)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            fontSize: 12,
          }}
          formatter={(value: number) => [`$${value.toFixed(4)}`, 'Coût estimé']}
        />
        <Bar dataKey="cost_usd" fill="var(--chart-1)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 3: Skeleton**

`app/(app)/admin/_components/skeletons/finops-panel-skeleton.tsx`:

```tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '@/app/(app)/_components/skeletons/loading-region'

export function FinopsPanelSkeleton() {
  return (
    <LoadingRegion label="Chargement des indicateurs finops">
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {['users', 'activities', 'cost-est', 'cost-billed'].map((key) => (
            <div key={key} className="space-y-2 rounded-lg border p-4">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-7 w-16" />
            </div>
          ))}
        </div>
        <Skeleton className="h-52 w-full rounded-md" />
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 4: Panel (async Server Component)**

`app/(app)/admin/_components/finops-panel.tsx`:

```tsx
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { createClient } from '@/lib/supabase/server'
import { CostPerDayChart } from './charts/cost-per-day-chart'
import type { AdminOverview } from '@/lib/admin/types'

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`
}

export async function FinopsPanel() {
  const supabase = await createClient()
  const { data, error } = await supabase.rpc('admin_overview')
  if (error || !data) {
    return <p className="text-destructive text-sm">Impossible de charger les indicateurs finops.</p>
  }
  const overview = data as AdminOverview

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold">Finops</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Utilisateurs</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{overview.users.total}</p>
            <p className="text-muted-foreground text-xs">{overview.users.active_7d} actifs sur 7j</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Activités</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{overview.activities.total}</p>
            <p className="text-muted-foreground text-xs">{overview.activities.last_7d} sur 7j</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Coût IA estimé (7j)</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{formatUsd(overview.llm_estimated.cost_usd_7d)}</p>
            <p className="text-muted-foreground text-xs">
              {overview.llm_estimated.total_tokens_7d.toLocaleString('fr-FR')} tokens
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Coût IA facturé (7j)</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{formatUsd(overview.llm_billed.cost_usd_7d)}</p>
            <p className="text-muted-foreground text-xs">Source OpenAI, délai ~24-48h</p>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader><CardTitle className="text-sm font-medium">Coût estimé / jour (7j)</CardTitle></CardHeader>
        <CardContent>
          <CostPerDayChart data={overview.cost_per_day_7d} />
        </CardContent>
      </Card>
    </section>
  )
}
```

- [ ] **Step 5: Typecheck + build**

Run: `pnpm typecheck` → clean (this file isn't mounted anywhere yet, but must compile
standalone).

- [ ] **Step 6: Commit**

```bash
git add lib/admin/types.ts app/"(app)"/admin/_components/charts/cost-per-day-chart.tsx \
  app/"(app)"/admin/_components/finops-panel.tsx \
  app/"(app)"/admin/_components/skeletons/finops-panel-skeleton.tsx
git commit -m "feat(admin): FinopsPanel — users/activities/cost estimé vs facturé"
```

---

## Phase B — Feature flags

### Task 10: `feature_flags` table + `is_feature_flag_active()` + admin RPCs + seed

**Files:**
- Create: `supabase/migrations/20260708050000_e18_feature_flags.sql`

**Interfaces:**
- Produces: table `public.feature_flags`; RPC `is_feature_flag_active(p_key text)
  returns boolean` (`grant ... to authenticated` — used directly by the frontend
  maintenance-mode check in Task 13); RPCs `admin_list_feature_flags()` and
  `admin_set_feature_flag(p_key text, p_enabled boolean, p_expires_at timestamptz)`
  (both admin-gated). Seeds `llm_generation_enabled`, `maintenance_mode`,
  `public_registration_enabled` (all `enabled = false` by default).

- [ ] **Step 1: Write the migration**

```sql
-- 20260708050000_e18_feature_flags.sql
create table public.feature_flags (
  key         text primary key,
  enabled     boolean not null default false,
  expires_at  timestamptz,
  description text not null,
  updated_at  timestamptz not null default now(),
  updated_by  uuid references auth.users(id) on delete set null
);

alter table public.feature_flags enable row level security;
-- Pas de policies : RLS deny-all. Accès via is_feature_flag_active() (lecture ciblée,
-- large) et admin_list/set_feature_flag() (lecture/écriture complète, admin only).

insert into public.feature_flags (key, enabled, description) values
  ('llm_generation_enabled', true, 'Kill switch : coupe la génération IA (séances) si actif=false'),
  ('maintenance_mode', false, 'Bloque l''app pour tout le monde sauf les admins'),
  ('public_registration_enabled', false, 'Bypass temporaire de l''allowlist à l''inscription (expiration obligatoire)')
on conflict (key) do nothing;

create or replace function public.is_feature_flag_active(p_key text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select coalesce(
    (select enabled and (expires_at is null or expires_at > now())
     from public.feature_flags where key = p_key),
    false
  )
$$;

grant execute on function public.is_feature_flag_active(text) to authenticated;

create or replace function public.admin_list_feature_flags()
returns setof public.feature_flags
language plpgsql
security definer
set search_path = public
as $$
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;
  return query select * from public.feature_flags order by key;
end;
$$;

grant execute on function public.admin_list_feature_flags() to authenticated;

create or replace function public.admin_set_feature_flag(
  p_key text,
  p_enabled boolean,
  p_expires_at timestamptz
)
returns public.feature_flags
language plpgsql
security definer
set search_path = public
as $$
declare
  updated public.feature_flags;
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;
  if p_key = 'public_registration_enabled' and p_enabled and p_expires_at is null then
    raise exception 'public_registration_enabled requires an expiration when enabled';
  end if;

  update public.feature_flags
  set enabled = p_enabled,
      expires_at = p_expires_at,
      updated_at = now(),
      updated_by = auth.uid()
  where key = p_key
  returning * into updated;

  if updated.key is null then
    raise exception 'unknown feature flag: %', p_key;
  end if;
  return updated;
end;
$$;

grant execute on function public.admin_set_feature_flag(text, boolean, timestamptz) to authenticated;
```

- [ ] **Step 2: Apply + verify**

Apply via `mcp__supabase__apply_migration` (name `e18_feature_flags`). Verify seed:

```sql
select key, enabled, expires_at from public.feature_flags order by key;
```

Expected: 3 rows, `llm_generation_enabled` = `true`, the other two `false`,
`expires_at` null on all three.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260708050000_e18_feature_flags.sql
git commit -m "feat(db): E18 — table feature_flags + RPCs + 3 flags seedés"
```

### Task 11: Worker — kill switch (`llm_generation_enabled`)

**Files:**
- Create: `worker/src/garmin_sync/feature_flags.py`
- Modify: `worker/src/garmin_sync/coach/sessions.py` (`ensure_sessions`,
  `regenerate_session`)
- Test: `worker/tests/test_feature_flags.py`
- Test: `worker/tests/coach/test_sessions.py`

**Interfaces:**
- Produces: `is_flag_active(db: Any, key: str) -> bool` (`feature_flags.py`, plain
  service-role table read — worker doesn't need the RPC, it already bypasses RLS).
- Consumes: `get_admin_client()` return value passed in by the caller (matches existing
  `sessions.py` style, which always threads `db` through as a parameter rather than
  fetching it internally).

- [ ] **Step 1: Write the failing tests**

`worker/tests/test_feature_flags.py`:

```python
from unittest.mock import MagicMock

from garmin_sync.feature_flags import is_flag_active


def _db_with_flag(row):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = row
    return db


def test_is_flag_active_true_no_expiry():
    db = _db_with_flag({"enabled": True, "expires_at": None})
    assert is_flag_active(db, "llm_generation_enabled") is True


def test_is_flag_active_false_when_disabled():
    db = _db_with_flag({"enabled": False, "expires_at": None})
    assert is_flag_active(db, "llm_generation_enabled") is False


def test_is_flag_active_false_when_expired():
    db = _db_with_flag({"enabled": True, "expires_at": "2020-01-01T00:00:00+00:00"})
    assert is_flag_active(db, "public_registration_enabled") is False


def test_is_flag_active_true_when_expiry_in_future():
    db = _db_with_flag({"enabled": True, "expires_at": "2999-01-01T00:00:00+00:00"})
    assert is_flag_active(db, "public_registration_enabled") is True


def test_is_flag_active_false_when_row_missing():
    db = _db_with_flag(None)
    assert is_flag_active(db, "unknown_key") is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd worker && uv run pytest tests/test_feature_flags.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

`worker/src/garmin_sync/feature_flags.py`:

```python
"""Worker-side feature flag reads. Service-role bypasses RLS, so this reads the
table directly rather than going through the is_feature_flag_active() RPC."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def is_flag_active(db: Any, key: str) -> bool:
    resp = (
        db.table("feature_flags")
        .select("enabled, expires_at")
        .eq("key", key)
        .maybe_single()
        .execute()
    )
    row = resp.data
    if not row or not row.get("enabled"):
        return False
    expires_at = row.get("expires_at")
    if expires_at is None:
        return True
    return datetime.fromisoformat(expires_at) > datetime.now(UTC)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd worker && uv run pytest tests/test_feature_flags.py -v` → PASS.

- [ ] **Step 5: Write the failing tests — kill switch in `ensure_sessions` and `regenerate_session`**

Add to `worker/tests/coach/test_sessions.py`:

```python
@patch("garmin_sync.coach.sessions.is_flag_active", return_value=False)
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_skips_generation_when_kill_switch_off(mock_db, mock_gen, _mock_flag):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [
        {
            "id": "s1", "sport": "run", "session_type": "endurance",
            "target_duration_s": 3000, "target_tss": 50, "phase": "base",
            "date": "2026-05-21",
        },
    ]

    result = ensure_sessions(user_id="u1", days=7)

    mock_gen.assert_not_called()
    assert result["generated_count"] == 0
    assert result["skipped_count"] == 1
    assert result["llm_generation_disabled"] is True


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=False)
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_regenerate_session_returns_disabled_status_when_kill_switch_off(mock_db, mock_gen, _mock_flag):
    db = MagicMock()
    mock_db.return_value = db
    session_lookup = db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value  # noqa: E501
    session_lookup.data = {
        "id": "s1", "user_id": "u1", "sport": "run", "session_type": "intervals",
        "target_duration_s": 3600, "target_tss": 80, "phase": "peak", "date": "2026-05-25",
    }

    result = regenerate_session(user_id="u1", session_id="s1")

    assert result == {"status": "generation_disabled"}
    mock_gen.assert_not_called()
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd worker && uv run pytest tests/coach/test_sessions.py -k kill_switch -v`
Expected: FAIL — no such check exists yet (`is_flag_active` isn't imported/called by
`sessions.py`, so patching it has no effect and both generation paths still run).

- [ ] **Step 7: Implement — `ensure_sessions`**

In `sessions.py`, add the import:

```python
from garmin_sync.feature_flags import is_flag_active
```

At the top of `ensure_sessions`, right after computing `generatable` (before
`athlete, race, weeks = _load_profile_and_race(...)`):

```python
    if not is_flag_active(db, "llm_generation_enabled"):
        return {
            "generated_count": 0,
            "failed_count": 0,
            "skipped_count": len(pending),
            "llm_generation_disabled": True,
        }
```

- [ ] **Step 8: Implement — `regenerate_session`**

At the top of `regenerate_session`, right after the `_should_skip_workout_generation`
early return:

```python
    if not is_flag_active(db, "llm_generation_enabled"):
        return {"status": "generation_disabled"}
```

- [ ] **Step 9: Fix the other existing tests that now reach the kill-switch check**

`is_flag_active` is called unconditionally once `ensure_sessions` has at least one
generatable session, and once `regenerate_session` has a non-rest session — **before**
any of these five existing/Task-4-modified tests' own mocking takes over. Without
mocking it, `is_flag_active` runs for real against a bare `MagicMock` `db`, and
`datetime.fromisoformat(expires_at)` crashes on the `MagicMock` it gets back for
`expires_at` (a `MagicMock` is truthy and not `None`, so the function tries to parse it
as a date string). Add `@patch("garmin_sync.coach.sessions.is_flag_active",
return_value=True)` as a **new topmost decorator** (so its mock argument, conventionally
named `_mock_flag` since the tests below don't assert on it, becomes the new last
parameter) to exactly these five tests:

1. `test_ensure_sessions_generates_for_each_pending` →
   `def test_ensure_sessions_generates_for_each_pending(mock_db, mock_gen, mock_record, _mock_flag):`
2. `test_ensure_sessions_continues_on_error` →
   `def test_ensure_sessions_continues_on_error(mock_db, mock_gen, mock_record, _mock_flag):`
3. `test_ensure_sessions_reports_failure_to_sentry` (not touched by Task 4 — add the
   decorator on top of its existing four) →

```python
@patch("garmin_sync.coach.sessions.is_flag_active", return_value=True)
@patch("garmin_sync.coach.sessions.capture")
@patch("garmin_sync.coach.sessions._load_activity_review")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_reports_failure_to_sentry(mock_db, mock_gen, mock_review, mock_capture, _mock_flag):
```

4. `test_ensure_sessions_passes_activity_review_to_generation` →
   `def test_ensure_sessions_passes_activity_review_to_generation(mock_db, mock_gen, mock_review, mock_record, _mock_flag):`
5. `test_regenerate_session_updates_existing` →
   `def test_regenerate_session_updates_existing(mock_db, mock_gen, mock_record, _mock_flag):`

For each, only the decorator stack and the function signature's parameter list change —
the test bodies (already written in Task 4/earlier in this task) are untouched.

- [ ] **Step 10: Run full suite**

Run: `cd worker && uv run pytest tests/coach/test_sessions.py -v` → all PASS.

- [ ] **Step 11: Commit**

```bash
cd worker && git add src/garmin_sync/feature_flags.py src/garmin_sync/coach/sessions.py \
  tests/test_feature_flags.py tests/coach/test_sessions.py
git commit -m "feat(worker): llm_generation_enabled kill switch on session generation"
```

### Task 12: `is_email_allowed` bypass via `public_registration_enabled`

**Files:**
- Create: `supabase/migrations/20260708060000_e18_public_registration_flag.sql`

**Interfaces:**
- Modifies (same signature, `create or replace`): `is_email_allowed(p_email text)
  returns boolean`. No frontend change needed — `app/(auth)/_actions/auth.ts` already
  calls this RPC as-is; the bypass is entirely server-side.

- [ ] **Step 1: Write the migration**

```sql
-- 20260708060000_e18_public_registration_flag.sql
create or replace function public.is_email_allowed(p_email text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select
    exists (select 1 from public.allowed_emails where email = lower(p_email))
    or public.is_feature_flag_active('public_registration_enabled')
$$;
```

(Grants are untouched — `create or replace function` on the same signature keeps the
existing `grant execute ... to anon, authenticated` from the original migration.)

- [ ] **Step 2: Apply + verify**

Apply via `mcp__supabase__apply_migration` (name `e18_public_registration_flag`).
Verify the bypass, using an email that is NOT in `allowed_emails`:

```sql
select public.is_email_allowed('definitely-not-allowlisted@example.com'); -- expect false

update public.feature_flags
set enabled = true, expires_at = now() + interval '1 hour'
where key = 'public_registration_enabled';

select public.is_email_allowed('definitely-not-allowlisted@example.com'); -- expect true

update public.feature_flags set enabled = false, expires_at = null
where key = 'public_registration_enabled'; -- reset to V1 default
```

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260708060000_e18_public_registration_flag.sql
git commit -m "feat(db): is_email_allowed bypass via public_registration_enabled flag"
```

### Task 13: Frontend — `maintenance_mode` in the app layout

**Files:**
- Modify: `app/(app)/layout.tsx`
- Create: `app/(app)/_components/maintenance-page.tsx`
- Test: `tests/unit/app/layout.test.tsx` (mirror `tests/unit/onboarding/guard.test.ts`'s
  mocking style for `createClient`/`redirect` — here there's no redirect, just
  conditional rendering, so mock `.rpc` instead of `.from`)

**Interfaces:**
- Consumes: RPC `is_admin_caller` (Task 1) and `is_feature_flag_active` (Task 10) via
  `supabase.rpc(...)`.

- [ ] **Step 1: Write the failing test**

`tests/unit/app/layout.test.tsx`:

```tsx
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

const getUser = vi.fn()
const rpc = vi.fn()
vi.mock('@/lib/supabase/server', () => ({
  createClient: () => Promise.resolve({ auth: { getUser }, rpc }),
}))
vi.mock('next/navigation', () => ({ redirect: vi.fn() }))

import AppLayout from '@/app/(app)/layout'

beforeEach(() => {
  getUser.mockReset()
  rpc.mockReset()
})

describe('AppLayout maintenance mode', () => {
  it('shows the maintenance page to a non-admin when maintenance_mode is active', async () => {
    getUser.mockResolvedValue({ data: { user: { id: 'u1' } } })
    rpc.mockImplementation((fn: string) => {
      if (fn === 'is_admin_caller') return Promise.resolve({ data: false })
      if (fn === 'is_feature_flag_active') return Promise.resolve({ data: true })
      return Promise.resolve({ data: null })
    })
    const ui = await AppLayout({ children: <div>app content</div> })
    render(ui)
    expect(screen.getByText(/maintenance/i)).toBeInTheDocument()
    expect(screen.queryByText('app content')).not.toBeInTheDocument()
  })

  it('still shows normal content to an admin during maintenance', async () => {
    getUser.mockResolvedValue({ data: { user: { id: 'owner' } } })
    rpc.mockImplementation((fn: string) => {
      if (fn === 'is_admin_caller') return Promise.resolve({ data: true })
      if (fn === 'is_feature_flag_active') return Promise.resolve({ data: true })
      return Promise.resolve({ data: null })
    })
    const ui = await AppLayout({ children: <div>app content</div> })
    render(ui)
    expect(screen.getByText('app content')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm test tests/unit/app/layout.test.tsx`
Expected: FAIL (no maintenance check exists yet).

- [ ] **Step 3: Implement — maintenance page component**

`app/(app)/_components/maintenance-page.tsx`:

```tsx
export function MaintenancePage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-6 text-center">
      <div className="max-w-sm space-y-2">
        <h1 className="text-xl font-semibold">Maintenance en cours</h1>
        <p className="text-muted-foreground text-sm">
          L&rsquo;application est momentanément indisponible. Réessaie dans quelques minutes.
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Implement — layout guard**

Modify `app/(app)/layout.tsx`:

```tsx
import { redirect } from 'next/navigation'
import { BottomNav } from '@/components/nav/bottom-nav'
import { SideNav } from '@/components/nav/side-nav'
import { createClient } from '@/lib/supabase/server'
import { SyncNowButton } from '@/app/(app)/_components/sync-now-button'
import { MaintenancePage } from '@/app/(app)/_components/maintenance-page'

export default async function AppLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  const [{ data: isAdmin }, { data: maintenanceActive }] = await Promise.all([
    supabase.rpc('is_admin_caller'),
    supabase.rpc('is_feature_flag_active', { p_key: 'maintenance_mode' }),
  ])

  if (maintenanceActive && !isAdmin) {
    return <MaintenancePage />
  }

  return (
    <div className="flex min-h-screen">
      <SideNav />
      <main className="flex-1 pb-20 md:pb-0 md:pl-64">
        <div className="container mx-auto max-w-6xl px-4 py-6">
          <div className="mb-4 flex justify-end">
            <SyncNowButton />
          </div>
          {children}
        </div>
      </main>
      <BottomNav />
    </div>
  )
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `pnpm test tests/unit/app/layout.test.tsx` → PASS.

- [ ] **Step 6: Full frontend gates**

Run: `pnpm lint && pnpm typecheck && pnpm test`

- [ ] **Step 7: Commit**

```bash
git add app/"(app)"/layout.tsx app/"(app)"/_components/maintenance-page.tsx \
  tests/unit/app/layout.test.tsx
git commit -m "feat(app): show maintenance page to non-admins when maintenance_mode is on"
```

### Task 14: Frontend — `FeatureFlagsPanel` + Server Actions

**Files:**
- Create: `app/(app)/admin/actions.ts`
- Create: `app/(app)/admin/_components/feature-flags-panel.tsx`
- Create: `app/(app)/admin/_components/skeletons/feature-flags-panel-skeleton.tsx`
- Test: `tests/unit/admin/actions.test.ts`

**Interfaces:**
- Produces: `setFeatureFlag(input: { key: string; enabled: boolean; expiresAt: string |
  null }): Promise<ActionResult>` (Server Action, same `ActionResult` shape as
  `app/(auth)/_actions/auth.ts`); `<FeatureFlagsPanel />` async Server Component
  (includes the risk banner for `maintenance_mode`/`public_registration_enabled` inline
  — same Suspense boundary, same RPC call, no separate fetch).
- Consumes: RPCs `admin_list_feature_flags`, `admin_set_feature_flag` (Task 10).

- [ ] **Step 1: Write the failing test**

`tests/unit/admin/actions.test.ts` (mirrors `tests/unit/auth/register-action.test.ts`):

```ts
import { describe, expect, it, vi, beforeEach } from 'vitest'

const revalidatePath = vi.fn()
vi.mock('next/cache', () => ({
  revalidatePath: (path: string): void => {
    revalidatePath(path)
  },
}))

const mockSupabase = { rpc: vi.fn() }
vi.mock('@/lib/supabase/server', () => ({ createClient: async () => mockSupabase }))

import { setFeatureFlag } from '@/app/(app)/admin/actions'

beforeEach(() => {
  mockSupabase.rpc.mockReset()
  revalidatePath.mockReset()
})

describe('setFeatureFlag', () => {
  it('calls admin_set_feature_flag with the right args and revalidates /admin', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: { key: 'maintenance_mode' }, error: null })
    const result = await setFeatureFlag({ key: 'maintenance_mode', enabled: true, expiresAt: null })
    expect(mockSupabase.rpc).toHaveBeenCalledWith('admin_set_feature_flag', {
      p_key: 'maintenance_mode',
      p_enabled: true,
      p_expires_at: null,
    })
    expect(result).toEqual({ success: true })
    expect(revalidatePath).toHaveBeenCalledWith('/admin')
  })

  it('rejects enabling public_registration_enabled without an expiry (client-side guard)', async () => {
    const result = await setFeatureFlag({
      key: 'public_registration_enabled',
      enabled: true,
      expiresAt: null,
    })
    expect(result).toEqual({ success: false, error: 'expiry_required' })
    expect(mockSupabase.rpc).not.toHaveBeenCalled()
  })

  it('returns save_failed when the RPC errors, without revalidating', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: null, error: { message: 'not authorized' } })
    const result = await setFeatureFlag({ key: 'maintenance_mode', enabled: true, expiresAt: null })
    expect(result).toEqual({ success: false, error: 'save_failed' })
    expect(revalidatePath).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm test tests/unit/admin/actions.test.ts`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `actions.ts`**

`app/(app)/admin/actions.ts`:

Follow the codebase's existing mutation convention (see `app/actions/sessions.ts` and
`app/(app)/onboarding/actions.ts`, both of which call `revalidatePath(...)` at the end of
every mutating Server Action, rather than relying on the client to force a reload):

```ts
'use server'

import { revalidatePath } from 'next/cache'
import { createClient } from '@/lib/supabase/server'

export type AdminActionError = 'expiry_required' | 'save_failed'
export type ActionResult = { success: true } | { success: false; error: AdminActionError }

interface SetFeatureFlagInput {
  key: string
  enabled: boolean
  expiresAt: string | null
}

export async function setFeatureFlag(input: SetFeatureFlagInput): Promise<ActionResult> {
  if (input.key === 'public_registration_enabled' && input.enabled && !input.expiresAt) {
    return { success: false, error: 'expiry_required' }
  }
  const supabase = await createClient()
  const { error } = await supabase.rpc('admin_set_feature_flag', {
    p_key: input.key,
    p_enabled: input.enabled,
    p_expires_at: input.expiresAt,
  })
  if (error) return { success: false, error: 'save_failed' }
  revalidatePath('/admin')
  return { success: true }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `pnpm test tests/unit/admin/actions.test.ts` → PASS.

- [ ] **Step 5: Add the `feature_flags` type + skeleton**

Add to `lib/admin/types.ts`:

```typescript
export interface FeatureFlagRow {
  key: string
  enabled: boolean
  expires_at: string | null
  description: string
  updated_at: string
}
```

`app/(app)/admin/_components/skeletons/feature-flags-panel-skeleton.tsx`:

```tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '@/app/(app)/_components/skeletons/loading-region'

export function FeatureFlagsPanelSkeleton() {
  return (
    <LoadingRegion label="Chargement des feature flags">
      <div className="space-y-2">
        {['flag-1', 'flag-2', 'flag-3'].map((key) => (
          <Skeleton key={key} className="h-14 w-full rounded-md" />
        ))}
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 6: Panel component (client island for the toggles, server-fetched data)**

`app/(app)/admin/_components/feature-flags-panel.tsx` — a client component receiving
already-fetched rows (server fetch stays in a thin async wrapper so the Suspense
boundary in Task 18 wraps the fetch, not the interactivity):

Add an `isFlagActive` helper to `lib/admin/types.ts` (next to `FeatureFlagRow`) — the
raw `enabled` column does **not** account for expiry (the row stays `enabled = true`
after `expires_at` passes; only reads through `is_feature_flag_active()`/this helper
resolve the real state), so every place that displays "is this flag on" must go through
it rather than reading `flag.enabled` directly:

```typescript
export function isFlagActive(flag: FeatureFlagRow): boolean {
  if (!flag.enabled) return false
  if (!flag.expires_at) return true
  return new Date(flag.expires_at) > new Date()
}
```

```tsx
import { createClient } from '@/lib/supabase/server'
import { isFlagActive, type FeatureFlagRow } from '@/lib/admin/types'
import { FeatureFlagsList } from './feature-flags-list'

export async function FeatureFlagsPanel() {
  const supabase = await createClient()
  const { data, error } = await supabase.rpc('admin_list_feature_flags')
  if (error || !data) {
    return <p className="text-destructive text-sm">Impossible de charger les feature flags.</p>
  }
  const flags = data as FeatureFlagRow[]
  const risky = flags.filter(
    (f) => isFlagActive(f) && (f.key === 'maintenance_mode' || f.key === 'public_registration_enabled')
  )

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold">Feature flags</h2>
      {risky.length > 0 && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
          {risky.map((f) => (
            <p key={f.key}>
              ⚠ {f.description}
              {f.expires_at && ` — expire le ${new Date(f.expires_at).toLocaleString('fr-FR')}`}
            </p>
          ))}
        </div>
      )}
      <FeatureFlagsList flags={flags} />
    </section>
  )
}
```

Create the client sub-component `app/(app)/admin/_components/feature-flags-list.tsx`
(kept separate from the async server panel so only the interactive part is `'use
client'`):

Follow the same post-mutation pattern as `components/auth/sign-out-button.tsx` (call the
action, then `router.refresh()` — never `window.location.reload()`, which would throw
away client-side state and defeats Next.js's cache-aware re-render):

```tsx
'use client'
import { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { setFeatureFlag } from '../actions'
import { isFlagActive, type FeatureFlagRow } from '@/lib/admin/types'

const DURATIONS: { label: string; hours: number }[] = [
  { label: '1h', hours: 1 },
  { label: '24h', hours: 24 },
  { label: '7j', hours: 24 * 7 },
]

export function FeatureFlagsList({ flags }: { readonly flags: FeatureFlagRow[] }) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const [durationHours, setDurationHours] = useState<number>(24)

  function toggle(flag: FeatureFlagRow) {
    const requiresExpiry = flag.key === 'public_registration_enabled'
    const nextEnabled = !isFlagActive(flag)
    const expiresAt =
      requiresExpiry && nextEnabled
        ? new Date(Date.now() + durationHours * 3_600_000).toISOString()
        : null
    startTransition(async () => {
      await setFeatureFlag({ key: flag.key, enabled: nextEnabled, expiresAt })
      router.refresh()
    })
  }

  return (
    <ul className="divide-y rounded-md border">
      {flags.map((flag) => {
        const active = isFlagActive(flag)
        return (
          <li key={flag.key} className="flex items-center justify-between gap-4 p-4">
            <div>
              <p className="text-sm font-medium">{flag.key}</p>
              <p className="text-muted-foreground text-xs">{flag.description}</p>
            </div>
            <div className="flex items-center gap-2">
              {flag.key === 'public_registration_enabled' && !active && (
                <select
                  aria-label="Durée d'activation"
                  className="rounded border bg-background px-2 py-1 text-xs"
                  value={durationHours}
                  onChange={(e) => setDurationHours(Number(e.target.value))}
                >
                  {DURATIONS.map((d) => (
                    <option key={d.label} value={d.hours}>{d.label}</option>
                  ))}
                </select>
              )}
              <Button
                size="sm"
                variant={active ? 'destructive' : 'default'}
                disabled={pending}
                onClick={() => toggle(flag)}
              >
                {active ? 'Désactiver' : 'Activer'}
              </Button>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
```

- [ ] **Step 7: Gates**

Run: `pnpm lint && pnpm typecheck && pnpm test`

- [ ] **Step 8: Commit**

```bash
git add app/"(app)"/admin/actions.ts app/"(app)"/admin/_components/feature-flags-panel.tsx \
  app/"(app)"/admin/_components/feature-flags-list.tsx \
  app/"(app)"/admin/_components/skeletons/feature-flags-panel-skeleton.tsx \
  lib/admin/types.ts tests/unit/admin/actions.test.ts
git commit -m "feat(admin): FeatureFlagsPanel with duration picker for public_registration_enabled"
```

---

## Phase C — Allowlist UI

### Task 15: Allowlist admin RPCs

**Files:**
- Create: `supabase/migrations/20260708070000_e18_allowlist_admin_rpcs.sql`

**Interfaces:**
- Produces: `admin_list_allowed_emails()` (returns email/note/invited_by/created_at +
  computed `status` — `'pending'` or `'active'`), `admin_add_allowed_email(p_email
  text, p_note text)`, `admin_remove_allowed_email(p_email text)`. All admin-gated.

- [ ] **Step 1: Write the migration**

```sql
-- 20260708070000_e18_allowlist_admin_rpcs.sql
create or replace function public.admin_list_allowed_emails()
returns table (
  email text,
  note text,
  invited_by uuid,
  created_at timestamptz,
  status text,
  registered_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;
  return query
    select
      a.email,
      a.note,
      a.invited_by,
      a.created_at,
      case when p.password_set then 'active' else 'pending' end as status,
      case when p.password_set then p.updated_at else null end as registered_at
    from public.allowed_emails a
    left join auth.users u on lower(u.email) = a.email
    left join public.athlete_profiles p on p.user_id = u.id
    order by a.created_at desc;
end;
$$;

grant execute on function public.admin_list_allowed_emails() to authenticated;

create or replace function public.admin_add_allowed_email(p_email text, p_note text)
returns public.allowed_emails
language plpgsql
security definer
set search_path = public
as $$
declare
  inserted public.allowed_emails;
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;
  insert into public.allowed_emails (email, note, invited_by)
  values (lower(p_email), p_note, auth.uid())
  on conflict (email) do update set note = excluded.note
  returning * into inserted;
  return inserted;
end;
$$;

grant execute on function public.admin_add_allowed_email(text, text) to authenticated;

create or replace function public.admin_remove_allowed_email(p_email text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;
  delete from public.allowed_emails where email = lower(p_email);
end;
$$;

grant execute on function public.admin_remove_allowed_email(text) to authenticated;
```

- [ ] **Step 2: Apply + verify**

Apply via `mcp__supabase__apply_migration` (name `e18_allowlist_admin_rpcs`). Verify the
existing owner row shows up as `active` (it already has `password_set = true`):

```sql
-- as the owner, from the app (Task 17) or via a temporary RLS-bypassing check:
select * from public.allowed_emails; -- sanity: table untouched, still has the owner row
```

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260708070000_e18_allowlist_admin_rpcs.sql
git commit -m "feat(db): E18 — RPCs admin_list/add/remove_allowed_email"
```

### Task 16: Add missing shadcn components

**Files:**
- Create: `components/ui/table.tsx`, `components/ui/badge.tsx`,
  `components/ui/alert-dialog.tsx` (via CLI, not hand-written)

**Interfaces:**
- Produces: `Table`/`TableHeader`/`TableBody`/`TableRow`/`TableCell`, `Badge`,
  `AlertDialog` + subcomponents — standard shadcn exports, consumed by Task 17.

- [ ] **Step 1: Install**

Run: `npx shadcn@latest add table badge alert-dialog`
(non-interactive: pass `--yes` if prompted; `components.json` is already configured,
see `components.json` at repo root — `style: default`, alias `@/components/ui`)

- [ ] **Step 2: Verify**

Run: `ls components/ui/` → confirm `table.tsx`, `badge.tsx`, `alert-dialog.tsx` now
present alongside the existing 6 files.
Run: `pnpm typecheck && pnpm build` → clean (new components must compile and not break
the build).

- [ ] **Step 3: Commit**

```bash
git add components/ui/table.tsx components/ui/badge.tsx components/ui/alert-dialog.tsx
git commit -m "chore(ui): add shadcn table/badge/alert-dialog components"
```

### Task 17: Frontend — `AllowlistPanel` + Server Actions

**Files:**
- Modify: `app/(app)/admin/actions.ts` (add `addAllowedEmail`, `removeAllowedEmail`)
- Create: `app/(app)/admin/_components/allowlist-panel.tsx`
- Create: `app/(app)/admin/_components/allowlist-table.tsx`
- Create: `app/(app)/admin/_components/skeletons/allowlist-panel-skeleton.tsx`
- Test: `tests/unit/admin/actions.test.ts` (extend)

**Interfaces:**
- Consumes: `Table`/`Badge`/`AlertDialog` (Task 16); RPCs
  `admin_list/add/remove_allowed_email` (Task 15).
- Produces: `addAllowedEmail(input: { email: string; note: string | null }):
  Promise<ActionResult>`, `removeAllowedEmail(email: string): Promise<ActionResult>`;
  `<AllowlistPanel />` async Server Component.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/admin/actions.test.ts`:

```ts
import { addAllowedEmail, removeAllowedEmail } from '@/app/(app)/admin/actions'

describe('addAllowedEmail', () => {
  it('normalizes email to lowercase and calls the RPC', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: { email: 'ami@example.com' }, error: null })
    const result = await addAllowedEmail({ email: 'AMI@Example.com', note: 'copain de club' })
    expect(mockSupabase.rpc).toHaveBeenCalledWith('admin_add_allowed_email', {
      p_email: 'ami@example.com',
      p_note: 'copain de club',
    })
    expect(result).toEqual({ success: true })
  })

  it('rejects an invalid email before calling the RPC', async () => {
    const result = await addAllowedEmail({ email: 'not-an-email', note: null })
    expect(result).toEqual({ success: false, error: 'save_failed' })
    expect(mockSupabase.rpc).not.toHaveBeenCalled()
  })
})

describe('removeAllowedEmail', () => {
  it('calls admin_remove_allowed_email and revalidates /admin', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: null, error: null })
    const result = await removeAllowedEmail('ami@example.com')
    expect(mockSupabase.rpc).toHaveBeenCalledWith('admin_remove_allowed_email', {
      p_email: 'ami@example.com',
    })
    expect(result).toEqual({ success: true })
    expect(revalidatePath).toHaveBeenCalledWith('/admin')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm test tests/unit/admin/actions.test.ts` → FAIL (functions don't exist).

- [ ] **Step 3: Implement — extend `actions.ts`**

Add to `app/(app)/admin/actions.ts`:

```ts
import { z } from 'zod'

const addAllowedEmailSchema = z.object({
  email: z.email().transform((s) => s.toLowerCase().trim()),
  note: z.string().nullable(),
})

export async function addAllowedEmail(input: {
  email: string
  note: string | null
}): Promise<ActionResult> {
  const parsed = addAllowedEmailSchema.safeParse(input)
  if (!parsed.success) return { success: false, error: 'save_failed' }
  const supabase = await createClient()
  const { error } = await supabase.rpc('admin_add_allowed_email', {
    p_email: parsed.data.email,
    p_note: parsed.data.note,
  })
  if (error) return { success: false, error: 'save_failed' }
  revalidatePath('/admin')
  return { success: true }
}

export async function removeAllowedEmail(email: string): Promise<ActionResult> {
  const supabase = await createClient()
  const { error } = await supabase.rpc('admin_remove_allowed_email', { p_email: email })
  if (error) return { success: false, error: 'save_failed' }
  revalidatePath('/admin')
  return { success: true }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `pnpm test tests/unit/admin/actions.test.ts` → PASS.

- [ ] **Step 5: Type + skeleton**

Add to `lib/admin/types.ts`:

```typescript
export interface AllowedEmailRow {
  email: string
  note: string | null
  invited_by: string | null
  created_at: string
  status: 'pending' | 'active'
  registered_at: string | null
}
```

`app/(app)/admin/_components/skeletons/allowlist-panel-skeleton.tsx`:

```tsx
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '@/app/(app)/_components/skeletons/loading-region'

export function AllowlistPanelSkeleton() {
  return (
    <LoadingRegion label="Chargement de l'allowlist">
      <div className="space-y-2">
        <Skeleton className="h-9 w-full max-w-md rounded-md" />
        <Skeleton className="h-48 w-full rounded-md" />
      </div>
    </LoadingRegion>
  )
}
```

- [ ] **Step 6: Client table + form**

`app/(app)/admin/_components/allowlist-table.tsx`:

```tsx
'use client'
import { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { addAllowedEmail, removeAllowedEmail } from '../actions'
import type { AllowedEmailRow } from '@/lib/admin/types'

export function AllowlistTable({ rows }: { readonly rows: AllowedEmailRow[] }) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const [email, setEmail] = useState('')
  const [note, setNote] = useState('')

  function handleAdd() {
    startTransition(async () => {
      await addAllowedEmail({ email, note: note || null })
      router.refresh()
    })
  }

  function handleRemove(target: string) {
    startTransition(async () => {
      await removeAllowedEmail(target)
      router.refresh()
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="ami@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="max-w-xs"
        />
        <Input
          placeholder="Note (optionnel)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="max-w-xs"
        />
        <Button disabled={pending || !email} onClick={handleAdd}>Ajouter</Button>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Email</TableHead>
            <TableHead>Statut</TableHead>
            <TableHead>Note</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.email}>
              <TableCell>{row.email}</TableCell>
              <TableCell>
                <Badge variant={row.status === 'active' ? 'default' : 'secondary'}>
                  {row.status === 'active' ? 'Actif' : 'En attente'}
                </Badge>
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">{row.note ?? '—'}</TableCell>
              <TableCell>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button size="sm" variant="outline">Retirer</Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Retirer {row.email} ?</AlertDialogTitle>
                      <AlertDialogDescription>
                        Bloque toute future inscription avec cet email. Si {row.email} a déjà un
                        compte actif, son accès n&rsquo;est pas révoqué.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Annuler</AlertDialogCancel>
                      <AlertDialogAction onClick={() => handleRemove(row.email)}>
                        Retirer
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
```

`app/(app)/admin/_components/allowlist-panel.tsx`:

```tsx
import { createClient } from '@/lib/supabase/server'
import type { AllowedEmailRow } from '@/lib/admin/types'
import { AllowlistTable } from './allowlist-table'

export async function AllowlistPanel() {
  const supabase = await createClient()
  const { data, error } = await supabase.rpc('admin_list_allowed_emails')
  if (error || !data) {
    return <p className="text-destructive text-sm">Impossible de charger l&rsquo;allowlist.</p>
  }
  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold">Allowlist</h2>
      <AllowlistTable rows={data as AllowedEmailRow[]} />
    </section>
  )
}
```

- [ ] **Step 7: Gates**

Run: `pnpm lint && pnpm typecheck && pnpm test`

- [ ] **Step 8: Commit**

```bash
git add app/"(app)"/admin/actions.ts app/"(app)"/admin/_components/allowlist-panel.tsx \
  app/"(app)"/admin/_components/allowlist-table.tsx \
  app/"(app)"/admin/_components/skeletons/allowlist-panel-skeleton.tsx \
  lib/admin/types.ts tests/unit/admin/actions.test.ts
git commit -m "feat(admin): AllowlistPanel — add/list/remove with confirmation dialog"
```

---

## Phase D — Page assembly

### Task 18: `app/(app)/admin/page.tsx`

**Files:**
- Create: `lib/admin/guard.ts`
- Create: `app/(app)/admin/page.tsx`
- Test: `tests/unit/admin/guard.test.ts`

**Interfaces:**
- Produces: `requireAdmin(): Promise<string>` (mirrors `lib/onboarding/guard.ts`'s
  `requireOnboarded`, same redirect-via-throw testing pattern), page component
  assembling `FinopsPanel`, `FeatureFlagsPanel`, `AllowlistPanel` each in their own
  `<Suspense>`.

- [ ] **Step 1: Write the failing test — guard**

`tests/unit/admin/guard.test.ts` (copy the exact mocking scaffolding from
`tests/unit/onboarding/guard.test.ts`, swap `.from`/`onboarding_completed_at` for `.rpc`):

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getUser = vi.fn()
const rpc = vi.fn()

vi.mock('@/lib/supabase/server', () => ({
  createClient: () => Promise.resolve({ auth: { getUser }, rpc }),
}))

const redirect = vi.fn((path: string) => {
  throw new Error(`__REDIRECT__:${path}`)
})
vi.mock('next/navigation', () => ({ redirect: (path: string) => redirect(path) }))

beforeEach(() => {
  getUser.mockReset()
  rpc.mockReset()
  redirect.mockClear()
})

afterEach(() => {
  vi.resetModules()
})

describe('requireAdmin', () => {
  it('redirects to /login when no user', async () => {
    getUser.mockResolvedValueOnce({ data: { user: null } })
    const { requireAdmin } = await import('@/lib/admin/guard')
    await expect(requireAdmin()).rejects.toThrow(/__REDIRECT__:\/login/)
  })

  it('redirects to /today when the user is not an admin', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    rpc.mockResolvedValueOnce({ data: false })
    const { requireAdmin } = await import('@/lib/admin/guard')
    await expect(requireAdmin()).rejects.toThrow(/__REDIRECT__:\/today/)
  })

  it('returns the user id when the user is an admin', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'owner-id' } } })
    rpc.mockResolvedValueOnce({ data: true })
    const { requireAdmin } = await import('@/lib/admin/guard')
    await expect(requireAdmin()).resolves.toBe('owner-id')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm test tests/unit/admin/guard.test.ts` → FAIL (module doesn't exist).

- [ ] **Step 3: Implement the guard**

`lib/admin/guard.ts`:

```ts
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

/** Use at the top of app/(app)/admin/page.tsx. Redirects to /login (no session) or
 * /today (authenticated but not in the `admins` table). Returns the user id. */
export async function requireAdmin(): Promise<string> {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const { data: isAdmin } = await supabase.rpc('is_admin_caller')
  if (!isAdmin) redirect('/today')

  return user.id
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `pnpm test tests/unit/admin/guard.test.ts` → PASS.

- [ ] **Step 5: Implement the page**

`app/(app)/admin/page.tsx`:

```tsx
import { Suspense } from 'react'
import { requireAdmin } from '@/lib/admin/guard'
import { FinopsPanel } from './_components/finops-panel'
import { FeatureFlagsPanel } from './_components/feature-flags-panel'
import { AllowlistPanel } from './_components/allowlist-panel'
import { FinopsPanelSkeleton } from './_components/skeletons/finops-panel-skeleton'
import { FeatureFlagsPanelSkeleton } from './_components/skeletons/feature-flags-panel-skeleton'
import { AllowlistPanelSkeleton } from './_components/skeletons/allowlist-panel-skeleton'

export const revalidate = 0

export default async function AdminPage() {
  await requireAdmin()

  return (
    <div className="space-y-8">
      <header>
        <p className="text-muted-foreground text-sm">Réservé à l&rsquo;owner</p>
        <h1 className="text-2xl font-semibold">Console admin</h1>
      </header>

      <Suspense fallback={<FinopsPanelSkeleton />}>
        <FinopsPanel />
      </Suspense>

      <Suspense fallback={<FeatureFlagsPanelSkeleton />}>
        <FeatureFlagsPanel />
      </Suspense>

      <Suspense fallback={<AllowlistPanelSkeleton />}>
        <AllowlistPanel />
      </Suspense>
    </div>
  )
}
```

Each `<Suspense>` boundary is mounted at the same level and starts fetching the moment
the page renders — none blocks the others, matching `app/(app)/today/page.tsx`'s
`BriefingLoader` pattern (Global Constraints).

- [ ] **Step 6: Full frontend gates**

Run: `pnpm lint && pnpm typecheck && pnpm build && pnpm test`

- [ ] **Step 7: Commit**

```bash
git add lib/admin/guard.ts app/"(app)"/admin/page.tsx tests/unit/admin/guard.test.ts
git commit -m "feat(admin): assemble /admin page — 3 independently-loading panels"
```

### Task 19: Manual end-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Start both stacks**

Run: `pnpm dev` (frontend) and, in another shell, `cd worker && uv run uvicorn
garmin_sync.main:app --reload --port 8080` (only needed if exercising session
generation — not required to view `/admin`).

- [ ] **Step 2: Log in as the owner, visit `/admin`**

Confirm: page loads, three sections render, each panel appears independently (throttle
network in devtools to confirm panels don't wait on each other — the finops chart can
render before the allowlist table if its RPC resolves first).

- [ ] **Step 3: Log in as a non-admin test user, visit `/admin`**

Confirm: immediate redirect to `/today`.

- [ ] **Step 4: Toggle `maintenance_mode` on, reload as the non-admin user**

Confirm: maintenance page shown. Reload as the owner: normal app still accessible.
Toggle back off before continuing.

- [ ] **Step 5: Toggle `public_registration_enabled` on (1h) via the UI**

Confirm the banner appears on `/admin`. In an incognito window, try registering with an
email NOT in `allowed_emails` — confirm the OTP is sent (no `email_not_allowed`). Toggle
off (or let it expire) and confirm registration is blocked again for a fresh email.

- [ ] **Step 6: Add and remove an allowlist entry via the UI**

Confirm the row appears as `En attente`, and that removing it doesn't affect any
already-registered account.

- [ ] **Step 7: Toggle `llm_generation_enabled` off, trigger a session regeneration**

Call the worker's `/coach/regenerate-session/{id}` (or trigger via the app's existing
regenerate button, if wired to the frontend) and confirm the response is
`{"status": "generation_disabled"}` rather than a fresh OpenAI call. Toggle back on.

- [ ] **Step 8: Run `python -m garmin_sync.cron billing` once manually**

From inside the worker container/venv with `OPENAI_ADMIN_API_KEY` set, run:
`cd worker && uv run python -m garmin_sync.cron billing`
Confirm `openai_billing_snapshot` gets rows (via `mcp__supabase__execute_sql`:
`select * from openai_billing_snapshot order by billing_date desc;`) and that the
`/admin` Finops panel's "facturé" figure updates on next load.

---

## Phase E — Quality gate (owner requirement)

### Task 20: `/vqo` audit — iterate to ≥9.5 on every category

**Files:** whichever files the audit flags (fixed in place, on the same feature
branch/worktree — no separate branch).

- [ ] **Step 1: Run the audit**

Once Tasks 1-19 are merged into the feature branch and all quality gates
(`pnpm lint && pnpm typecheck && pnpm build && pnpm test`,
`cd worker && uv run ruff check . && uv run mypy src/ && uv run pytest -v`) are green,
invoke the `vqo` skill (`Skill({ skill: "vqo" })`) against the full diff introduced by
this plan (Phase 0 through D — table `admins`, `llm_usage`, `openai_billing_snapshot`,
`feature_flags`, allowlist RPCs, worker instrumentation, `/admin` page).

- [ ] **Step 2: Read the per-category scores**

`vqo` reports scores per category (security, correctness, test coverage, performance,
maintainability — exact category list comes from the skill's own report format). Note
every category below 9.5.

- [ ] **Step 3: Fix and re-run, iterating to convergence**

For each finding below 9.5: fix it in place (respecting this plan's existing patterns —
e.g. a security finding on a new RPC gets the same `is_admin_caller()` guard style
already used everywhere else in this plan, not a bespoke one-off check). Re-run `/vqo`
after each fix batch. Repeat until **every category reports ≥ 9.5**.

- [ ] **Step 4: Re-run full test suites after the last fix batch**

Run: `pnpm lint && pnpm typecheck && pnpm build && pnpm test` and
`cd worker && uv run ruff check . && uv run mypy src/ && uv run pytest -v` — both clean.

- [ ] **Step 5: Commit the fixes**

```bash
git add -A
git commit -m "fix: address /vqo findings — all categories >= 9.5"
```

(If `/vqo` finds nothing below 9.5 on the first run, skip straight to Step 4 — no empty
commit.)
