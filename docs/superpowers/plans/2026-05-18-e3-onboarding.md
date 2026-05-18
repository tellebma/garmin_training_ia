# E3 — Profile & Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Onboarding wizard hybride 4 étapes + page profile éditable inline + endpoint worker `/garmin/profile-sync` qui pré-remplit FTP/VMA/FCmax depuis Garmin.

**Architecture:** Frontend Next.js 15 App Router avec Server Components qui chargent l'état + Client Component stepper qui orchestre les 4 étapes, chaque étape étant un form Zod avec sa Server Action propre. Le worker FastAPI expose un nouvel endpoint qui appelle `python-garminconnect` (déjà installé) pour récupérer le profil et upsert dans `athlete_profiles`. Schemas Zod partagés entre wizard et page profile édit (DRY).

**Tech Stack:**
- Frontend : Next.js 15 (App Router), TypeScript strict, Tailwind 4, shadcn/ui, Zod, supabase-js, sonner (toasts)
- Worker : Python 3.12, FastAPI, python-garminconnect 0.3.x, supabase-py, cryptography (Fernet)
- DB : Supabase Postgres + RLS, migrations dans `supabase/migrations/`
- Tests : Vitest (frontend unit), Playwright (E2E), pytest (worker)

**Spec source :** [`docs/superpowers/specs/2026-05-18-e3-onboarding-design.md`](../specs/2026-05-18-e3-onboarding-design.md)

---

## Pré-requis avant de démarrer

- Branche dédiée : `git checkout main && git pull && git checkout -b feat/e3-onboarding`
- Worker tourne en local (pour tester /garmin/profile-sync) : `cd worker && uv run uvicorn garmin_sync.main:app --reload --port 8080`
- Frontend tourne en local : `pnpm dev` → http://localhost:3000
- Variables d'env locales : `.env.local` doit contenir `WORKER_URL=http://localhost:8080` + clés Supabase

---

## Task 1 — Migration DB : `race_goals` + alter `athlete_profiles`

**Files:**
- Create: `supabase/migrations/20260518000000_e3_onboarding.sql`

- [ ] **Step 1: Créer le fichier migration**

```sql
-- 20260518000000_e3_onboarding.sql
-- E3 — Profile & Onboarding : nouvelle table race_goals + 2 colonnes athlete_profiles

-- =========================================
-- Table: race_goals
-- 1→N : un user peut avoir plusieurs courses (1 active "is_primary", N archivées)
-- =========================================
create table if not exists public.race_goals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  race_date date not null,
  race_distance text not null
    check (race_distance in ('sprint','olympique','half_ironman','ironman','autre')),
  name text,
  location text,
  target_time_seconds integer
    check (target_time_seconds is null or target_time_seconds between 600 and 86400),
  is_primary boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists race_goals_user_primary_idx
  on public.race_goals (user_id, is_primary) where is_primary;
create unique index if not exists race_goals_one_primary_per_user
  on public.race_goals (user_id) where is_primary;

alter table public.race_goals enable row level security;

drop policy if exists "users read own race_goals"   on public.race_goals;
drop policy if exists "users insert own race_goals" on public.race_goals;
drop policy if exists "users update own race_goals" on public.race_goals;
drop policy if exists "users delete own race_goals" on public.race_goals;

create policy "users read own race_goals"   on public.race_goals for select
  using (auth.uid() = user_id);
create policy "users insert own race_goals" on public.race_goals for insert
  with check (auth.uid() = user_id);
create policy "users update own race_goals" on public.race_goals for update
  using (auth.uid() = user_id);
create policy "users delete own race_goals" on public.race_goals for delete
  using (auth.uid() = user_id);

drop trigger if exists touch_race_goals_updated_at on public.race_goals;
create trigger touch_race_goals_updated_at before update on public.race_goals
  for each row execute function public.touch_updated_at();

-- =========================================
-- Alter: athlete_profiles
-- Ajouts: hours_per_week + garmin_synced_at
-- =========================================
alter table public.athlete_profiles
  add column if not exists hours_per_week integer
    check (hours_per_week is null or hours_per_week between 1 and 30),
  add column if not exists garmin_synced_at timestamptz;

comment on column public.athlete_profiles.hours_per_week is
  'Heures d''entraînement disponibles par semaine (1-30).';
comment on column public.athlete_profiles.garmin_synced_at is
  'Last successful auto-fetch from Garmin user-settings (FTP/VO2max/FCmax).';
```

- [ ] **Step 2: Appliquer la migration via Supabase MCP**

Via `mcp__supabase__apply_migration` avec `project_id=peiyrqplymdlmlpsbqzu` et le contenu SQL ci-dessus en `query`. Name : `20260518000000_e3_onboarding`.

- [ ] **Step 3: Vérifier la création + RLS via SELECT**

Via `mcp__supabase__execute_sql` :

```sql
select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public' and table_name = 'race_goals'
order by ordinal_position;
```

Expected: 11 colonnes incluant `id`, `user_id`, `race_date`, `race_distance`, `is_primary`, etc.

```sql
select policyname, cmd from pg_policies where tablename = 'race_goals' order by policyname;
```

Expected: 4 rows (delete/insert/select/update), tous "users ... own race_goals".

```sql
select column_name from information_schema.columns
where table_schema = 'public' and table_name = 'athlete_profiles'
  and column_name in ('hours_per_week','garmin_synced_at');
```

Expected: 2 rows.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260518000000_e3_onboarding.sql
git commit -m "feat(db): add race_goals table + extend athlete_profiles for E3 onboarding"
```

---

## Task 2 — Worker : transformer `_transform_profile` (TDD)

**Files:**
- Create: `worker/src/garmin_sync/profile_sync.py`
- Create: `worker/tests/test_profile_sync.py`

- [ ] **Step 1: Write the failing test**

Contenu de `worker/tests/test_profile_sync.py` :

```python
"""Tests for profile_sync transformer + orchestrator."""

from __future__ import annotations

import pytest

from garmin_sync.profile_sync import _transform_profile, _vma_from_vo2max, _normalize_sex


def test_transform_profile_full_payload() -> None:
    user_profile = {
        "birthDate": "1990-04-12",
        "gender": "MALE",
        "functionalThresholdPower": 245,
        "userMaxHr": 188,
    }
    max_metrics = {"vo2MaxValueRunning": 57.75}

    row = _transform_profile(user_profile, max_metrics)

    assert row == {"ftp_watts": 245, "vma_kmh": 16.5, "fc_max_bpm": 188}
    assert "dob" not in row  # NEVER touch dob — saisi à l'étape Perso
    assert "sex" not in row  # idem


def test_transform_profile_excludes_none_keys() -> None:
    """If Garmin has no value for a field, we must NOT include the key — the
    UPDATE would otherwise overwrite a manually-entered value with null."""
    user_profile = {"functionalThresholdPower": None, "userMaxHr": 188}
    max_metrics = {"vo2MaxValueRunning": None}

    row = _transform_profile(user_profile, max_metrics)

    assert row == {"fc_max_bpm": 188}
    assert "ftp_watts" not in row
    assert "vma_kmh" not in row


def test_transform_profile_empty_payload_returns_empty() -> None:
    row = _transform_profile({}, {})
    assert row == {}


def test_vma_from_vo2max() -> None:
    assert _vma_from_vo2max(56.0) == 16.0
    assert _vma_from_vo2max(57.75) == 16.5
    assert _vma_from_vo2max(None) is None
    assert _vma_from_vo2max(0) is None  # falsy → None, garde contre divisions weird


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("MALE", "M"),
        ("FEMALE", "F"),
        ("male", "M"),  # case-insensitive
        ("OTHER", "X"),
        ("UNKNOWN", None),
        (None, None),
    ],
)
def test_normalize_sex(raw: str | None, expected: str | None) -> None:
    assert _normalize_sex(raw) == expected
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd worker && uv run pytest tests/test_profile_sync.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'garmin_sync.profile_sync'`

- [ ] **Step 3: Write the transformer implementation**

Contenu initial de `worker/src/garmin_sync/profile_sync.py` :

```python
"""Garmin profile auto-fetch — pulls FTP/VO2max/FCmax from Garmin Connect and
upserts into athlete_profiles. Called from the wizard step Perf and from the
'↻ Sync Garmin' button on /profile.

Design notes
------------
- We NEVER touch dob/sex (saisis manuellement à l'étape Perso, overwrite serait
  surprenant UX).
- We exclude keys whose Garmin value is None — the resulting UPDATE only writes
  fields where Garmin has a fresh value, preserving any manual entry the user
  made before.
- No cooldown : tokens already valid, the endpoint never triggers the login
  cascade that PR #6 protects against.
"""

from __future__ import annotations

from typing import Any


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _vma_from_vo2max(vo2: float | None) -> float | None:
    """VO2max (ml/kg/min) → VMA (km/h) via VMA = VO2max / 3.5 (formule classique)."""
    if not vo2:
        return None
    return round(vo2 / 3.5, 2)


def _normalize_sex(raw: str | None) -> str | None:
    if not raw:
        return None
    upper = raw.upper()
    if upper == "MALE":
        return "M"
    if upper == "FEMALE":
        return "F"
    if upper == "OTHER":
        return "X"
    return None


def _transform_profile(user_profile: dict[str, Any], max_metrics: dict[str, Any]) -> dict[str, Any]:
    """Return only non-null perf fields. Keys with None values are EXCLUDED."""
    row: dict[str, Any] = {}
    ftp = _safe_int(user_profile.get("functionalThresholdPower"))
    if ftp is not None:
        row["ftp_watts"] = ftp
    vma = _vma_from_vo2max(max_metrics.get("vo2MaxValueRunning"))
    if vma is not None:
        row["vma_kmh"] = vma
    fcmax = _safe_int(user_profile.get("userMaxHr"))
    if fcmax is not None:
        row["fc_max_bpm"] = fcmax
    return row
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd worker && uv run pytest tests/test_profile_sync.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Quality gates**

```bash
cd worker && uv run ruff check . && uv run mypy src/
```

Expected: All checks passed.

- [ ] **Step 6: Commit**

```bash
git add worker/src/garmin_sync/profile_sync.py worker/tests/test_profile_sync.py
git commit -m "feat(worker): add Garmin profile transformer for E3 onboarding"
```

---

## Task 3 — Worker : orchestrator `sync_garmin_profile` (TDD)

**Files:**
- Modify: `worker/src/garmin_sync/profile_sync.py`
- Modify: `worker/tests/test_profile_sync.py`

- [ ] **Step 1: Add the failing orchestrator tests**

Ajouter à la fin de `worker/tests/test_profile_sync.py` :

```python
from datetime import datetime
from unittest.mock import MagicMock, patch

from garmin_sync.garmin_client import GarminAuthError
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)


def _make_creds_row(token_plain: str = '{"oauth": "ok"}') -> dict[str, object]:
    from garmin_sync.crypto import TokenCipher

    cipher = TokenCipher()
    return {"oauth_tokens_encrypted": cipher.encrypt(token_plain).decode("ascii")}


def test_sync_garmin_profile_returns_no_credentials_when_missing() -> None:
    from garmin_sync.profile_sync import sync_garmin_profile

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = None  # noqa: E501

    with patch("garmin_sync.profile_sync.get_admin_client", return_value=fake_db):
        result = sync_garmin_profile("u1")

    assert result == {"status": "no_credentials"}


def test_sync_garmin_profile_returns_auth_failed_on_dead_token() -> None:
    from garmin_sync.profile_sync import sync_garmin_profile

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (  # noqa: E501
        _make_creds_row()
    )

    with (
        patch("garmin_sync.profile_sync.get_admin_client", return_value=fake_db),
        patch("garmin_sync.profile_sync.login_with_tokens") as login_mock,
    ):
        login_mock.side_effect = GarminAuthError("session expired")
        result = sync_garmin_profile("u1")

    assert result == {"status": "auth_failed"}


def test_sync_garmin_profile_returns_rate_limited_on_429() -> None:
    from garmin_sync.profile_sync import sync_garmin_profile

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (  # noqa: E501
        _make_creds_row()
    )
    fake_client = MagicMock()
    fake_client.get_user_profile.side_effect = GarminConnectTooManyRequestsError("429")

    with (
        patch("garmin_sync.profile_sync.get_admin_client", return_value=fake_db),
        patch("garmin_sync.profile_sync.login_with_tokens", return_value=fake_client),
    ):
        result = sync_garmin_profile("u1")

    assert result == {"status": "rate_limited"}


def test_sync_garmin_profile_happy_path_upserts_only_present_fields() -> None:
    from garmin_sync.profile_sync import sync_garmin_profile

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (  # noqa: E501
        _make_creds_row()
    )
    fake_client = MagicMock()
    fake_client.get_user_profile.return_value = {
        "functionalThresholdPower": 245,
        "userMaxHr": 188,
    }
    fake_client.get_max_metrics.return_value = {"vo2MaxValueRunning": 57.75}

    with (
        patch("garmin_sync.profile_sync.get_admin_client", return_value=fake_db),
        patch("garmin_sync.profile_sync.login_with_tokens", return_value=fake_client),
    ):
        result = sync_garmin_profile("u1")

    assert result["status"] == "ok"
    assert result["fetched"] == {"ftp_watts": 245, "vma_kmh": 16.5, "fc_max_bpm": 188}
    # Verify the UPDATE call sent garmin_synced_at + the 3 perf fields
    update_call = fake_db.table.return_value.update.call_args
    payload = update_call.args[0]
    assert payload["ftp_watts"] == 245
    assert payload["vma_kmh"] == 16.5
    assert payload["fc_max_bpm"] == 188
    assert "garmin_synced_at" in payload
    assert "dob" not in payload
    assert "sex" not in payload


def test_sync_garmin_profile_happy_path_only_garmin_synced_at_when_empty() -> None:
    """If Garmin returned nothing useful, the UPDATE still bumps garmin_synced_at
    so the UI knows we tried (and the wizard step Perf doesn't re-trigger)."""
    from garmin_sync.profile_sync import sync_garmin_profile

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (  # noqa: E501
        _make_creds_row()
    )
    fake_client = MagicMock()
    fake_client.get_user_profile.return_value = {}
    fake_client.get_max_metrics.return_value = {}

    with (
        patch("garmin_sync.profile_sync.get_admin_client", return_value=fake_db),
        patch("garmin_sync.profile_sync.login_with_tokens", return_value=fake_client),
    ):
        result = sync_garmin_profile("u1")

    assert result["status"] == "ok"
    assert result["fetched"] == {}
    payload = fake_db.table.return_value.update.call_args.args[0]
    assert list(payload.keys()) == ["garmin_synced_at"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd worker && uv run pytest tests/test_profile_sync.py -v
```

Expected: 5 new tests FAIL (`sync_garmin_profile not defined`), 5 previous PASS.

- [ ] **Step 3: Implement the orchestrator**

Ajouter en haut de `worker/src/garmin_sync/profile_sync.py` (imports) :

```python
import logging
from datetime import UTC, date, datetime
from typing import cast

from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from garmin_sync.crypto import TokenCipher
from garmin_sync.garmin_client import GarminAuthError, login_with_tokens
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)
```

Ajouter en bas de `worker/src/garmin_sync/profile_sync.py` :

```python
def sync_garmin_profile(user_id: str) -> dict[str, Any]:
    """Auto-fetch FTP/VMA/FCmax from Garmin Connect, upsert into athlete_profiles.

    Returns one of:
        {"status": "ok", "fetched": {...}}
        {"status": "no_credentials"}
        {"status": "auth_failed"}        — tokens dead, user must reconnect Garmin
        {"status": "rate_limited"}       — Garmin 429
        {"status": "garmin_error", "type": "..."}
    """
    db = get_admin_client()
    creds_resp = (
        db.table("garmin_credentials")
        .select("oauth_tokens_encrypted")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    creds = cast("dict[str, Any] | None", creds_resp.data)
    if not creds or not creds.get("oauth_tokens_encrypted"):
        return {"status": "no_credentials"}

    cipher = TokenCipher()
    serialized = cipher.decrypt(creds["oauth_tokens_encrypted"].encode("ascii"))
    try:
        client = login_with_tokens(serialized)
    except (GarminAuthError, GarminConnectAuthenticationError):
        return {"status": "auth_failed"}

    try:
        user_profile = client.get_user_profile()
        max_metrics = client.get_max_metrics(date.today().isoformat())
    except GarminConnectTooManyRequestsError:
        log.warning("Garmin rate-limited /profile-sync for user=%s", user_id)
        return {"status": "rate_limited"}
    except Exception as e:
        log.exception("Garmin error during /profile-sync for user=%s", user_id)
        return {"status": "garmin_error", "type": type(e).__name__}

    row = _transform_profile(user_profile or {}, max_metrics or {})
    db.table("athlete_profiles").update(
        {**row, "garmin_synced_at": datetime.now(UTC).isoformat()}
    ).eq("user_id", user_id).execute()
    return {"status": "ok", "fetched": row}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd worker && uv run pytest tests/test_profile_sync.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 5: Quality gates**

```bash
cd worker && uv run ruff check . && uv run mypy src/
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add worker/src/garmin_sync/profile_sync.py worker/tests/test_profile_sync.py
git commit -m "feat(worker): implement sync_garmin_profile orchestrator with status enum"
```

---

## Task 4 — Worker : FastAPI endpoint `POST /garmin/profile-sync`

**Files:**
- Modify: `worker/src/garmin_sync/main.py`
- Modify: `worker/tests/test_main.py`

- [ ] **Step 1: Write the failing endpoint test**

Ajouter à `worker/tests/test_main.py` (en réutilisant les patterns existants de la fixture client) :

```python
def test_garmin_profile_sync_requires_jwt(client) -> None:
    """No Authorization header → 401."""
    r = client.post("/garmin/profile-sync")
    assert r.status_code == 401


def test_garmin_profile_sync_returns_status_dict(client, monkeypatch) -> None:
    """Happy path : endpoint returns the status dict from sync_garmin_profile."""
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")

    def fake_sync(user_id: str) -> dict:
        assert user_id == "u1"
        return {"status": "ok", "fetched": {"ftp_watts": 245}}

    monkeypatch.setattr("garmin_sync.profile_sync.sync_garmin_profile", fake_sync)

    r = client.post("/garmin/profile-sync", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "fetched": {"ftp_watts": 245}}


def test_garmin_profile_sync_catches_unexpected(client, monkeypatch) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")
    monkeypatch.setattr(
        "garmin_sync.profile_sync.sync_garmin_profile",
        lambda _u: (_ for _ in ()).throw(RuntimeError("kaboom")),
    )

    r = client.post("/garmin/profile-sync", headers={"Authorization": "Bearer x"})
    body = r.json()
    assert body["status"] == "unexpected_error"
    assert body["type"] == "RuntimeError"
    assert "error_id" in body
    assert "detail" not in body
    assert "traceback" not in body
```

NOTE: si `client` fixture n'existe pas dans test_main.py, regarder comment les autres tests `/garmin/connect` sont structurés et copier le pattern (typiquement TestClient(app) injecté).

- [ ] **Step 2: Run the test, observe failure**

```bash
cd worker && uv run pytest tests/test_main.py -v -k profile_sync
```

Expected: 3 tests FAIL — `404 not found`.

- [ ] **Step 3: Add the endpoint**

Modifier `worker/src/garmin_sync/main.py`, ajouter après `garmin_mfa` endpoint :

```python
@app.post("/garmin/profile-sync")
def garmin_profile_sync(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Pull FTP/VMA/FCmax from Garmin and upsert into athlete_profiles.

    Called by the wizard step Perf (first arrival only) and by the manual
    'Sync Garmin' button on /profile. Idempotent — safe to call repeatedly.
    """
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.profile_sync import sync_garmin_profile

        return sync_garmin_profile(user_id)
    except Exception as e:
        error_id = _new_error_id()
        log.exception("[%s] garmin_profile_sync endpoint crashed for user=%s", error_id, user_id)
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd worker && uv run pytest tests/test_main.py -v -k profile_sync
```

Expected: 3 PASS.

- [ ] **Step 5: Run full worker test suite + quality gates**

```bash
cd worker && uv run pytest -q && uv run ruff check . && uv run mypy src/
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add worker/src/garmin_sync/main.py worker/tests/test_main.py
git commit -m "feat(worker): expose POST /garmin/profile-sync endpoint"
```

---

## Task 5 — Frontend : schemas Zod partagés + tests Vitest

**Files:**
- Create: `lib/onboarding/schemas.ts`
- Create: `lib/onboarding/steps.ts`
- Create: `lib/onboarding/schemas.test.ts`

- [ ] **Step 1: Create steps.ts (types helpers)**

```typescript
// lib/onboarding/steps.ts
export const STEPS = ['perso', 'race', 'perf', 'dispo'] as const
export type Step = (typeof STEPS)[number]

export const STEP_LABELS: Record<Step, string> = {
  perso: 'Informations personnelles',
  race: 'Course cible',
  perf: 'Performance',
  dispo: 'Disponibilité',
}

export function nextStep(current: Step): Step | null {
  const i = STEPS.indexOf(current)
  return i >= 0 && i < STEPS.length - 1 ? STEPS[i + 1] : null
}
```

- [ ] **Step 2: Write the failing schema tests**

```typescript
// lib/onboarding/schemas.test.ts
import { describe, expect, it } from 'vitest'
import { personSchema, raceSchema, perfSchema, dispoSchema, DISPO_DEFAULTS } from './schemas'

describe('personSchema', () => {
  const valid = {
    first_name: 'Maxime',
    dob: '1990-04-12',
    sex: 'M' as const,
    consent_data_processing: true,
  }

  it('accepts a valid minimal payload', () => {
    expect(personSchema.safeParse(valid).success).toBe(true)
  })

  it('rejects empty first_name', () => {
    expect(personSchema.safeParse({ ...valid, first_name: '' }).success).toBe(false)
  })

  it('rejects future dob', () => {
    expect(personSchema.safeParse({ ...valid, dob: '2999-01-01' }).success).toBe(false)
  })

  it('requires consent=true', () => {
    expect(
      personSchema.safeParse({ ...valid, consent_data_processing: false }).success
    ).toBe(false)
  })

  it('rejects invalid sex value', () => {
    expect(personSchema.safeParse({ ...valid, sex: 'Z' }).success).toBe(false)
  })
})

describe('raceSchema', () => {
  const future = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
  const valid = { race_date: future, race_distance: 'olympique' as const }

  it('accepts a valid minimal payload', () => {
    expect(raceSchema.safeParse(valid).success).toBe(true)
  })

  it('rejects past race_date', () => {
    expect(raceSchema.safeParse({ ...valid, race_date: '2000-01-01' }).success).toBe(false)
  })

  it('rejects unknown distance', () => {
    expect(raceSchema.safeParse({ ...valid, race_distance: 'mega' }).success).toBe(false)
  })

  it('rejects target_time below 600s', () => {
    expect(
      raceSchema.safeParse({ ...valid, target_time_seconds: 599 }).success
    ).toBe(false)
  })

  it('rejects target_time above 86400s', () => {
    expect(
      raceSchema.safeParse({ ...valid, target_time_seconds: 90000 }).success
    ).toBe(false)
  })
})

describe('perfSchema', () => {
  it('accepts an empty payload (tous optional)', () => {
    expect(perfSchema.safeParse({}).success).toBe(true)
  })

  it('rejects FTP=49', () => {
    expect(perfSchema.safeParse({ ftp_watts: 49 }).success).toBe(false)
  })

  it('rejects FTP=601', () => {
    expect(perfSchema.safeParse({ ftp_watts: 601 }).success).toBe(false)
  })

  it('rejects vma below 5', () => {
    expect(perfSchema.safeParse({ vma_kmh: 4.99 }).success).toBe(false)
  })

  it('rejects vma above 30', () => {
    expect(perfSchema.safeParse({ vma_kmh: 30.01 }).success).toBe(false)
  })

  it('rejects fc_max_bpm out of [100,230]', () => {
    expect(perfSchema.safeParse({ fc_max_bpm: 99 }).success).toBe(false)
    expect(perfSchema.safeParse({ fc_max_bpm: 231 }).success).toBe(false)
  })
})

describe('dispoSchema', () => {
  it('accepts an empty payload (tous optional → defaults appliqués ailleurs)', () => {
    expect(dispoSchema.safeParse({}).success).toBe(true)
  })

  it('rejects sports_strengths score out of [1,5]', () => {
    expect(
      dispoSchema.safeParse({
        sports_strengths: { swim: 0, bike: 3, run: 3 },
      }).success
    ).toBe(false)
  })

  it('rejects hours_per_week=0', () => {
    expect(dispoSchema.safeParse({ hours_per_week: 0 }).success).toBe(false)
  })

  it('rejects available_days containing unknown day', () => {
    expect(
      dispoSchema.safeParse({ available_days: ['mon', 'funday'] }).success
    ).toBe(false)
  })
})

describe('DISPO_DEFAULTS', () => {
  it('validates against the schema', () => {
    expect(dispoSchema.safeParse(DISPO_DEFAULTS).success).toBe(true)
  })
})
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pnpm test --run lib/onboarding
```

Expected: failure — `schemas.ts` not found.

- [ ] **Step 4: Implement the schemas**

```typescript
// lib/onboarding/schemas.ts
import { z } from 'zod'

const dateIsoString = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Format attendu YYYY-MM-DD')

export const personSchema = z.object({
  first_name: z.string().trim().min(1, 'Requis').max(80),
  dob: dateIsoString.refine(
    (d) => new Date(d) < new Date(),
    'La date de naissance doit être passée'
  ),
  sex: z.enum(['M', 'F', 'X']),
  city: z.string().trim().max(120).optional(),
  country: z.string().trim().max(80).optional(),
  consent_data_processing: z.literal(true, {
    errorMap: () => ({ message: 'Tu dois accepter le traitement des données' }),
  }),
})

export const RACE_DISTANCES = ['sprint', 'olympique', 'half_ironman', 'ironman', 'autre'] as const

export const raceSchema = z.object({
  race_date: dateIsoString.refine(
    (d) => new Date(d) > new Date(),
    'La date de course doit être future'
  ),
  race_distance: z.enum(RACE_DISTANCES),
  name: z.string().trim().max(160).optional(),
  location: z.string().trim().max(160).optional(),
  target_time_seconds: z.number().int().min(600).max(86400).optional(),
})

export const perfSchema = z.object({
  ftp_watts: z.number().int().min(50).max(600).optional(),
  vma_kmh: z.number().min(5).max(30).optional(),
  fc_max_bpm: z.number().int().min(100).max(230).optional(),
})

export const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

export const dispoSchema = z.object({
  available_days: z.array(z.enum(DAYS)).optional(),
  hours_per_week: z.number().int().min(1).max(30).optional(),
  sports_strengths: z
    .object({
      swim: z.number().int().min(1).max(5),
      bike: z.number().int().min(1).max(5),
      run: z.number().int().min(1).max(5),
    })
    .optional(),
})

export const DISPO_DEFAULTS = {
  available_days: ['mon', 'tue', 'wed', 'thu', 'sat'] as const,
  hours_per_week: 6,
  sports_strengths: { swim: 3, bike: 3, run: 3 },
} satisfies z.infer<typeof dispoSchema>

export type PersonInput = z.infer<typeof personSchema>
export type RaceInput = z.infer<typeof raceSchema>
export type PerfInput = z.infer<typeof perfSchema>
export type DispoInput = z.infer<typeof dispoSchema>
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pnpm test --run lib/onboarding
```

Expected: all PASS.

- [ ] **Step 6: Quality gates**

```bash
pnpm lint && pnpm typecheck
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add lib/onboarding/
git commit -m "feat(onboarding): add shared Zod schemas + steps helpers"
```

---

## Task 6 — Frontend : Server Actions (wizard + sync) — skeleton + saveStepPerso

**Files:**
- Create: `app/(app)/onboarding/actions.ts`

- [ ] **Step 1: Create actions.ts with saveStepPerso**

```typescript
// app/(app)/onboarding/actions.ts
'use server'

import { revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import {
  personSchema,
  raceSchema,
  perfSchema,
  dispoSchema,
  DISPO_DEFAULTS,
  type PersonInput,
  type RaceInput,
  type PerfInput,
  type DispoInput,
} from '@/lib/onboarding/schemas'
import { nextStep, type Step } from '@/lib/onboarding/steps'

export type StepResult =
  | { success: true; nextStep: Step | null }
  | { success: false; errors: Record<string, string[]> }
  | { success: false; error: 'save_failed' | 'unauthenticated' }

async function requireUserId(): Promise<string | { success: false; error: 'unauthenticated' }> {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) return { success: false, error: 'unauthenticated' }
  return user.id
}

export async function saveStepPerso(input: PersonInput): Promise<StepResult> {
  const parsed = personSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: parsed.error.flatten().fieldErrors }
  }
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') return userIdOrErr

  const supabase = await createClient()
  const { error } = await supabase.from('athlete_profiles').upsert(
    {
      user_id: userIdOrErr,
      first_name: parsed.data.first_name,
      dob: parsed.data.dob,
      sex: parsed.data.sex,
      city: parsed.data.city ?? null,
      country: parsed.data.country ?? null,
      consent_data_processing: parsed.data.consent_data_processing,
      consent_signed_at: new Date().toISOString(),
    },
    { onConflict: 'user_id' }
  )
  if (error) return { success: false, error: 'save_failed' }

  revalidatePath('/onboarding')
  return { success: true, nextStep: nextStep('perso') }
}
```

- [ ] **Step 2: Verify typecheck**

```bash
pnpm typecheck
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add app/'(app)'/onboarding/actions.ts
git commit -m "feat(onboarding): add saveStepPerso server action"
```

---

## Task 7 — Frontend : Server Actions `saveStepRace` (crée race_goals si primary absent, sinon update)

**Files:**
- Modify: `app/(app)/onboarding/actions.ts`

- [ ] **Step 1: Add saveStepRace**

Ajouter à `actions.ts` :

```typescript
export async function saveStepRace(input: RaceInput): Promise<StepResult> {
  const parsed = raceSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: parsed.error.flatten().fieldErrors }
  }
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') return userIdOrErr

  const supabase = await createClient()
  // Upsert : si un race_goal is_primary existe déjà → update, sinon insert
  const { data: existing } = await supabase
    .from('race_goals')
    .select('id')
    .eq('user_id', userIdOrErr)
    .eq('is_primary', true)
    .maybeSingle()

  const payload = {
    user_id: userIdOrErr,
    race_date: parsed.data.race_date,
    race_distance: parsed.data.race_distance,
    name: parsed.data.name ?? null,
    location: parsed.data.location ?? null,
    target_time_seconds: parsed.data.target_time_seconds ?? null,
    is_primary: true,
  }

  const { error } = existing
    ? await supabase.from('race_goals').update(payload).eq('id', existing.id)
    : await supabase.from('race_goals').insert(payload)

  if (error) return { success: false, error: 'save_failed' }

  revalidatePath('/onboarding')
  return { success: true, nextStep: nextStep('race') }
}
```

- [ ] **Step 2: Typecheck + commit**

```bash
pnpm typecheck
git add app/'(app)'/onboarding/actions.ts
git commit -m "feat(onboarding): add saveStepRace (upsert primary race_goal)"
```

---

## Task 8 — Frontend : Server Actions `saveStepPerf` + `syncGarminProfile`

**Files:**
- Modify: `app/(app)/onboarding/actions.ts`
- Modify: `lib/worker.ts` (extend type for profile-sync result)

- [ ] **Step 1: Extend ProfileSyncResult type in `lib/worker.ts`**

Ajouter à `lib/worker.ts` :

```typescript
export type ProfileSyncResult =
  | { status: 'ok'; fetched: { ftp_watts?: number; vma_kmh?: number; fc_max_bpm?: number } }
  | { status: 'no_credentials' }
  | { status: 'auth_failed' }
  | { status: 'rate_limited' }
  | { status: 'garmin_error'; type: string }
  | { status: 'unexpected_error'; error_id: string; type: string }
```

- [ ] **Step 2: Add saveStepPerf + syncGarminProfile to actions.ts**

```typescript
export async function saveStepPerf(input: PerfInput): Promise<StepResult> {
  const parsed = perfSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: parsed.error.flatten().fieldErrors }
  }
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') return userIdOrErr

  const supabase = await createClient()
  // Build patch excluding undefined values
  const patch: Record<string, number | null> = {}
  if (parsed.data.ftp_watts !== undefined) patch.ftp_watts = parsed.data.ftp_watts
  if (parsed.data.vma_kmh !== undefined) patch.vma_kmh = parsed.data.vma_kmh
  if (parsed.data.fc_max_bpm !== undefined) patch.fc_max_bpm = parsed.data.fc_max_bpm

  if (Object.keys(patch).length > 0) {
    const { error } = await supabase
      .from('athlete_profiles')
      .update(patch)
      .eq('user_id', userIdOrErr)
    if (error) return { success: false, error: 'save_failed' }
  }

  revalidatePath('/onboarding')
  return { success: true, nextStep: nextStep('perf') }
}

export async function syncGarminProfile(): Promise<import('@/lib/worker').ProfileSyncResult> {
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') {
    return { status: 'unexpected_error', error_id: '0', type: 'unauthenticated' }
  }
  const supabase = await createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (!session) {
    return { status: 'unexpected_error', error_id: '0', type: 'no_session' }
  }
  const { workerPost } = await import('@/lib/worker')
  const result = await workerPost<import('@/lib/worker').ProfileSyncResult>(
    '/garmin/profile-sync',
    {},
    session.access_token
  )
  // Cache invalidate so /profile + /onboarding pick up the new garmin_synced_at
  revalidatePath('/onboarding')
  revalidatePath('/profile')
  return result
}
```

- [ ] **Step 3: Typecheck + commit**

```bash
pnpm typecheck
git add app/'(app)'/onboarding/actions.ts lib/worker.ts
git commit -m "feat(onboarding): add saveStepPerf + syncGarminProfile server actions"
```

---

## Task 9 — Frontend : Server Actions `saveStepDispo` + `finalizeOnboarding`

**Files:**
- Modify: `app/(app)/onboarding/actions.ts`

- [ ] **Step 1: Add the two actions**

```typescript
export async function saveStepDispo(input: DispoInput): Promise<StepResult> {
  const parsed = dispoSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: parsed.error.flatten().fieldErrors }
  }
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') return userIdOrErr

  const supabase = await createClient()
  // Apply DISPO_DEFAULTS for any field left undefined.
  const patch = {
    available_days: parsed.data.available_days ?? DISPO_DEFAULTS.available_days,
    hours_per_week: parsed.data.hours_per_week ?? DISPO_DEFAULTS.hours_per_week,
    sports_strengths: parsed.data.sports_strengths ?? DISPO_DEFAULTS.sports_strengths,
  }

  const { error } = await supabase
    .from('athlete_profiles')
    .update(patch)
    .eq('user_id', userIdOrErr)
  if (error) return { success: false, error: 'save_failed' }

  revalidatePath('/onboarding')
  return { success: true, nextStep: nextStep('dispo') }  // returns null (dispo is last)
}

export async function finalizeOnboarding(): Promise<void> {
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') redirect('/login')

  const supabase = await createClient()
  await supabase
    .from('athlete_profiles')
    .update({ onboarding_completed_at: new Date().toISOString() })
    .eq('user_id', userIdOrErr as string)

  revalidatePath('/profile')
  redirect('/profile?onboarded=1')
}
```

- [ ] **Step 2: Typecheck + commit**

```bash
pnpm typecheck
git add app/'(app)'/onboarding/actions.ts
git commit -m "feat(onboarding): add saveStepDispo + finalizeOnboarding actions"
```

---

## Task 10 — Frontend : `/onboarding/page.tsx` Server Component + wizard skeleton

**Files:**
- Create: `app/(app)/onboarding/page.tsx`
- Create: `app/(app)/onboarding/_components/onboarding-wizard.tsx`

- [ ] **Step 1: Server Component qui calcule initialStep**

```typescript
// app/(app)/onboarding/page.tsx
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { OnboardingWizard, type WizardInitial } from './_components/onboarding-wizard'
import type { Step } from '@/lib/onboarding/steps'

interface ProfileRow {
  first_name: string | null
  dob: string | null
  sex: 'M' | 'F' | 'X' | null
  city: string | null
  country: string | null
  ftp_watts: number | null
  vma_kmh: number | null
  fc_max_bpm: number | null
  hours_per_week: number | null
  available_days: string[] | null
  sports_strengths: { swim?: number; bike?: number; run?: number } | null
  garmin_synced_at: string | null
  onboarding_completed_at: string | null
  consent_data_processing: boolean
}

interface RaceRow {
  race_date: string
  race_distance: 'sprint' | 'olympique' | 'half_ironman' | 'ironman' | 'autre'
  name: string | null
  location: string | null
  target_time_seconds: number | null
}

function computeInitialStep(profile: ProfileRow | null, race: RaceRow | null): Step {
  if (!profile?.first_name || !profile.dob || !profile.sex) return 'perso'
  if (!race) return 'race'
  // Perf : on saute si garmin_synced_at est set OU si au moins un champ a une valeur
  const hasPerf =
    profile.ftp_watts !== null || profile.vma_kmh !== null || profile.fc_max_bpm !== null
  if (!hasPerf && !profile.garmin_synced_at) return 'perf'
  if (!profile.hours_per_week) return 'dispo'
  return 'dispo'
}

export default async function OnboardingPage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const [{ data: profile }, { data: race }] = await Promise.all([
    supabase.from('athlete_profiles').select('*').eq('user_id', user.id).single<ProfileRow>(),
    supabase
      .from('race_goals')
      .select('race_date, race_distance, name, location, target_time_seconds')
      .eq('user_id', user.id)
      .eq('is_primary', true)
      .maybeSingle<RaceRow>(),
  ])

  // Déjà onboardé → /profile direct
  if (profile?.onboarding_completed_at) redirect('/profile')

  const initialStep = computeInitialStep(profile, race)

  const initial: WizardInitial = {
    perso: profile
      ? {
          first_name: profile.first_name ?? '',
          dob: profile.dob ?? '',
          sex: profile.sex ?? 'M',
          city: profile.city ?? '',
          country: profile.country ?? '',
          consent_data_processing: profile.consent_data_processing,
        }
      : null,
    race: race
      ? {
          race_date: race.race_date,
          race_distance: race.race_distance,
          name: race.name ?? '',
          location: race.location ?? '',
          target_time_seconds: race.target_time_seconds ?? undefined,
        }
      : null,
    perf: {
      ftp_watts: profile?.ftp_watts ?? undefined,
      vma_kmh: profile?.vma_kmh ?? undefined,
      fc_max_bpm: profile?.fc_max_bpm ?? undefined,
      garmin_synced_at: profile?.garmin_synced_at ?? null,
    },
    dispo: {
      available_days: profile?.available_days ?? [],
      hours_per_week: profile?.hours_per_week ?? undefined,
      sports_strengths: profile?.sports_strengths ?? { swim: 3, bike: 3, run: 3 },
    },
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Bienvenue {profile?.first_name ?? ''} 👋</h1>
        <p className="text-muted-foreground text-sm">
          Quelques infos pour générer ton plan d'entraînement. ~5 minutes.
        </p>
      </header>
      <OnboardingWizard initial={initial} initialStep={initialStep} />
    </div>
  )
}
```

- [ ] **Step 2: Client wizard skeleton (tabs + step rendering, forms à venir Task 11-13)**

```typescript
// app/(app)/onboarding/_components/onboarding-wizard.tsx
'use client'

import { useState } from 'react'
import { STEPS, STEP_LABELS, type Step } from '@/lib/onboarding/steps'
import { StepPersoForm } from './step-perso-form'
import { StepRaceForm } from './step-race-form'
import { StepPerfForm } from './step-perf-form'
import { StepDispoForm } from './step-dispo-form'
import type { PersonInput, RaceInput, PerfInput, DispoInput } from '@/lib/onboarding/schemas'
import { cn } from '@/lib/utils'

export interface WizardInitial {
  perso: PersonInput | null
  race: RaceInput | null
  perf: PerfInput & { garmin_synced_at: string | null }
  dispo: DispoInput
}

interface Props {
  initial: WizardInitial
  initialStep: Step
}

export function OnboardingWizard({ initial, initialStep }: Readonly<Props>) {
  const [step, setStep] = useState<Step>(initialStep)
  const [completed, setCompleted] = useState<Set<Step>>(() => {
    const s = new Set<Step>()
    if (initial.perso) s.add('perso')
    if (initial.race) s.add('race')
    if (initial.perf.ftp_watts || initial.perf.vma_kmh || initial.perf.fc_max_bpm) s.add('perf')
    if (initial.dispo.hours_per_week) s.add('dispo')
    return s
  })

  function markDoneAndAdvance(done: Step, nextStep: Step | null) {
    setCompleted((prev) => new Set(prev).add(done))
    if (nextStep) setStep(nextStep)
  }

  return (
    <section className="space-y-6">
      <nav aria-label="Étapes" className="flex flex-wrap gap-2 text-sm">
        {STEPS.map((s, i) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setStep(s)
            }}
            className={cn(
              'rounded-full border px-3 py-1 transition',
              step === s && 'bg-primary text-primary-foreground',
              completed.has(s) && step !== s && 'bg-emerald-500/10 text-emerald-600',
              !completed.has(s) && step !== s && 'text-muted-foreground'
            )}
          >
            {completed.has(s) && step !== s ? '✓ ' : `${String(i + 1)}. `}
            {STEP_LABELS[s]}
          </button>
        ))}
      </nav>

      <div className="rounded-lg border p-6">
        {step === 'perso' && (
          <StepPersoForm
            defaultValues={initial.perso}
            onDone={(nextStep) => {
              markDoneAndAdvance('perso', nextStep)
            }}
          />
        )}
        {step === 'race' && (
          <StepRaceForm
            defaultValues={initial.race}
            onDone={(nextStep) => {
              markDoneAndAdvance('race', nextStep)
            }}
          />
        )}
        {step === 'perf' && (
          <StepPerfForm
            defaultValues={initial.perf}
            onDone={(nextStep) => {
              markDoneAndAdvance('perf', nextStep)
            }}
          />
        )}
        {step === 'dispo' && (
          <StepDispoForm
            defaultValues={initial.dispo}
            onDone={(nextStep) => {
              markDoneAndAdvance('dispo', nextStep)
            }}
          />
        )}
      </div>
    </section>
  )
}
```

- [ ] **Step 3: Verify typecheck (forms missing → TS errors expected)**

```bash
pnpm typecheck
```

Expected: errors for missing `step-*-form` imports. C'est OK, on les ajoute Task 11-13.

- [ ] **Step 4: Commit (intermediate, TS still broken)**

```bash
git add app/'(app)'/onboarding/page.tsx app/'(app)'/onboarding/_components/onboarding-wizard.tsx
git commit -m "feat(onboarding): add page.tsx + wizard skeleton (forms in next commits)"
```

---

## Task 11 — Frontend : `step-perso-form.tsx` + `step-race-form.tsx`

**Files:**
- Create: `app/(app)/onboarding/_components/step-perso-form.tsx`
- Create: `app/(app)/onboarding/_components/step-race-form.tsx`

- [ ] **Step 1: step-perso-form.tsx**

```typescript
// app/(app)/onboarding/_components/step-perso-form.tsx
'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepPerso } from '../actions'
import type { PersonInput } from '@/lib/onboarding/schemas'
import type { Step } from '@/lib/onboarding/steps'

interface Props {
  defaultValues: PersonInput | null
  onDone: (nextStep: Step | null) => void
}

export function StepPersoForm({ defaultValues, onDone }: Readonly<Props>) {
  const [first_name, setFirstName] = useState(defaultValues?.first_name ?? '')
  const [dob, setDob] = useState(defaultValues?.dob ?? '')
  const [sex, setSex] = useState<'M' | 'F' | 'X'>(defaultValues?.sex ?? 'M')
  const [city, setCity] = useState(defaultValues?.city ?? '')
  const [country, setCountry] = useState(defaultValues?.country ?? '')
  const [consent, setConsent] = useState<boolean>(defaultValues?.consent_data_processing ?? false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    const result = await saveStepPerso({
      first_name,
      dob,
      sex,
      city: city || undefined,
      country: country || undefined,
      consent_data_processing: consent as true,
    })
    setLoading(false)
    if (!result.success) {
      if ('errors' in result) setErrors(result.errors)
      else toast.error('Erreur de sauvegarde, réessaye')
      return
    }
    onDone(result.nextStep)
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="first_name">Prénom</Label>
        <Input
          id="first_name"
          value={first_name}
          onChange={(e) => {
            setFirstName(e.target.value)
          }}
          required
        />
        {errors.first_name?.[0] && (
          <p className="text-destructive text-xs">{errors.first_name[0]}</p>
        )}
      </div>
      <div className="space-y-2">
        <Label htmlFor="dob">Date de naissance</Label>
        <Input
          id="dob"
          type="date"
          value={dob}
          onChange={(e) => {
            setDob(e.target.value)
          }}
          required
        />
        {errors.dob?.[0] && <p className="text-destructive text-xs">{errors.dob[0]}</p>}
      </div>
      <div className="space-y-2">
        <Label htmlFor="sex">Sexe</Label>
        <select
          id="sex"
          value={sex}
          onChange={(e) => {
            setSex(e.target.value as 'M' | 'F' | 'X')
          }}
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
        >
          <option value="M">M</option>
          <option value="F">F</option>
          <option value="X">X / Autre</option>
        </select>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="city">Ville</Label>
          <Input
            id="city"
            value={city}
            onChange={(e) => {
              setCity(e.target.value)
            }}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="country">Pays</Label>
          <Input
            id="country"
            value={country}
            onChange={(e) => {
              setCountry(e.target.value)
            }}
          />
        </div>
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => {
            setConsent(e.target.checked)
          }}
          className="mt-0.5"
          required
        />
        <span>
          J'accepte le traitement de mes données fitness pour générer un plan personnalisé. (RGPD)
        </span>
      </label>
      {errors.consent_data_processing?.[0] && (
        <p className="text-destructive text-xs">{errors.consent_data_processing[0]}</p>
      )}
      <Button type="submit" disabled={loading} className="w-full">
        {loading ? 'Sauvegarde...' : 'Suivant'}
      </Button>
    </form>
  )
}
```

- [ ] **Step 2: step-race-form.tsx**

```typescript
// app/(app)/onboarding/_components/step-race-form.tsx
'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepRace } from '../actions'
import { RACE_DISTANCES, type RaceInput } from '@/lib/onboarding/schemas'
import type { Step } from '@/lib/onboarding/steps'

interface Props {
  defaultValues: RaceInput | null
  onDone: (nextStep: Step | null) => void
}

const DISTANCE_LABELS: Record<(typeof RACE_DISTANCES)[number], string> = {
  sprint: 'Sprint (~750/20/5)',
  olympique: 'Olympique (1500/40/10)',
  half_ironman: 'Half Ironman 70.3',
  ironman: 'Ironman 140.6',
  autre: 'Autre',
}

export function StepRaceForm({ defaultValues, onDone }: Readonly<Props>) {
  const [race_date, setRaceDate] = useState(defaultValues?.race_date ?? '')
  const [race_distance, setDistance] = useState<(typeof RACE_DISTANCES)[number]>(
    defaultValues?.race_distance ?? 'olympique'
  )
  const [name, setName] = useState(defaultValues?.name ?? '')
  const [location, setLocation] = useState(defaultValues?.location ?? '')
  const [target_hms, setTargetHms] = useState(
    defaultValues?.target_time_seconds ? secondsToHms(defaultValues.target_time_seconds) : ''
  )
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    const target_time_seconds = target_hms ? hmsToSeconds(target_hms) : undefined
    const result = await saveStepRace({
      race_date,
      race_distance,
      name: name || undefined,
      location: location || undefined,
      target_time_seconds,
    })
    setLoading(false)
    if (!result.success) {
      if ('errors' in result) setErrors(result.errors)
      else toast.error('Erreur de sauvegarde, réessaye')
      return
    }
    onDone(result.nextStep)
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="race_date">Date de la course</Label>
        <Input
          id="race_date"
          type="date"
          value={race_date}
          onChange={(e) => {
            setRaceDate(e.target.value)
          }}
          required
        />
        {errors.race_date?.[0] && (
          <p className="text-destructive text-xs">{errors.race_date[0]}</p>
        )}
      </div>
      <div className="space-y-2">
        <Label htmlFor="race_distance">Distance</Label>
        <select
          id="race_distance"
          value={race_distance}
          onChange={(e) => {
            setDistance(e.target.value as (typeof RACE_DISTANCES)[number])
          }}
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
        >
          {RACE_DISTANCES.map((d) => (
            <option key={d} value={d}>
              {DISTANCE_LABELS[d]}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="name">Nom de la course (optionnel)</Label>
        <Input
          id="name"
          value={name}
          onChange={(e) => {
            setName(e.target.value)
          }}
          placeholder="ex: Ironman 70.3 Nice"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="location">Lieu (optionnel)</Label>
        <Input
          id="location"
          value={location}
          onChange={(e) => {
            setLocation(e.target.value)
          }}
          placeholder="ex: Nice, France"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="target_hms">Temps cible (optionnel, format hh:mm:ss)</Label>
        <Input
          id="target_hms"
          value={target_hms}
          onChange={(e) => {
            setTargetHms(e.target.value)
          }}
          placeholder="05:30:00"
          pattern="^\d{1,2}:\d{2}:\d{2}$"
        />
      </div>
      <Button type="submit" disabled={loading} className="w-full">
        {loading ? 'Sauvegarde...' : 'Suivant'}
      </Button>
    </form>
  )
}

function hmsToSeconds(hms: string): number {
  const [h, m, s] = hms.split(':').map((n) => Number.parseInt(n, 10))
  return h * 3600 + m * 60 + s
}

function secondsToHms(total: number): string {
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
```

- [ ] **Step 3: Typecheck**

```bash
pnpm typecheck
```

Expected: still missing 2 forms (perf, dispo).

- [ ] **Step 4: Commit**

```bash
git add app/'(app)'/onboarding/_components/step-perso-form.tsx app/'(app)'/onboarding/_components/step-race-form.tsx
git commit -m "feat(onboarding): add Perso + Race step forms"
```

---

## Task 12 — Frontend : `step-perf-form.tsx` avec auto-fetch Garmin

**Files:**
- Create: `app/(app)/onboarding/_components/step-perf-form.tsx`

- [ ] **Step 1: Create the form**

```typescript
// app/(app)/onboarding/_components/step-perf-form.tsx
'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepPerf, syncGarminProfile } from '../actions'
import type { PerfInput } from '@/lib/onboarding/schemas'
import type { Step } from '@/lib/onboarding/steps'

interface Props {
  defaultValues: PerfInput & { garmin_synced_at: string | null }
  onDone: (nextStep: Step | null) => void
}

export function StepPerfForm({ defaultValues, onDone }: Readonly<Props>) {
  const [ftp, setFtp] = useState<string>(defaultValues.ftp_watts?.toString() ?? '')
  const [vma, setVma] = useState<string>(defaultValues.vma_kmh?.toString() ?? '')
  const [fcmax, setFcmax] = useState<string>(defaultValues.fc_max_bpm?.toString() ?? '')
  const [syncedAt, setSyncedAt] = useState<string | null>(defaultValues.garmin_synced_at)
  const [syncing, setSyncing] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  // Auto-fetch UNIQUEMENT à la première arrivée (garmin_synced_at IS NULL)
  useEffect(() => {
    if (syncedAt !== null) return
    let cancelled = false
    void (async () => {
      setSyncing(true)
      const r = await syncGarminProfile()
      if (cancelled) return
      setSyncing(false)
      if (r.status === 'ok') {
        if (r.fetched.ftp_watts) setFtp(r.fetched.ftp_watts.toString())
        if (r.fetched.vma_kmh) setVma(r.fetched.vma_kmh.toString())
        if (r.fetched.fc_max_bpm) setFcmax(r.fetched.fc_max_bpm.toString())
        setSyncedAt(new Date().toISOString())
      } else if (r.status === 'rate_limited') {
        toast.warning('Garmin a temporisé — remplis manuellement ou retente plus tard.')
        setSyncedAt(new Date().toISOString())  // marquer pour ne pas re-tenter en boucle
      } else if (r.status === 'auth_failed') {
        toast.error('Connexion Garmin expirée — reconnecte depuis /profile.')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [syncedAt])

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    const result = await saveStepPerf({
      ftp_watts: ftp ? Number.parseInt(ftp, 10) : undefined,
      vma_kmh: vma ? Number.parseFloat(vma) : undefined,
      fc_max_bpm: fcmax ? Number.parseInt(fcmax, 10) : undefined,
    })
    setLoading(false)
    if (!result.success) {
      if ('errors' in result) setErrors(result.errors)
      else toast.error('Erreur de sauvegarde, réessaye')
      return
    }
    onDone(result.nextStep)
  }

  const fmtSynced = syncedAt
    ? new Date(syncedAt).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
    : null

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
    >
      {syncing && (
        <p className="text-muted-foreground text-sm">↻ Récupération depuis Garmin...</p>
      )}
      {fmtSynced && !syncing && (
        <p className="text-xs text-emerald-600 dark:text-emerald-400">
          ↻ Synchronisé de Garmin le {fmtSynced}
        </p>
      )}
      <p className="text-muted-foreground text-xs">
        Tous facultatifs. Si tu ne sais pas, laisse vide — ta montre Garmin te donne ces valeurs
        dans Performance &gt; Statistiques.
      </p>

      <div className="space-y-2">
        <Label htmlFor="ftp">FTP (watts)</Label>
        <Input
          id="ftp"
          type="number"
          min={50}
          max={600}
          value={ftp}
          onChange={(e) => {
            setFtp(e.target.value)
          }}
          placeholder="ex: 245"
        />
        {errors.ftp_watts?.[0] && (
          <p className="text-destructive text-xs">{errors.ftp_watts[0]}</p>
        )}
      </div>
      <div className="space-y-2">
        <Label htmlFor="vma">VMA (km/h)</Label>
        <Input
          id="vma"
          type="number"
          step="0.1"
          min={5}
          max={30}
          value={vma}
          onChange={(e) => {
            setVma(e.target.value)
          }}
          placeholder="ex: 16.5"
        />
        {errors.vma_kmh?.[0] && <p className="text-destructive text-xs">{errors.vma_kmh[0]}</p>}
      </div>
      <div className="space-y-2">
        <Label htmlFor="fcmax">FC max (bpm)</Label>
        <Input
          id="fcmax"
          type="number"
          min={100}
          max={230}
          value={fcmax}
          onChange={(e) => {
            setFcmax(e.target.value)
          }}
          placeholder="ex: 188"
        />
        {errors.fc_max_bpm?.[0] && (
          <p className="text-destructive text-xs">{errors.fc_max_bpm[0]}</p>
        )}
      </div>

      <Button type="submit" disabled={loading || syncing} className="w-full">
        {loading ? 'Sauvegarde...' : 'Suivant'}
      </Button>
    </form>
  )
}
```

- [ ] **Step 2: Typecheck (perso/race/perf imported, only dispo missing)**

```bash
pnpm typecheck
```

- [ ] **Step 3: Commit**

```bash
git add app/'(app)'/onboarding/_components/step-perf-form.tsx
git commit -m "feat(onboarding): add Perf step form with first-visit Garmin auto-fetch"
```

---

## Task 13 — Frontend : `step-dispo-form.tsx` + finalize on submit

**Files:**
- Create: `app/(app)/onboarding/_components/step-dispo-form.tsx`

- [ ] **Step 1: Create the form**

```typescript
// app/(app)/onboarding/_components/step-dispo-form.tsx
'use client'

import { useState, useTransition } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { finalizeOnboarding, saveStepDispo } from '../actions'
import { DAYS, type DispoInput } from '@/lib/onboarding/schemas'
import type { Step } from '@/lib/onboarding/steps'

interface Props {
  defaultValues: DispoInput
  onDone: (nextStep: Step | null) => void
}

const DAY_LABEL: Record<(typeof DAYS)[number], string> = {
  mon: 'Lun',
  tue: 'Mar',
  wed: 'Mer',
  thu: 'Jeu',
  fri: 'Ven',
  sat: 'Sam',
  sun: 'Dim',
}

export function StepDispoForm({ defaultValues, onDone }: Readonly<Props>) {
  const [days, setDays] = useState<(typeof DAYS)[number][]>(
    (defaultValues.available_days ?? []) as (typeof DAYS)[number][]
  )
  const [hours, setHours] = useState<string>(defaultValues.hours_per_week?.toString() ?? '')
  const [swim, setSwim] = useState<number>(defaultValues.sports_strengths?.swim ?? 3)
  const [bike, setBike] = useState<number>(defaultValues.sports_strengths?.bike ?? 3)
  const [run, setRun] = useState<number>(defaultValues.sports_strengths?.run ?? 3)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})
  const [, startTransition] = useTransition()

  function toggleDay(d: (typeof DAYS)[number]) {
    setDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]))
  }

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    const result = await saveStepDispo({
      available_days: days.length > 0 ? days : undefined,
      hours_per_week: hours ? Number.parseInt(hours, 10) : undefined,
      sports_strengths: { swim, bike, run },
    })
    if (!result.success) {
      setLoading(false)
      if ('errors' in result) setErrors(result.errors)
      else toast.error('Erreur de sauvegarde, réessaye')
      return
    }
    // Last step → finalize
    onDone(result.nextStep)
    startTransition(() => {
      void finalizeOnboarding()
    })
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label>Jours dispo (clique pour sélectionner)</Label>
        <div className="flex flex-wrap gap-2">
          {DAYS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => {
                toggleDay(d)
              }}
              className={
                days.includes(d)
                  ? 'bg-primary text-primary-foreground rounded-md border px-3 py-1 text-sm'
                  : 'text-muted-foreground rounded-md border px-3 py-1 text-sm'
              }
            >
              {DAY_LABEL[d]}
            </button>
          ))}
        </div>
        <p className="text-muted-foreground text-xs">
          Vide → defaults : Lun-Mar-Mer-Jeu-Sam.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="hours">Heures par semaine</Label>
        <Input
          id="hours"
          type="number"
          min={1}
          max={30}
          value={hours}
          onChange={(e) => {
            setHours(e.target.value)
          }}
          placeholder="ex: 6"
        />
        {errors.hours_per_week?.[0] && (
          <p className="text-destructive text-xs">{errors.hours_per_week[0]}</p>
        )}
      </div>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Niveau par sport (1=faible, 5=fort)</legend>
        {(['swim', 'bike', 'run'] as const).map((sport) => (
          <div key={sport} className="flex items-center gap-3 text-sm">
            <span className="w-12 capitalize">{sport}</span>
            <input
              type="range"
              min={1}
              max={5}
              value={sport === 'swim' ? swim : sport === 'bike' ? bike : run}
              onChange={(e) => {
                const v = Number.parseInt(e.target.value, 10)
                if (sport === 'swim') setSwim(v)
                else if (sport === 'bike') setBike(v)
                else setRun(v)
              }}
              className="flex-1"
            />
            <span className="w-6 text-right">
              {sport === 'swim' ? swim : sport === 'bike' ? bike : run}
            </span>
          </div>
        ))}
      </fieldset>

      <Button type="submit" disabled={loading} className="w-full">
        {loading ? 'Finalisation...' : 'Terminer l\'onboarding'}
      </Button>
    </form>
  )
}
```

- [ ] **Step 2: Full typecheck + lint + build**

```bash
pnpm typecheck && pnpm lint && pnpm build
```

Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add app/'(app)'/onboarding/_components/step-dispo-form.tsx
git commit -m "feat(onboarding): add Dispo step + trigger finalize on submit"
```

---

## Task 14 — Frontend : layout redirect non-onboardé

**Files:**
- Modify: `app/(app)/layout.tsx`

- [ ] **Step 1: Read current layout**

```bash
cat app/'(app)'/layout.tsx
```

(Note pour exécuteur : tu verras un layout qui fait déjà le check auth + redirect /login. On ajoute un 2ème redirect vers /onboarding.)

- [ ] **Step 2: Apply the patch**

Ajouter avant le `return (...)`, après la vérification user :

```typescript
// Vérifier si l'onboarding est complété — sinon redirect vers le wizard.
// Exception : on est déjà sur /onboarding, ne pas faire de boucle.
import { headers } from 'next/headers'
const pathname = (await headers()).get('x-pathname') ?? ''
const { data: profile } = await supabase
  .from('athlete_profiles')
  .select('onboarding_completed_at')
  .eq('user_id', user.id)
  .single()

if (!profile?.onboarding_completed_at && !pathname.startsWith('/onboarding')) {
  redirect('/onboarding')
}
```

NOTE : Next.js App Router ne fournit pas `pathname` nativement dans les Server Components / layouts. Solution la plus simple : ne PAS redirect depuis le layout, mais directement depuis chaque page protégée non-onboarding. Préférer cette approche :

```typescript
// lib/onboarding/guard.ts (nouveau)
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

export async function requireOnboarded(): Promise<void> {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')
  const { data } = await supabase
    .from('athlete_profiles')
    .select('onboarding_completed_at')
    .eq('user_id', user.id)
    .single()
  if (!data?.onboarding_completed_at) redirect('/onboarding')
}
```

Puis appeler `await requireOnboarded()` au début de chaque page protégée non-onboarding (`/today/page.tsx`, `/profile/page.tsx`).

- [ ] **Step 3: Create the guard helper**

Créer `lib/onboarding/guard.ts` avec le contenu ci-dessus.

- [ ] **Step 4: Add the guard call in /today and /profile pages**

Dans `app/(app)/today/page.tsx`, ajouter en haut de la fonction :

```typescript
import { requireOnboarded } from '@/lib/onboarding/guard'
// ...
export default async function TodayPage() {
  await requireOnboarded()
  // ... reste inchangé
}
```

Idem pour `app/(app)/profile/page.tsx` — ajouter `await requireOnboarded()` au début (mais APRÈS le check auth user, puisque `requireOnboarded` fait déjà ce check, on peut SIMPLIFIER en remplaçant le check auth manuel par juste `await requireOnboarded()`).

- [ ] **Step 5: Test manuellement le redirect**

```bash
pnpm dev
```

Manuel :
1. Login avec un user dont `onboarding_completed_at IS NULL`
2. Tenter d'accéder à `/today` → doit redirect `/onboarding`
3. Compléter le wizard → revenir sur `/today` doit marcher

- [ ] **Step 6: Commit**

```bash
git add lib/onboarding/guard.ts app/'(app)'/today/page.tsx app/'(app)'/profile/page.tsx
git commit -m "feat(onboarding): redirect non-onboarded users to /onboarding wizard"
```

---

## Task 15 — Frontend : `/profile` éditable inline (sections Perso/Race/Perf/Dispo)

**Files:**
- Modify: `app/(app)/profile/page.tsx`
- Create: `app/(app)/profile/_components/section-card.tsx` (helper réutilisé)
- Create: `app/(app)/profile/_components/perso-edit-form.tsx`
- Create: `app/(app)/profile/_components/race-edit-form.tsx`
- Create: `app/(app)/profile/_components/perf-edit-form.tsx`
- Create: `app/(app)/profile/_components/dispo-edit-form.tsx`
- Modify: `app/(app)/onboarding/actions.ts` (re-export pour le profile, **OU** créer un `profile/actions.ts` qui wrappe — à choisir)

- [ ] **Step 1: Refactor `/profile/page.tsx` pour rendre 4 sections en plus du Garmin Connect existant**

(NOTE: PR #8 a déjà ajouté le bloc Garmin Connect avec le badge. On garde tout ça, on AJOUTE les 4 sections en dessous.)

Le code complet de `app/(app)/profile/page.tsx` après refactor :

```typescript
import { redirect } from 'next/navigation'
import { SignOutButton } from '@/components/auth/sign-out-button'
import { Button } from '@/components/ui/button'
import { Link } from '@/components/ui/link'  // ou next/link selon convention
import { createClient } from '@/lib/supabase/server'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { PersoEditForm } from './_components/perso-edit-form'
import { RaceEditForm } from './_components/race-edit-form'
import { PerfEditForm } from './_components/perf-edit-form'
import { DispoEditForm } from './_components/dispo-edit-form'

// ... (interfaces GarminCredentialsRow + helpers existants gardés)

export default async function ProfilePage() {
  await requireOnboarded()

  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const [{ data: profile }, { data: race }, { data: garmin }] = await Promise.all([
    supabase
      .from('athlete_profiles')
      .select('*')
      .eq('user_id', user.id)
      .single(),
    supabase
      .from('race_goals')
      .select('id, race_date, race_distance, name, location, target_time_seconds, is_primary')
      .eq('user_id', user.id)
      .eq('is_primary', true)
      .maybeSingle(),
    supabase
      .from('garmin_credentials')
      .select(
        'last_sync_at, last_sync_status, initial_sync_completed_at, token_refresh_failed_at, updated_at'
      )
      .eq('user_id', user.id)
      .maybeSingle(),
  ])

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Profil</h1>
        <p className="text-muted-foreground text-sm">{user.email}</p>
      </header>

      {/* Section Garmin Connect — bloc existant de PR #8 (gardé tel quel) */}
      {/* ... */}

      <PersoEditForm
        initial={{
          first_name: profile?.first_name ?? '',
          dob: profile?.dob ?? '',
          sex: profile?.sex ?? 'M',
          city: profile?.city ?? '',
          country: profile?.country ?? '',
          consent_data_processing: profile?.consent_data_processing ?? true,
        }}
      />

      <RaceEditForm
        initial={
          race
            ? {
                race_date: race.race_date,
                race_distance: race.race_distance,
                name: race.name ?? '',
                location: race.location ?? '',
                target_time_seconds: race.target_time_seconds ?? undefined,
              }
            : null
        }
      />

      <PerfEditForm
        initial={{
          ftp_watts: profile?.ftp_watts ?? undefined,
          vma_kmh: profile?.vma_kmh ?? undefined,
          fc_max_bpm: profile?.fc_max_bpm ?? undefined,
          garmin_synced_at: profile?.garmin_synced_at ?? null,
        }}
      />

      <DispoEditForm
        initial={{
          available_days: profile?.available_days ?? [],
          hours_per_week: profile?.hours_per_week ?? undefined,
          sports_strengths: profile?.sports_strengths ?? { swim: 3, bike: 3, run: 3 },
        }}
      />

      <SignOutButton />
    </div>
  )
}
```

- [ ] **Step 2: Create the 4 edit forms — pattern**

Chaque edit form suit le même pattern : view-mode par défaut, bouton "Modifier" → bascule en edit-mode, save via la SAME Server Action que le wizard (réutilise `saveStepPerso`, `saveStepRace`, `saveStepPerf`, `saveStepDispo`).

Example pour `app/(app)/profile/_components/perso-edit-form.tsx` :

```typescript
'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepPerso } from '@/app/(app)/onboarding/actions'
import type { PersonInput } from '@/lib/onboarding/schemas'

interface Props {
  initial: PersonInput
}

export function PersoEditForm({ initial }: Readonly<Props>) {
  const [edit, setEdit] = useState(false)
  const [values, setValues] = useState(initial)
  const [loading, setLoading] = useState(false)

  if (!edit) {
    return (
      <section className="space-y-3 rounded-lg border p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Informations personnelles</h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEdit(true)
            }}
          >
            Modifier
          </Button>
        </div>
        <p className="text-sm">
          {values.first_name} · {values.dob} · {values.sex} ·{' '}
          {values.city ?? '—'}, {values.country ?? '—'}
        </p>
      </section>
    )
  }

  async function handleSave() {
    setLoading(true)
    const r = await saveStepPerso(values)
    setLoading(false)
    if (!r.success) {
      toast.error('Erreur de sauvegarde')
      return
    }
    setEdit(false)
    toast.success('Sauvegardé')
  }

  return (
    <section className="space-y-3 rounded-lg border p-6">
      <h2 className="text-lg font-semibold">Informations personnelles</h2>
      <div className="space-y-2">
        <Label>Prénom</Label>
        <Input
          value={values.first_name}
          onChange={(e) => {
            setValues({ ...values, first_name: e.target.value })
          }}
        />
      </div>
      <div className="space-y-2">
        <Label>Date de naissance</Label>
        <Input
          type="date"
          value={values.dob}
          onChange={(e) => {
            setValues({ ...values, dob: e.target.value })
          }}
        />
      </div>
      {/* ... sex, city, country fields */}
      <div className="flex gap-2">
        <Button
          onClick={() => {
            void handleSave()
          }}
          disabled={loading}
        >
          {loading ? 'Sauvegarde...' : 'Enregistrer'}
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            setEdit(false)
            setValues(initial)
          }}
          disabled={loading}
        >
          Annuler
        </Button>
      </div>
    </section>
  )
}
```

Créer les 3 autres edit forms (`race-edit-form.tsx`, `perf-edit-form.tsx`, `dispo-edit-form.tsx`) en suivant le même pattern. Le PerfEditForm ajoute un bouton "↻ Sync Garmin" qui appelle `syncGarminProfile()` (importée de `onboarding/actions`) et met à jour les champs au retour. Le RaceEditForm peut afficher en plus un bouton "+ Ajouter une autre course" qui révèle un sous-form créant une row `race_goals` avec `is_primary=false` (création seule, l'édition d'is_primary swap est hors scope MVP).

- [ ] **Step 3: Typecheck + lint + build**

```bash
pnpm typecheck && pnpm lint && pnpm build
```

- [ ] **Step 4: Manual test**

```bash
pnpm dev
```

Manuel :
1. `/profile` affiche les 4 sections en view-mode + le bloc Garmin existant
2. Clic "Modifier" sur une section → bascule en edit + save fonctionne
3. Clic "↻ Sync Garmin" sur Perf → refresh des valeurs

- [ ] **Step 5: Commit**

```bash
git add app/'(app)'/profile/
git commit -m "feat(profile): add inline edit forms for perso/race/perf/dispo sections"
```

---

## Task 16 — E2E Playwright : happy path onboarding

**Files:**
- Create: `tests/e2e/onboarding.spec.ts`

- [ ] **Step 1: Read existing Playwright config + auth helper**

```bash
ls tests/e2e/
cat playwright.config.ts
```

(Note pour exécuteur : adapter le test selon les helpers d'auth existants. Probablement il y a un fixture qui setup un user authentifié.)

- [ ] **Step 2: Write the happy path test**

```typescript
// tests/e2e/onboarding.spec.ts
import { test, expect } from '@playwright/test'

test.describe('E3 — onboarding happy path', () => {
  test('non-onboarded user is redirected, completes 4 steps, lands on /profile', async ({
    page,
  }) => {
    // Suppose une fixture qui login un user fraîchement créé sans onboarding
    // OU on appelle ici createTestUser() helper
    await page.goto('/today')
    await expect(page).toHaveURL(/\/onboarding/)

    // Étape Perso
    await page.fill('#first_name', 'Test User')
    await page.fill('#dob', '1990-04-12')
    await page.selectOption('#sex', 'M')
    await page.fill('#city', 'Toulouse')
    await page.fill('#country', 'France')
    await page.check('input[type="checkbox"]')  // consent
    await page.click('button[type="submit"]')

    // Étape Race
    await page.waitForSelector('#race_date')
    const future = new Date()
    future.setMonth(future.getMonth() + 3)
    await page.fill('#race_date', future.toISOString().slice(0, 10))
    await page.selectOption('#race_distance', 'olympique')
    await page.fill('#name', 'Test Race')
    await page.click('button[type="submit"]')

    // Étape Perf (auto-fetch mocké → vide, on remplit manuellement)
    await page.waitForSelector('#ftp')
    await page.fill('#ftp', '200')
    await page.fill('#vma', '15')
    await page.fill('#fcmax', '180')
    await page.click('button[type="submit"]')

    // Étape Dispo
    await page.waitForSelector('input[type="range"]')
    await page.fill('#hours', '6')
    // Sélectionner Lun + Mar + Sam
    await page.click('button:has-text("Lun")')
    await page.click('button:has-text("Mar")')
    await page.click('button:has-text("Sam")')
    await page.click('button[type="submit"]')

    // Finalize → /profile
    await expect(page).toHaveURL(/\/profile/)
    await expect(page.getByText('Informations personnelles')).toBeVisible()
    await expect(page.getByText('Test User')).toBeVisible()
  })
})
```

NOTE: si auto-fetch Garmin essaie de partir au step Perf et bloque le test, ajouter au début du test :

```typescript
await page.route('**/garmin/profile-sync', (route) =>
  route.fulfill({ status: 200, body: JSON.stringify({ status: 'rate_limited' }) })
)
```

- [ ] **Step 3: Run the test**

```bash
pnpm test:e2e onboarding.spec.ts
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/onboarding.spec.ts
git commit -m "test(e2e): happy path through E3 onboarding wizard"
```

---

## Task 17 — Final integration : push branch + open PR

**Files:** none

- [ ] **Step 1: Run full quality gates one last time**

```bash
cd worker && uv run pytest -q && uv run ruff check . && uv run mypy src/
cd ..
pnpm lint && pnpm typecheck && pnpm test --run && pnpm build
```

Expected: all green.

- [ ] **Step 2: Push branch**

```bash
git push -u origin feat/e3-onboarding
```

- [ ] **Step 3: Open PR**

```bash
gh pr create --base main --head feat/e3-onboarding \
  --title "feat(e3): profile & onboarding (wizard + auto-fetch Garmin + /profile editable)" \
  --body "$(cat docs/superpowers/specs/2026-05-18-e3-onboarding-design.md | head -50)
... (résumé du contenu + lien vers le spec)"
```

- [ ] **Step 4: Wait for CI, fix any failures, then ping user for review**

```bash
gh pr checks
```

Expected: all green (CI worker, CI frontend, Lighthouse, Docker build, SonarQube).

Note pour l'exécuteur : si Docker rebuild échoue à cause d'un test worker, fix avant de demander la review.

---

## Quality gates de référence (toutes tasks)

À chaque commit important, vérifier :

| Couche | Commande | Doit retourner |
|---|---|---|
| Worker lint | `cd worker && uv run ruff check .` | All checks passed |
| Worker types | `cd worker && uv run mypy src/` | Success |
| Worker tests | `cd worker && uv run pytest -q` | 55+ passed |
| Frontend lint | `pnpm lint` | 0 errors |
| Frontend types | `pnpm typecheck` | 0 errors |
| Frontend tests | `pnpm test --run` | All passed |
| Frontend build | `pnpm build` | Compiled successfully |
| Frontend e2e | `pnpm test:e2e` | All passed |

Si un quality gate échoue, ARRÊTER, fixer, re-tester, puis continuer la task suivante.

---

## Cas d'erreur fréquents (anticipés)

| Symptôme | Cause probable | Fix |
|---|---|---|
| `pnpm typecheck` rouge sur `step-*-form` imports | Wizard committé avant les forms (intermédiaire) | Continuer Task 11+, typecheck redeviendra vert |
| Server Action retourne 500 en local | `WORKER_URL` mal défini dans `.env.local` | Vérifier `WORKER_URL=http://localhost:8080` |
| Test pytest échoue sur `_make_creds_row` | TokenCipher demande `FERNET_KEY` dans env | Setup conftest.py (déjà fait, voir tests/conftest.py) |
| Redirect boucle `/onboarding` ↔ `/profile` | Layout redirect appliqué SUR /onboarding aussi | Bien utiliser le guard helper, pas le redirect dans layout |
| Auto-fetch part en boucle infinie au mount | `useEffect` deps array contient un objet qui change à chaque render | Vérifier la deps `[syncedAt]` — c'est une string nullable, doit être stable |
