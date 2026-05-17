# E2 — Garmin Sync Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python worker (deployed on Fly.io) that syncs Garmin Connect data (activities, sleep, HRV, daily metrics, body composition) for each user once a day, plus an on-demand HTTP endpoint, with encrypted OAuth tokens and proper RLS-protected storage in Supabase.

**Architecture:** A FastAPI service runs in a Fly.io machine. A scheduled Fly.io machine fires daily at 05:00 UTC, queries `public.garmin_credentials` for all linked users, decrypts each user's Garmin OAuth tokens with Fernet, calls Garmin Connect via `python-garminconnect`, normalizes the payloads into our schema, and upserts into `public.activities`, `public.daily_metrics`, `public.sleep`, `public.hrv`, `public.body_composition`. The Next.js app has a `/profile/garmin` page where the user enters their Garmin credentials (with MFA support) — these credentials are sent through a Server Action that forwards to the worker, which authenticates with Garmin, stores tokens encrypted, and returns success/needs-MFA.

**Tech Stack:** Python 3.12, FastAPI 0.115+, Pydantic v2, `python-garminconnect` 0.3.2+, `supabase-py` 2.x, `cryptography` (Fernet), `httpx`, `pytest` + `pytest-asyncio` + `respx`, `ruff`, `mypy --strict`. Deployed via Docker on Fly.io. Sentry SDK for monitoring.

**Spec reference:** `docs/superpowers/specs/2026-05-17-garmin-training-design.md` § 7 (E2).

> ⚠️ **Execution order**: This plan assumes E1 + E1b are complete (Next.js scaffold, Supabase schema, Vercel deploy, quality gates). Tables `athlete_profiles` and `garmin_credentials` already exist. The DB migrations in this plan add new tables (`activities`, `daily_metrics`, `sleep`, `hrv`, `body_composition`) and a few columns to `garmin_credentials`.

---

## File Structure

```
garmin_training/
├── worker/                              ← NEW: Python worker project
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── fly.toml
│   ├── .python-version
│   ├── .dockerignore
│   ├── README.md
│   ├── src/
│   │   └── garmin_sync/
│   │       ├── __init__.py
│   │       ├── main.py                  # FastAPI app entry
│   │       ├── config.py                # Pydantic settings (env)
│   │       ├── crypto.py                # Fernet encrypt/decrypt
│   │       ├── supabase_client.py       # Supabase service-role client
│   │       ├── garmin_client.py         # python-garminconnect wrapper
│   │       ├── auth.py                  # JWT verification (Supabase tokens)
│   │       ├── sync.py                  # Per-user sync orchestration
│   │       ├── cron.py                  # Cron entry point
│   │       └── transformers/
│   │           ├── __init__.py
│   │           ├── activities.py
│   │           ├── daily.py
│   │           ├── sleep.py
│   │           ├── hrv.py
│   │           └── body.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_crypto.py
│       ├── test_config.py
│       ├── test_transformers/
│       │   ├── __init__.py
│       │   ├── test_activities.py
│       │   ├── test_daily.py
│       │   ├── test_sleep.py
│       │   ├── test_hrv.py
│       │   └── test_body.py
│       └── test_sync.py
├── supabase/migrations/
│   ├── 20260517000002_e2_activities_table.sql
│   ├── 20260517000003_e2_daily_metrics_table.sql
│   ├── 20260517000004_e2_sleep_table.sql
│   ├── 20260517000005_e2_hrv_table.sql
│   ├── 20260517000006_e2_body_composition_table.sql
│   └── 20260517000007_e2_garmin_credentials_columns.sql
├── app/(app)/profile/garmin/
│   └── page.tsx                         # NEW: Garmin connect UI
├── components/garmin/
│   ├── connect-form.tsx                 # email/password form
│   └── mfa-form.tsx                     # MFA code form
├── app/actions/
│   └── garmin-auth.ts                   # Server Actions calling worker
├── lib/
│   └── worker.ts                        # Worker HTTP client (frontend → worker)
└── .github/workflows/
    └── worker-ci.yml                    # NEW: Python worker CI
```

**Key boundaries:**
- `worker/` is a standalone Python project; the Next.js codebase doesn't import from it. Comms are HTTP-only.
- `worker/src/garmin_sync/transformers/*` each handle one Garmin data category — keeps files focused (~100 lines each).
- `app/actions/garmin-auth.ts` is the ONLY place the frontend talks to the worker.

---

## Prerequisites

Before starting:

- [ ] E1 + E1b plans completed and deployed
- [ ] Python 3.12+ available (`python3 --version`) — install via `uv python install 3.12` or pyenv if missing
- [ ] `uv` package manager installed (`uv --version`) — install: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [ ] Fly.io CLI installed (`flyctl version`) — install: `curl -L https://fly.io/install.sh | sh`
- [ ] Fly.io account + auth (`flyctl auth login`)
- [ ] Supabase project's **service role key** (Dashboard → Project Settings → API → `service_role` secret). Will be stored in Fly.io secrets, never in git.
- [ ] A Garmin Connect account for testing
- [ ] Sentry account (free tier) — optional but recommended

---

## Task 1: Initialize Python worker project

**Files:**
- Create: `worker/pyproject.toml`, `worker/.python-version`, `worker/.dockerignore`, `worker/src/garmin_sync/__init__.py`, `worker/tests/__init__.py`, `worker/tests/conftest.py`

- [ ] **Step 1.1: Create the worker directory and Python version pin**

```bash
mkdir -p worker/src/garmin_sync/transformers worker/tests/test_transformers
cd worker
echo "3.12" > .python-version
```

- [ ] **Step 1.2: Create `worker/pyproject.toml`**

```toml
[project]
name = "garmin-sync"
version = "0.1.0"
description = "Garmin Connect sync worker for Garmin Training Coach"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "python-garminconnect>=0.3.2",
  "supabase>=2.10",
  "cryptography>=43",
  "httpx>=0.27",
  "pyjwt>=2.9",
  "sentry-sdk[fastapi]>=2.18",
]

[dependency-groups]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "pytest-cov>=5.0",
  "respx>=0.21",
  "ruff>=0.7",
  "mypy>=1.13",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
  "E", "F", "W",     # pycodestyle + pyflakes
  "I",                # isort
  "B",                # bugbear
  "UP",               # pyupgrade
  "S",                # bandit (security)
  "RUF",              # ruff-specific
  "ASYNC",            # async correctness
  "SIM",              # simplify
  "PT",               # pytest style
]
ignore = ["S101"]  # allow assert in tests

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S105", "S106"]  # hardcoded test passwords are OK

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra --strict-markers"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/garmin_sync"]
```

- [ ] **Step 1.3: Create empty package and test init files**

`worker/src/garmin_sync/__init__.py`:

```python
"""Garmin Connect sync worker."""

__version__ = "0.1.0"
```

`worker/tests/__init__.py`: empty.

`worker/tests/conftest.py`:

```python
"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide deterministic env vars so config.Settings() always loads."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key-test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "jwt-secret-test")
    monkeypatch.setenv("FERNET_KEY", "Mk7-aBcDEfGhIjKlMnOpQrStUvWxYz0123456789abc=")
    monkeypatch.setenv("WORKER_SHARED_TOKEN", "shared-token-test")
    monkeypatch.setenv("ENV", "test")
    # Disable Sentry in tests
    monkeypatch.delenv("SENTRY_DSN", raising=False)
```

- [ ] **Step 1.4: Create `worker/.dockerignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
tests/
*.md
.env*
.git/
.github/
```

- [ ] **Step 1.5: Install deps and verify**

```bash
cd worker
uv sync --all-groups
uv run python -c "import garmin_sync; print(garmin_sync.__version__)"
```

Expected: `0.1.0`.

- [ ] **Step 1.6: Run lint and typecheck (should pass on empty project)**

```bash
cd worker
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```

Expected: all 3 commands exit 0 (no files to lint or check yet).

- [ ] **Step 1.7: Commit**

```bash
cd ..
git add worker/
git commit -m "feat(worker): scaffold Python worker project with uv, ruff, mypy strict"
```

---

## Task 2: Worker configuration module

**Files:**
- Create: `worker/src/garmin_sync/config.py`, `worker/tests/test_config.py`

- [ ] **Step 2.1: Write the failing test**

`worker/tests/test_config.py`:

```python
"""Tests for config.Settings — env var loading and validation."""

from __future__ import annotations

import pytest

from garmin_sync.config import Settings


def test_settings_loads_from_env() -> None:
    s = Settings()
    assert str(s.supabase_url) == "https://example.supabase.co/"
    assert s.supabase_service_role_key.get_secret_value() == "service-role-key-test"
    assert s.fernet_key.get_secret_value() == "Mk7-aBcDEfGhIjKlMnOpQrStUvWxYz0123456789abc="
    assert s.worker_shared_token.get_secret_value() == "shared-token-test"
    assert s.env == "test"


def test_settings_rejects_invalid_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "not-a-url")
    with pytest.raises(ValueError, match="supabase_url"):
        Settings()


def test_settings_rejects_short_fernet_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FERNET_KEY", "too-short")
    with pytest.raises(ValueError, match="fernet_key"):
        Settings()
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
cd worker && uv run pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'garmin_sync.config'`.

- [ ] **Step 2.3: Implement `worker/src/garmin_sync/config.py`**

```python
"""Application configuration loaded from environment variables."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All secrets come from env vars (never committed)."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)

    supabase_url: HttpUrl = Field(alias="SUPABASE_URL")
    supabase_service_role_key: SecretStr = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: SecretStr = Field(alias="SUPABASE_JWT_SECRET")
    fernet_key: SecretStr = Field(alias="FERNET_KEY")
    worker_shared_token: SecretStr = Field(alias="WORKER_SHARED_TOKEN")
    env: Literal["dev", "test", "staging", "prod"] = Field(default="dev", alias="ENV")
    sentry_dsn: SecretStr | None = Field(default=None, alias="SENTRY_DSN")

    @field_validator("fernet_key")
    @classmethod
    def _validate_fernet_key(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        # Fernet keys are 44-char url-safe base64-encoded 32-byte values
        if len(raw) != 44 or not raw.endswith("="):
            msg = f"fernet_key must be a 44-char url-safe base64 string, got len={len(raw)}"
            raise ValueError(msg)
        return v


def get_settings() -> Settings:
    """Convenience accessor — Pydantic re-reads env on construction."""
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
cd worker && uv run pytest tests/test_config.py -v
```

Expected: PASS, 3 tests.

- [ ] **Step 2.5: Commit**

```bash
cd ..
git add worker/
git commit -m "feat(worker): config module with Pydantic settings + env validation"
```

---

## Task 3: Crypto module (Fernet for token encryption)

**Files:**
- Create: `worker/src/garmin_sync/crypto.py`, `worker/tests/test_crypto.py`

- [ ] **Step 3.1: Write the failing tests**

`worker/tests/test_crypto.py`:

```python
"""Tests for crypto.TokenCipher — Fernet encryption of OAuth tokens."""

from __future__ import annotations

import pytest

from garmin_sync.crypto import TokenCipher, generate_fernet_key


def test_roundtrip_encrypt_decrypt() -> None:
    cipher = TokenCipher()
    plaintext = '{"access_token": "abc", "refresh_token": "def"}'
    encrypted = cipher.encrypt(plaintext)
    decrypted = cipher.decrypt(encrypted)
    assert decrypted == plaintext


def test_encrypt_produces_different_bytes_each_time() -> None:
    cipher = TokenCipher()
    plaintext = "same input"
    a = cipher.encrypt(plaintext)
    b = cipher.encrypt(plaintext)
    assert a != b  # Fernet uses random IV → ciphertext differs


def test_decrypt_rejects_tampered_data() -> None:
    cipher = TokenCipher()
    encrypted = cipher.encrypt("payload")
    tampered = encrypted[:-2] + b"00"
    with pytest.raises(ValueError, match="invalid|corrupt|InvalidToken"):
        cipher.decrypt(tampered)


def test_generate_fernet_key_is_valid() -> None:
    key = generate_fernet_key()
    assert len(key) == 44
    assert key.endswith("=")
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
cd worker && uv run pytest tests/test_crypto.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3.3: Implement `worker/src/garmin_sync/crypto.py`**

```python
"""Symmetric encryption (Fernet) for sensitive OAuth tokens at rest."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from garmin_sync.config import get_settings


def generate_fernet_key() -> str:
    """Helper for ops: generate a new Fernet key (run once, store as env var)."""
    return Fernet.generate_key().decode("ascii")


class TokenCipher:
    """Wraps Fernet symmetric encryption with the project's key from settings."""

    def __init__(self, key: bytes | None = None) -> None:
        if key is None:
            key = get_settings().fernet_key.get_secret_value().encode("ascii")
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as e:
            msg = "ciphertext is invalid or corrupted"
            raise ValueError(msg) from e
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
cd worker && uv run pytest tests/test_crypto.py -v
```

Expected: PASS, 4 tests.

- [ ] **Step 3.5: Commit**

```bash
cd ..
git add worker/
git commit -m "feat(worker): Fernet-based token cipher with roundtrip + tamper tests"
```

---

## Task 4: Supabase service-role client wrapper

**Files:**
- Create: `worker/src/garmin_sync/supabase_client.py`, `worker/tests/test_supabase_client.py`

- [ ] **Step 4.1: Write the failing test**

`worker/tests/test_supabase_client.py`:

```python
"""Tests for the Supabase service-role client wrapper."""

from __future__ import annotations

from garmin_sync.supabase_client import get_admin_client


def test_admin_client_is_constructed_once() -> None:
    a = get_admin_client()
    b = get_admin_client()
    assert a is b  # cached singleton


def test_admin_client_uses_service_role_key() -> None:
    client = get_admin_client()
    # supabase-py stores headers including the auth header
    headers = client.postgrest.session.headers
    # Should not be empty; the actual key is the service role from env
    assert "Authorization" in headers or "apikey" in headers
```

- [ ] **Step 4.2: Run test (expect fail)**

```bash
cd worker && uv run pytest tests/test_supabase_client.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 4.3: Implement `worker/src/garmin_sync/supabase_client.py`**

```python
"""Supabase Postgres client using the service role key — bypasses RLS by design.

This is ONLY used by the worker. The worker accesses every user's data, so it
needs service role. RLS still protects user-facing access (from the Next.js app
via the anon key).
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from garmin_sync.config import get_settings


@lru_cache(maxsize=1)
def get_admin_client() -> Client:
    """Returns a cached service-role Supabase client."""
    settings = get_settings()
    return create_client(
        str(settings.supabase_url),
        settings.supabase_service_role_key.get_secret_value(),
    )
```

- [ ] **Step 4.4: Run test to verify it passes**

```bash
cd worker && uv run pytest tests/test_supabase_client.py -v
```

Expected: PASS, 2 tests.

- [ ] **Step 4.5: Commit**

```bash
cd ..
git add worker/
git commit -m "feat(worker): cached Supabase service-role admin client"
```

---

## Task 5: DB migrations — new tables for Garmin data

**Files:**
- Create: `supabase/migrations/20260517000002_e2_activities_table.sql`, `20260517000003_e2_daily_metrics_table.sql`, `20260517000004_e2_sleep_table.sql`, `20260517000005_e2_hrv_table.sql`, `20260517000006_e2_body_composition_table.sql`, `20260517000007_e2_garmin_credentials_columns.sql`

- [ ] **Step 5.1: Create activities migration**

`supabase/migrations/20260517000002_e2_activities_table.sql`:

```sql
-- E2 — activities table — one row per Garmin activity
create table public.activities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  garmin_activity_id bigint not null,
  start_time timestamptz not null,
  sport text not null,
  sub_sport text,
  duration_s integer not null check (duration_s >= 0),
  distance_m numeric(10,2) check (distance_m is null or distance_m >= 0),
  tss numeric(6,2) check (tss is null or tss >= 0),
  hr_avg integer check (hr_avg is null or hr_avg between 30 and 240),
  hr_max integer check (hr_max is null or hr_max between 30 and 240),
  power_avg integer check (power_avg is null or power_avg between 0 and 2000),
  power_max integer check (power_max is null or power_max between 0 and 2000),
  pace_avg_s_per_km numeric(6,2),
  elevation_gain_m integer,
  calories integer,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (user_id, garmin_activity_id)
);

create index activities_user_start_idx on public.activities (user_id, start_time desc);
create index activities_user_sport_idx on public.activities (user_id, sport);

alter table public.activities enable row level security;

create policy "users read own activities"
  on public.activities for select
  using (auth.uid() = user_id);
```

- [ ] **Step 5.2: Create daily_metrics migration**

`supabase/migrations/20260517000003_e2_daily_metrics_table.sql`:

```sql
-- E2 — daily metrics: one row per (user, date)
create table public.daily_metrics (
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  resting_hr integer check (resting_hr is null or resting_hr between 30 and 120),
  body_battery_low integer check (body_battery_low is null or body_battery_low between 0 and 100),
  body_battery_high integer check (body_battery_high is null or body_battery_high between 0 and 100),
  stress_avg integer check (stress_avg is null or stress_avg between 0 and 100),
  steps integer check (steps is null or steps >= 0),
  active_calories integer check (active_calories is null or active_calories >= 0),
  total_calories integer check (total_calories is null or total_calories >= 0),
  readiness_score numeric(5,2) check (readiness_score is null or readiness_score between 0 and 100),
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, date)
);

create index daily_metrics_user_date_idx on public.daily_metrics (user_id, date desc);

alter table public.daily_metrics enable row level security;

create policy "users read own daily_metrics"
  on public.daily_metrics for select
  using (auth.uid() = user_id);

create trigger trg_daily_metrics_updated_at
  before update on public.daily_metrics
  for each row execute procedure public.touch_updated_at();
```

- [ ] **Step 5.3: Create sleep migration**

`supabase/migrations/20260517000004_e2_sleep_table.sql`:

```sql
-- E2 — sleep — one row per (user, date)
create table public.sleep (
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  sleep_duration_s integer check (sleep_duration_s is null or sleep_duration_s between 0 and 86400),
  sleep_score integer check (sleep_score is null or sleep_score between 0 and 100),
  deep_sleep_s integer,
  light_sleep_s integer,
  rem_sleep_s integer,
  awake_s integer,
  bedtime timestamptz,
  wake_time timestamptz,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, date)
);

create index sleep_user_date_idx on public.sleep (user_id, date desc);

alter table public.sleep enable row level security;

create policy "users read own sleep"
  on public.sleep for select
  using (auth.uid() = user_id);
```

- [ ] **Step 5.4: Create hrv migration**

`supabase/migrations/20260517000005_e2_hrv_table.sql`:

```sql
-- E2 — HRV — one row per (user, date)
create table public.hrv (
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  hrv_rmssd numeric(6,2) check (hrv_rmssd is null or hrv_rmssd between 0 and 300),
  hrv_status text check (
    hrv_status is null or hrv_status in ('balanced', 'unbalanced', 'low', 'poor', 'no_status')
  ),
  hrv_weekly_avg numeric(6,2),
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, date)
);

create index hrv_user_date_idx on public.hrv (user_id, date desc);

alter table public.hrv enable row level security;

create policy "users read own hrv"
  on public.hrv for select
  using (auth.uid() = user_id);
```

- [ ] **Step 5.5: Create body_composition migration**

`supabase/migrations/20260517000006_e2_body_composition_table.sql`:

```sql
-- E2 — body composition — one row per (user, date)
create table public.body_composition (
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  weight_kg numeric(5,2) check (weight_kg is null or weight_kg between 20 and 300),
  body_fat_pct numeric(4,1) check (body_fat_pct is null or body_fat_pct between 1 and 70),
  muscle_mass_kg numeric(5,2),
  bone_mass_kg numeric(4,2),
  body_water_pct numeric(4,1),
  visceral_fat numeric(4,1),
  bmi numeric(4,1),
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, date)
);

create index body_composition_user_date_idx on public.body_composition (user_id, date desc);

alter table public.body_composition enable row level security;

create policy "users read own body_composition"
  on public.body_composition for select
  using (auth.uid() = user_id);
```

- [ ] **Step 5.6: Add columns to garmin_credentials**

`supabase/migrations/20260517000007_e2_garmin_credentials_columns.sql`:

```sql
-- E2 — extend garmin_credentials with first-sync flag and error state
alter table public.garmin_credentials
  add column if not exists initial_sync_completed_at timestamptz,
  add column if not exists token_refresh_failed_at timestamptz;

comment on column public.garmin_credentials.initial_sync_completed_at is
  'When the 90-day backfill finished. Null = not yet, or auth lost.';
comment on column public.garmin_credentials.token_refresh_failed_at is
  'Last time Garmin auth refresh failed; user must reconnect when set.';
```

- [ ] **Step 5.7: Apply all 6 migrations via Supabase MCP**

For each migration file, use `mcp__supabase__apply_migration` with `project_id=peiyrqplymdlmlpsbqzu`, `name=e2_activities_table` (and so on for each), and the SQL content as `query`.

Apply in order: activities → daily_metrics → sleep → hrv → body_composition → garmin_credentials_columns.

Verify with `mcp__supabase__list_tables` (schema `public`): all 5 new tables should appear with `rls_enabled: true`.

Verify with `mcp__supabase__get_advisors` (type `security`): no new advisor warnings.

- [ ] **Step 5.8: Commit all migrations**

```bash
git add supabase/migrations/2026051700000{2,3,4,5,6,7}*
git commit -m "feat(db): E2 schema — activities + daily_metrics + sleep + hrv + body_composition + RLS"
```

---

## Task 6: JWT verification (for inbound HTTP requests from Next.js)

**Files:**
- Create: `worker/src/garmin_sync/auth.py`, `worker/tests/test_auth.py`

- [ ] **Step 6.1: Write the failing tests**

`worker/tests/test_auth.py`:

```python
"""Tests for JWT verification of Supabase-issued user tokens."""

from __future__ import annotations

import time

import jwt
import pytest

from garmin_sync.auth import (
    AuthError,
    verify_shared_token,
    verify_supabase_jwt,
)


def _make_jwt(secret: str, sub: str, exp_offset: int = 3600) -> str:
    payload = {"sub": sub, "exp": int(time.time()) + exp_offset, "role": "authenticated"}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_verify_supabase_jwt_returns_user_id() -> None:
    token = _make_jwt("jwt-secret-test", "user-abc-123")
    assert verify_supabase_jwt(token) == "user-abc-123"


def test_verify_supabase_jwt_rejects_expired_token() -> None:
    token = _make_jwt("jwt-secret-test", "u1", exp_offset=-60)
    with pytest.raises(AuthError, match="expired"):
        verify_supabase_jwt(token)


def test_verify_supabase_jwt_rejects_wrong_signature() -> None:
    token = _make_jwt("wrong-secret", "u1")
    with pytest.raises(AuthError):
        verify_supabase_jwt(token)


def test_verify_shared_token_accepts_match() -> None:
    assert verify_shared_token("shared-token-test") is True


def test_verify_shared_token_rejects_mismatch() -> None:
    assert verify_shared_token("nope") is False
```

- [ ] **Step 6.2: Run tests (expect fail)**

```bash
cd worker && uv run pytest tests/test_auth.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 6.3: Implement `worker/src/garmin_sync/auth.py`**

```python
"""Authentication for inbound requests.

Two modes:
  1. End-user requests (from Next.js Server Action on behalf of the user) carry
     a Supabase-issued JWT in the Authorization header. We verify the signature
     using SUPABASE_JWT_SECRET and trust the `sub` claim as the user id.
  2. Cron/admin requests (from Fly.io scheduled machine or operator) carry the
     WORKER_SHARED_TOKEN secret. Strictly equality-compared.
"""

from __future__ import annotations

import hmac

import jwt

from garmin_sync.config import get_settings


class AuthError(Exception):
    """Raised when authentication fails."""


def verify_supabase_jwt(token: str) -> str:
    """Verify a Supabase-issued JWT and return the user id (`sub` claim).

    Raises AuthError on any failure (expired, invalid signature, missing sub).
    """
    secret = get_settings().supabase_jwt_secret.get_secret_value()
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=None,
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as e:
        msg = "jwt expired"
        raise AuthError(msg) from e
    except jwt.InvalidTokenError as e:
        msg = "jwt invalid"
        raise AuthError(msg) from e

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        msg = "jwt missing 'sub' claim"
        raise AuthError(msg)
    return sub


def verify_shared_token(presented: str) -> bool:
    """Constant-time compare of the operator/cron shared token."""
    expected = get_settings().worker_shared_token.get_secret_value()
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))
```

- [ ] **Step 6.4: Run tests to pass**

(`pyjwt` is already declared in `pyproject.toml` — already installed at Task 1.5.)

```bash
uv run pytest tests/test_auth.py -v
```

Expected: PASS, 5 tests.

- [ ] **Step 6.5: Commit**

```bash
cd ..
git add worker/
git commit -m "feat(worker): JWT + shared-token verification for inbound auth"
```

---

## Task 7: Garmin client wrapper

**Files:**
- Create: `worker/src/garmin_sync/garmin_client.py`, `worker/tests/test_garmin_client.py`

- [ ] **Step 7.1: Write the failing tests**

`worker/tests/test_garmin_client.py`:

```python
"""Tests for the Garmin client wrapper — happy path + MFA + auth failure."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.garmin_client import (
    GarminAuthError,
    GarminMFARequired,
    login_with_credentials,
    login_with_tokens,
    submit_mfa_code,
)


@pytest.fixture
def fake_garmin() -> Iterator[MagicMock]:
    with patch("garmin_sync.garmin_client.Garmin") as cls:
        yield cls


def test_login_with_credentials_no_mfa_returns_token_dict(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    instance.login.return_value = (None, None)  # no MFA
    instance.garth.dumps.return_value = '{"oauth_token": "abc"}'

    tokens = login_with_credentials("user@example.com", "pwd")

    assert tokens == '{"oauth_token": "abc"}'
    fake_garmin.assert_called_once_with(email="user@example.com", password="pwd", is_cn=False)
    instance.login.assert_called_once_with()


def test_login_with_credentials_mfa_required_raises(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    instance.login.return_value = ("needs_mfa", instance)  # tuple shape signals MFA

    with pytest.raises(GarminMFARequired) as exc:
        login_with_credentials("user@example.com", "pwd")
    assert exc.value.challenge is not None  # opaque continuation object


def test_submit_mfa_code_completes_login(fake_garmin: MagicMock) -> None:
    challenge = MagicMock()
    challenge.resume_login.return_value = None
    challenge.garth.dumps.return_value = '{"oauth_token": "xyz"}'

    tokens = submit_mfa_code(challenge, "123456")

    assert tokens == '{"oauth_token": "xyz"}'
    challenge.resume_login.assert_called_once_with("123456")


def test_login_with_tokens_restores_session(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    client = login_with_tokens('{"oauth_token": "abc"}')
    assert client is instance
    instance.garth.loads.assert_called_once_with('{"oauth_token": "abc"}')
    instance.login.assert_called_once_with()  # confirms session validity


def test_login_with_credentials_invalid_creds_raises(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    # python-garminconnect raises GarminConnectAuthenticationError on bad creds;
    # we wrap it in our own GarminAuthError.
    from garminconnect import GarminConnectAuthenticationError
    instance.login.side_effect = GarminConnectAuthenticationError("nope")

    with pytest.raises(GarminAuthError):
        login_with_credentials("user@example.com", "pwd")


def test_get_activities_calls_lib(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    instance.get_activities_by_date.return_value = [{"activityId": 1}]
    client = login_with_tokens("{}")
    result: list[dict[str, Any]] = client.get_activities_by_date("2026-01-01", "2026-01-31")
    assert result == [{"activityId": 1}]
```

- [ ] **Step 7.2: Run tests (expect fail)**

```bash
cd worker && uv run pytest tests/test_garmin_client.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 7.3: Implement `worker/src/garmin_sync/garmin_client.py`**

```python
"""Thin wrapper over python-garminconnect that exposes the operations we need
and translates library exceptions into our domain types.
"""

from __future__ import annotations

from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


class GarminError(Exception):
    """Generic Garmin error."""


class GarminAuthError(GarminError):
    """Garmin rejected our credentials or expired tokens."""


class GarminMFARequired(GarminError):
    """Garmin returned an MFA challenge. Carry `challenge` to resume."""

    def __init__(self, challenge: Any) -> None:
        super().__init__("MFA required")
        self.challenge = challenge


class GarminRateLimitError(GarminError):
    """Garmin rate-limited us; back off."""


def login_with_credentials(email: str, password: str) -> str:
    """Log in to Garmin Connect with email/password.

    Returns the serialized garth session as a JSON string (to be encrypted and
    stored in `garmin_credentials.oauth_tokens_encrypted`).

    Raises:
        GarminAuthError: invalid credentials.
        GarminMFARequired: MFA needed — call submit_mfa_code(challenge, code).
        GarminRateLimitError: too many login attempts.
    """
    client = Garmin(email=email, password=password, is_cn=False)
    try:
        result = client.login()
    except GarminConnectAuthenticationError as e:
        msg = "invalid Garmin credentials"
        raise GarminAuthError(msg) from e
    except GarminConnectTooManyRequestsError as e:
        msg = "rate limited by Garmin"
        raise GarminRateLimitError(msg) from e
    except GarminConnectConnectionError as e:
        msg = "connection error reaching Garmin"
        raise GarminError(msg) from e

    if isinstance(result, tuple) and result[0] == "needs_mfa":
        # garminconnect's MFA flow returns a continuation we resume later
        raise GarminMFARequired(challenge=result[1])

    return client.garth.dumps()  # type: ignore[no-any-return]


def submit_mfa_code(challenge: Any, code: str) -> str:
    """Resume an MFA login with the user-provided code."""
    try:
        challenge.resume_login(code)
    except GarminConnectAuthenticationError as e:
        msg = "MFA code invalid"
        raise GarminAuthError(msg) from e
    return challenge.garth.dumps()  # type: ignore[no-any-return]


def login_with_tokens(serialized_session: str) -> Garmin:
    """Restore a Garmin client from previously dumped garth tokens.

    Issues a refresh login() to confirm the session is still valid. Raises
    GarminAuthError if tokens are expired and need re-auth.
    """
    client = Garmin()
    client.garth.loads(serialized_session)
    try:
        client.login()  # refresh, validates tokens
    except GarminConnectAuthenticationError as e:
        msg = "Garmin session expired"
        raise GarminAuthError(msg) from e
    return client
```

- [ ] **Step 7.4: Run tests to pass**

```bash
cd worker && uv run pytest tests/test_garmin_client.py -v
```

Expected: PASS, 6 tests.

- [ ] **Step 7.5: Commit**

```bash
cd ..
git add worker/
git commit -m "feat(worker): Garmin client wrapper with MFA + auth error mapping"
```

---

## Task 8: Transformers — activities

**Files:**
- Create: `worker/src/garmin_sync/transformers/__init__.py`, `worker/src/garmin_sync/transformers/activities.py`, `worker/tests/test_transformers/test_activities.py`

- [ ] **Step 8.1: Write the failing tests**

`worker/tests/test_transformers/__init__.py`: empty.

`worker/tests/test_transformers/test_activities.py`:

```python
"""Tests for activities transformer: Garmin API JSON → our DB row."""

from __future__ import annotations

from garmin_sync.transformers.activities import transform_activity


def test_transform_basic_running_activity() -> None:
    raw = {
        "activityId": 12345,
        "activityName": "Easy run",
        "startTimeGMT": "2026-05-10 07:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 3600.0,
        "distance": 10000.0,
        "averageHR": 145,
        "maxHR": 168,
        "calories": 700,
        "elevationGain": 50.0,
        "averageSpeed": 2.78,  # m/s = ~6:00/km
    }
    user_id = "11111111-1111-1111-1111-111111111111"
    row = transform_activity(user_id=user_id, raw=raw)

    assert row["user_id"] == user_id
    assert row["garmin_activity_id"] == 12345
    assert row["sport"] == "running"
    assert row["duration_s"] == 3600
    assert row["distance_m"] == 10000.0
    assert row["hr_avg"] == 145
    assert row["hr_max"] == 168
    assert row["elevation_gain_m"] == 50
    assert row["calories"] == 700
    # pace = 1000 / 2.78 / 60 → no, pace_avg_s_per_km = 1000 / 2.78 ≈ 360
    assert row["pace_avg_s_per_km"] is not None
    assert 355 <= row["pace_avg_s_per_km"] <= 365
    assert row["raw"] == raw


def test_transform_cycling_with_power() -> None:
    raw = {
        "activityId": 99,
        "startTimeGMT": "2026-05-10 09:00:00",
        "activityType": {"typeKey": "cycling"},
        "duration": 7200.0,
        "distance": 80000.0,
        "averagePower": 220,
        "maxPower": 450,
        "averageHR": 150,
    }
    row = transform_activity(user_id="u1", raw=raw)
    assert row["sport"] == "cycling"
    assert row["power_avg"] == 220
    assert row["power_max"] == 450


def test_transform_swim_no_distance_pace() -> None:
    raw = {
        "activityId": 7,
        "startTimeGMT": "2026-05-10 18:00:00",
        "activityType": {"typeKey": "lap_swimming"},
        "duration": 1800.0,
        "distance": 2000.0,
    }
    row = transform_activity(user_id="u1", raw=raw)
    assert row["sport"] == "lap_swimming"
    assert row["distance_m"] == 2000.0
    # No averageSpeed → no pace
    assert row["pace_avg_s_per_km"] is None


def test_transform_handles_null_fields_gracefully() -> None:
    raw = {
        "activityId": 1,
        "startTimeGMT": "2026-05-10 08:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 0.0,
        "distance": None,
        "averageHR": None,
    }
    row = transform_activity(user_id="u1", raw=raw)
    assert row["distance_m"] is None
    assert row["hr_avg"] is None
    assert row["duration_s"] == 0
```

- [ ] **Step 8.2: Run tests (expect fail)**

```bash
cd worker && uv run pytest tests/test_transformers/test_activities.py -v
```

Expected: FAIL.

- [ ] **Step 8.3: Implement `worker/src/garmin_sync/transformers/__init__.py`**

```python
"""Pure functions that translate Garmin API payloads into DB row dicts."""
```

- [ ] **Step 8.4: Implement `worker/src/garmin_sync/transformers/activities.py`**

```python
"""Transform a Garmin activity payload into an `activities` row."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Garmin returns "YYYY-MM-DD HH:MM:SS" assumed UTC
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _pace_s_per_km(avg_speed_m_s: float | None) -> float | None:
    if not avg_speed_m_s or avg_speed_m_s <= 0:
        return None
    return round(1000.0 / avg_speed_m_s, 2)


def transform_activity(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a Garmin activity dict into our `activities` table row.

    Pure function — no I/O. The caller decides whether to insert/upsert.
    """
    start = _parse_dt(raw.get("startTimeGMT"))
    activity_type = raw.get("activityType") or {}
    return {
        "user_id": user_id,
        "garmin_activity_id": int(raw["activityId"]),
        "start_time": start.isoformat() if start else None,
        "sport": activity_type.get("typeKey", "unknown"),
        "sub_sport": activity_type.get("parentTypeId"),
        "duration_s": int(raw.get("duration") or 0),
        "distance_m": float(raw["distance"]) if raw.get("distance") is not None else None,
        "tss": None,  # Garmin doesn't expose TSS directly; computed in E4
        "hr_avg": _to_int(raw.get("averageHR")),
        "hr_max": _to_int(raw.get("maxHR")),
        "power_avg": _to_int(raw.get("averagePower")),
        "power_max": _to_int(raw.get("maxPower")),
        "pace_avg_s_per_km": _pace_s_per_km(raw.get("averageSpeed")),
        "elevation_gain_m": _to_int(raw.get("elevationGain")),
        "calories": _to_int(raw.get("calories")),
        "raw": raw,
    }


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 8.5: Run tests to pass**

```bash
cd worker && uv run pytest tests/test_transformers/test_activities.py -v
```

Expected: PASS, 4 tests.

- [ ] **Step 8.6: Commit**

```bash
cd ..
git add worker/
git commit -m "feat(worker): activities transformer + tests"
```

---

## Task 9: Transformers — daily, sleep, HRV, body composition

**Files:**
- Create: `worker/src/garmin_sync/transformers/daily.py`, `sleep.py`, `hrv.py`, `body.py` and their tests in `worker/tests/test_transformers/`

Each transformer follows the same pattern as activities. For brevity, this task implements all four together since they're tightly coupled.

- [ ] **Step 9.1: Write daily metrics test**

`worker/tests/test_transformers/test_daily.py`:

```python
from __future__ import annotations

from garmin_sync.transformers.daily import transform_daily


def test_transform_daily_full_payload() -> None:
    raw = {
        "calendarDate": "2026-05-15",
        "restingHeartRate": 52,
        "bodyBatteryMostRecentValue": 78,
        "bodyBatteryLowestValue": 23,
        "averageStressLevel": 35,
        "totalSteps": 12500,
        "activeKilocalories": 850,
        "totalKilocalories": 2400,
    }
    row = transform_daily(user_id="u1", raw=raw)
    assert row["date"] == "2026-05-15"
    assert row["resting_hr"] == 52
    assert row["body_battery_high"] == 78
    assert row["body_battery_low"] == 23
    assert row["stress_avg"] == 35
    assert row["steps"] == 12500


def test_transform_daily_missing_fields() -> None:
    raw = {"calendarDate": "2026-05-15"}
    row = transform_daily(user_id="u1", raw=raw)
    assert row["date"] == "2026-05-15"
    assert row["resting_hr"] is None
    assert row["steps"] is None
```

- [ ] **Step 9.2: Implement `worker/src/garmin_sync/transformers/daily.py`**

```python
"""Transform a Garmin daily stats payload into a `daily_metrics` row."""

from __future__ import annotations

from typing import Any


def transform_daily(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "date": raw["calendarDate"],
        "resting_hr": _to_int(raw.get("restingHeartRate")),
        "body_battery_low": _to_int(raw.get("bodyBatteryLowestValue")),
        "body_battery_high": _to_int(raw.get("bodyBatteryMostRecentValue")),
        "stress_avg": _to_int(raw.get("averageStressLevel")),
        "steps": _to_int(raw.get("totalSteps")),
        "active_calories": _to_int(raw.get("activeKilocalories")),
        "total_calories": _to_int(raw.get("totalKilocalories")),
        "readiness_score": None,  # computed later (E4)
        "raw": raw,
    }


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 9.3: Write sleep test**

`worker/tests/test_transformers/test_sleep.py`:

```python
from __future__ import annotations

from garmin_sync.transformers.sleep import transform_sleep


def test_transform_sleep() -> None:
    raw = {
        "dailySleepDTO": {
            "calendarDate": "2026-05-15",
            "sleepTimeSeconds": 28800,
            "deepSleepSeconds": 7200,
            "lightSleepSeconds": 14400,
            "remSleepSeconds": 5400,
            "awakeSleepSeconds": 1800,
            "sleepStartTimestampGMT": 1715900400000,  # ms
            "sleepEndTimestampGMT": 1715929200000,
        },
        "sleepScores": {"overall": {"value": 82}},
    }
    row = transform_sleep(user_id="u1", raw=raw)
    assert row["date"] == "2026-05-15"
    assert row["sleep_duration_s"] == 28800
    assert row["sleep_score"] == 82
    assert row["deep_sleep_s"] == 7200
```

- [ ] **Step 9.4: Implement `worker/src/garmin_sync/transformers/sleep.py`**

```python
"""Transform a Garmin sleep payload into a `sleep` row."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def transform_sleep(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    dto = raw.get("dailySleepDTO") or {}
    scores = raw.get("sleepScores") or {}
    return {
        "user_id": user_id,
        "date": dto.get("calendarDate"),
        "sleep_duration_s": dto.get("sleepTimeSeconds"),
        "sleep_score": (scores.get("overall") or {}).get("value"),
        "deep_sleep_s": dto.get("deepSleepSeconds"),
        "light_sleep_s": dto.get("lightSleepSeconds"),
        "rem_sleep_s": dto.get("remSleepSeconds"),
        "awake_s": dto.get("awakeSleepSeconds"),
        "bedtime": _ms_to_iso(dto.get("sleepStartTimestampGMT")),
        "wake_time": _ms_to_iso(dto.get("sleepEndTimestampGMT")),
        "raw": raw,
    }
```

- [ ] **Step 9.5: Write HRV test**

`worker/tests/test_transformers/test_hrv.py`:

```python
from __future__ import annotations

from garmin_sync.transformers.hrv import transform_hrv


def test_transform_hrv_full() -> None:
    raw = {
        "calendarDate": "2026-05-15",
        "lastNightAvg": 54.3,
        "status": "BALANCED",
        "weeklyAvg": 52.1,
    }
    row = transform_hrv(user_id="u1", raw=raw)
    assert row["date"] == "2026-05-15"
    assert row["hrv_rmssd"] == 54.3
    assert row["hrv_status"] == "balanced"
    assert row["hrv_weekly_avg"] == 52.1


def test_transform_hrv_no_data() -> None:
    raw = {"calendarDate": "2026-05-15"}
    row = transform_hrv(user_id="u1", raw=raw)
    assert row["hrv_rmssd"] is None
    assert row["hrv_status"] is None
```

- [ ] **Step 9.6: Implement `worker/src/garmin_sync/transformers/hrv.py`**

```python
"""Transform a Garmin HRV payload into an `hrv` row."""

from __future__ import annotations

from typing import Any

_ALLOWED_STATUSES = {"balanced", "unbalanced", "low", "poor", "no_status"}


def transform_hrv(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    status_raw = raw.get("status")
    status = (status_raw or "").lower().replace(" ", "_") if status_raw else None
    return {
        "user_id": user_id,
        "date": raw.get("calendarDate"),
        "hrv_rmssd": raw.get("lastNightAvg"),
        "hrv_status": status if status in _ALLOWED_STATUSES else None,
        "hrv_weekly_avg": raw.get("weeklyAvg"),
        "raw": raw,
    }
```

- [ ] **Step 9.7: Write body composition test**

`worker/tests/test_transformers/test_body.py`:

```python
from __future__ import annotations

from garmin_sync.transformers.body import transform_body


def test_transform_body_full() -> None:
    raw = {
        "calendarDate": "2026-05-15",
        "weight": 72500,  # grams in Garmin payload
        "bodyFat": 14.2,
        "muscleMass": 35200,
        "boneMass": 3100,
        "bodyWater": 60.5,
        "visceralFat": 8.0,
        "bmi": 22.4,
    }
    row = transform_body(user_id="u1", raw=raw)
    assert row["weight_kg"] == 72.5
    assert row["body_fat_pct"] == 14.2
    assert row["muscle_mass_kg"] == 35.2
    assert row["bmi"] == 22.4
```

- [ ] **Step 9.8: Implement `worker/src/garmin_sync/transformers/body.py`**

```python
"""Transform a Garmin body composition payload into a `body_composition` row."""

from __future__ import annotations

from typing import Any


def _g_to_kg(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / 1000.0, 2)
    except (TypeError, ValueError):
        return None


def transform_body(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "date": raw.get("calendarDate"),
        "weight_kg": _g_to_kg(raw.get("weight")),
        "body_fat_pct": raw.get("bodyFat"),
        "muscle_mass_kg": _g_to_kg(raw.get("muscleMass")),
        "bone_mass_kg": _g_to_kg(raw.get("boneMass")),
        "body_water_pct": raw.get("bodyWater"),
        "visceral_fat": raw.get("visceralFat"),
        "bmi": raw.get("bmi"),
        "raw": raw,
    }
```

- [ ] **Step 9.9: Run all transformer tests**

```bash
cd worker && uv run pytest tests/test_transformers/ -v
```

Expected: PASS — at least 10 tests across daily, sleep, hrv, body, activities.

- [ ] **Step 9.10: Commit**

```bash
cd ..
git add worker/
git commit -m "feat(worker): daily/sleep/hrv/body transformers with unit tests"
```

---

## Task 10: Sync orchestration (per-user)

**Files:**
- Create: `worker/src/garmin_sync/sync.py`, `worker/tests/test_sync.py`

- [ ] **Step 10.1: Write the test**

`worker/tests/test_sync.py`:

```python
"""Tests for per-user sync orchestration with mocked Garmin + Supabase."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.sync import sync_user_for_date_range


@pytest.fixture
def fake_garmin_client() -> MagicMock:
    client = MagicMock()
    client.get_activities_by_date.return_value = [
        {
            "activityId": 1,
            "startTimeGMT": "2026-05-15 07:00:00",
            "activityType": {"typeKey": "running"},
            "duration": 1800.0,
            "distance": 5000.0,
        }
    ]
    client.get_stats.return_value = {
        "calendarDate": "2026-05-15",
        "restingHeartRate": 52,
        "totalSteps": 8000,
    }
    client.get_sleep_data.return_value = {
        "dailySleepDTO": {"calendarDate": "2026-05-15", "sleepTimeSeconds": 28800},
    }
    client.get_hrv_data.return_value = {"calendarDate": "2026-05-15", "lastNightAvg": 50.0}
    client.get_body_composition.return_value = [
        {"calendarDate": "2026-05-15", "weight": 70000}
    ]
    return client


@pytest.fixture
def fake_admin_client() -> MagicMock:
    return MagicMock()


def test_sync_user_inserts_each_table(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
        )

    # 5 tables touched
    tables_touched = {call.args[0] for call in fake_admin_client.table.call_args_list}
    assert tables_touched >= {"activities", "daily_metrics", "sleep", "hrv", "body_composition"}


def test_sync_user_continues_when_one_endpoint_fails(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    # hrv endpoint blows up
    fake_garmin_client.get_hrv_data.side_effect = RuntimeError("garmin 500")

    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        # Should not raise — partial sync is acceptable
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
        )

    tables_touched = {call.args[0] for call in fake_admin_client.table.call_args_list}
    assert "activities" in tables_touched
    assert "hrv" not in tables_touched
```

- [ ] **Step 10.2: Run test (expect fail)**

```bash
cd worker && uv run pytest tests/test_sync.py -v
```

Expected: FAIL.

- [ ] **Step 10.3: Implement `worker/src/garmin_sync/sync.py`**

```python
"""Per-user sync orchestration.

Calls each Garmin endpoint, transforms the payload, upserts into Supabase.
Designed to be resilient: a failure in one endpoint must not abort the others.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from garminconnect import Garmin

from garmin_sync.supabase_client import get_admin_client
from garmin_sync.transformers.activities import transform_activity
from garmin_sync.transformers.body import transform_body
from garmin_sync.transformers.daily import transform_daily
from garmin_sync.transformers.hrv import transform_hrv
from garmin_sync.transformers.sleep import transform_sleep

log = logging.getLogger(__name__)


def sync_user_for_date_range(
    *,
    user_id: str,
    client: Garmin,
    start: date,
    end: date,
) -> None:
    """Sync all categories for a single user across [start, end] (inclusive)."""
    db = get_admin_client()

    # Activities — one shot for the whole range
    try:
        activities = client.get_activities_by_date(start.isoformat(), end.isoformat())
        rows = [transform_activity(user_id=user_id, raw=a) for a in activities]
        if rows:
            db.table("activities").upsert(rows, on_conflict="user_id,garmin_activity_id").execute()
    except Exception:
        log.exception("activities sync failed for user=%s", user_id)

    # Per-day metrics — daily, sleep, hrv, body
    current = start
    while current <= end:
        iso = current.isoformat()
        _safe_upsert_daily(db, user_id, client, iso)
        _safe_upsert_sleep(db, user_id, client, iso)
        _safe_upsert_hrv(db, user_id, client, iso)
        _safe_upsert_body(db, user_id, client, iso)
        current += timedelta(days=1)


def _safe_upsert_daily(db: Any, user_id: str, client: Garmin, iso_date: str) -> None:
    try:
        raw = client.get_stats(iso_date)
        if raw and raw.get("calendarDate"):
            db.table("daily_metrics").upsert(
                transform_daily(user_id=user_id, raw=raw), on_conflict="user_id,date"
            ).execute()
    except Exception:
        log.exception("daily sync failed user=%s date=%s", user_id, iso_date)


def _safe_upsert_sleep(db: Any, user_id: str, client: Garmin, iso_date: str) -> None:
    try:
        raw = client.get_sleep_data(iso_date)
        if raw and (raw.get("dailySleepDTO") or {}).get("calendarDate"):
            db.table("sleep").upsert(
                transform_sleep(user_id=user_id, raw=raw), on_conflict="user_id,date"
            ).execute()
    except Exception:
        log.exception("sleep sync failed user=%s date=%s", user_id, iso_date)


def _safe_upsert_hrv(db: Any, user_id: str, client: Garmin, iso_date: str) -> None:
    try:
        raw = client.get_hrv_data(iso_date)
        if raw and raw.get("calendarDate"):
            db.table("hrv").upsert(
                transform_hrv(user_id=user_id, raw=raw), on_conflict="user_id,date"
            ).execute()
    except Exception:
        log.exception("hrv sync failed user=%s date=%s", user_id, iso_date)


def _safe_upsert_body(db: Any, user_id: str, client: Garmin, iso_date: str) -> None:
    try:
        items = client.get_body_composition(iso_date, iso_date)
        for raw in items or []:
            if raw.get("calendarDate"):
                db.table("body_composition").upsert(
                    transform_body(user_id=user_id, raw=raw), on_conflict="user_id,date"
                ).execute()
    except Exception:
        log.exception("body sync failed user=%s date=%s", user_id, iso_date)
```

- [ ] **Step 10.4: Run tests to pass**

```bash
cd worker && uv run pytest tests/test_sync.py -v
```

Expected: PASS, 2 tests.

- [ ] **Step 10.5: Commit**

```bash
cd ..
git add worker/
git commit -m "feat(worker): per-user sync orchestration with resilient error handling"
```

---

## Task 11: HTTP entry point (FastAPI app + cron)

**Files:**
- Create: `worker/src/garmin_sync/main.py`, `worker/src/garmin_sync/cron.py`, `worker/tests/test_main.py`

- [ ] **Step 11.1: Write API test**

`worker/tests/test_main.py`:

```python
"""Tests for FastAPI HTTP endpoints."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Iterator[TestClient]:
    from garmin_sync.main import app
    yield TestClient(app)


def test_health_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_sync_endpoint_requires_shared_token(client: TestClient) -> None:
    r = client.post("/sync/u1", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_sync_endpoint_with_valid_token(client: TestClient) -> None:
    with patch("garmin_sync.main.run_sync_for_user") as fake:
        fake.return_value = {"activities": 5}
        r = client.post(
            "/sync/u1",
            headers={"Authorization": "Bearer shared-token-test"},
        )
    assert r.status_code == 200
    assert r.json() == {"activities": 5}
    fake.assert_called_once_with("u1", initial=False)


def test_garmin_connect_endpoint_requires_jwt(client: TestClient) -> None:
    r = client.post("/garmin/connect", json={"email": "a@b.c", "password": "p"})
    assert r.status_code == 401
```

- [ ] **Step 11.2: Run test (expect fail)**

```bash
cd worker && uv run pytest tests/test_main.py -v
```

Expected: FAIL.

- [ ] **Step 11.3: Implement `worker/src/garmin_sync/main.py`**

```python
"""FastAPI HTTP entry point: health, manual sync, Garmin connect/MFA."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from garmin_sync.auth import AuthError, verify_shared_token, verify_supabase_jwt
from garmin_sync.config import get_settings
from garmin_sync.cron import run_sync_for_user

log = logging.getLogger(__name__)
app = FastAPI(title="garmin-sync", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": get_settings().env}


def _require_shared_token(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    if not verify_shared_token(token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


def _require_user_jwt(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        return verify_supabase_jwt(token)
    except AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e


@app.post("/sync/{user_id}")
def sync_user(
    user_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_shared_token(authorization)
    return run_sync_for_user(user_id, initial=False)


class GarminConnectRequest(BaseModel):
    email: str
    password: str


class GarminMFARequest(BaseModel):
    challenge_id: str
    code: str


@app.post("/garmin/connect")
def garmin_connect(
    body: GarminConnectRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Initiate Garmin login. Called by Next.js Server Action on behalf of user."""
    user_id = _require_user_jwt(authorization)
    from garmin_sync.connect import start_connect_flow
    return start_connect_flow(user_id=user_id, email=body.email, password=body.password)


@app.post("/garmin/mfa")
def garmin_mfa(
    body: GarminMFARequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _require_user_jwt(authorization)
    from garmin_sync.connect import resume_connect_flow
    return resume_connect_flow(user_id=user_id, challenge_id=body.challenge_id, code=body.code)
```

- [ ] **Step 11.4: Implement `worker/src/garmin_sync/cron.py`**

```python
"""Cron entry point — run sync for all users with valid Garmin credentials."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from garmin_sync.crypto import TokenCipher
from garmin_sync.garmin_client import GarminAuthError, login_with_tokens
from garmin_sync.supabase_client import get_admin_client
from garmin_sync.sync import sync_user_for_date_range

log = logging.getLogger(__name__)

INITIAL_BACKFILL_DAYS = 90


def run_sync_for_user(user_id: str, *, initial: bool = False) -> dict[str, Any]:
    """Sync a single user. Used by /sync endpoint and by run_daily_cron."""
    db = get_admin_client()
    creds_resp = (
        db.table("garmin_credentials")
        .select("oauth_tokens_encrypted, initial_sync_completed_at")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    creds = creds_resp.data
    if not creds or not creds.get("oauth_tokens_encrypted"):
        return {"status": "no_credentials"}

    cipher = TokenCipher()
    serialized = cipher.decrypt(bytes(creds["oauth_tokens_encrypted"]))
    try:
        client = login_with_tokens(serialized)
    except GarminAuthError:
        db.table("garmin_credentials").update(
            {"token_refresh_failed_at": datetime.now(UTC).isoformat()}
        ).eq("user_id", user_id).execute()
        return {"status": "auth_failed"}

    today = date.today()
    if initial or not creds.get("initial_sync_completed_at"):
        start = today - timedelta(days=INITIAL_BACKFILL_DAYS)
    else:
        start = today - timedelta(days=2)  # always re-sync last 2 days to catch corrections

    sync_user_for_date_range(user_id=user_id, client=client, start=start, end=today)

    db.table("garmin_credentials").update(
        {
            "last_sync_at": datetime.now(UTC).isoformat(),
            "last_sync_status": "ok",
            "initial_sync_completed_at": datetime.now(UTC).isoformat()
            if not creds.get("initial_sync_completed_at")
            else creds["initial_sync_completed_at"],
        }
    ).eq("user_id", user_id).execute()

    return {"status": "ok", "days_synced": (today - start).days + 1}


def run_daily_cron() -> dict[str, Any]:
    """Iterate all users with credentials and sync each."""
    db = get_admin_client()
    users = (
        db.table("garmin_credentials")
        .select("user_id")
        .is_("token_refresh_failed_at", "null")
        .execute()
    )

    results: dict[str, dict[str, Any]] = {}
    for row in users.data:
        uid = row["user_id"]
        try:
            results[uid] = run_sync_for_user(uid, initial=False)
        except Exception:
            log.exception("daily cron failed for user=%s", uid)
            results[uid] = {"status": "exception"}
    return {"total_users": len(users.data), "results": results}


if __name__ == "__main__":
    # Entry point for Fly.io scheduled machine: `python -m garmin_sync.cron`
    import json
    out = run_daily_cron()
    print(json.dumps(out, indent=2))
```

- [ ] **Step 11.5: Implement Garmin connect flow** (stubbed for now, full impl in Task 12)

`worker/src/garmin_sync/connect.py`:

```python
"""Garmin connect/MFA flow. Stores encrypted tokens on success.

MFA challenges are kept in an in-memory dict keyed by a synthetic challenge_id.
This is acceptable for single-instance worker; for multi-instance we'd need
Redis. The flow expires unused challenges after 5 minutes.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from garmin_sync.crypto import TokenCipher
from garmin_sync.garmin_client import (
    GarminAuthError,
    GarminMFARequired,
    login_with_credentials,
    submit_mfa_code,
)
from garmin_sync.supabase_client import get_admin_client

_MFA_EXPIRY_S = 300
_pending_mfa: dict[str, tuple[float, str, Any]] = {}  # challenge_id → (created_at, user_id, challenge)


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, (ts, _u, _c) in _pending_mfa.items() if now - ts > _MFA_EXPIRY_S]
    for k in expired:
        _pending_mfa.pop(k, None)


def start_connect_flow(*, user_id: str, email: str, password: str) -> dict[str, Any]:
    _purge_expired()
    try:
        tokens_json = login_with_credentials(email, password)
    except GarminMFARequired as e:
        challenge_id = uuid.uuid4().hex
        _pending_mfa[challenge_id] = (time.time(), user_id, e.challenge)
        return {"status": "mfa_required", "challenge_id": challenge_id}
    except GarminAuthError:
        return {"status": "invalid_credentials"}

    _persist_tokens(user_id=user_id, tokens_json=tokens_json)
    return {"status": "connected"}


def resume_connect_flow(*, user_id: str, challenge_id: str, code: str) -> dict[str, Any]:
    _purge_expired()
    entry = _pending_mfa.pop(challenge_id, None)
    if not entry:
        return {"status": "challenge_expired"}

    _ts, owner, challenge = entry
    if owner != user_id:
        return {"status": "challenge_user_mismatch"}

    try:
        tokens_json = submit_mfa_code(challenge, code)
    except GarminAuthError:
        return {"status": "invalid_code"}

    _persist_tokens(user_id=user_id, tokens_json=tokens_json)
    return {"status": "connected"}


def _persist_tokens(*, user_id: str, tokens_json: str) -> None:
    cipher = TokenCipher()
    encrypted = cipher.encrypt(tokens_json)
    db = get_admin_client()
    db.table("garmin_credentials").upsert(
        {
            "user_id": user_id,
            "oauth_tokens_encrypted": encrypted.decode("ascii"),
            "token_refresh_failed_at": None,
            "last_sync_status": None,
            "updated_at": datetime.now(UTC).isoformat(),
        },
        on_conflict="user_id",
    ).execute()
```

- [ ] **Step 11.6: Run all worker tests**

```bash
cd worker && uv run pytest -v
```

Expected: ALL tests pass (config + crypto + auth + transformers + sync + main).

- [ ] **Step 11.7: Lint + typecheck**

```bash
cd worker
uv run ruff check .
uv run ruff format .
uv run mypy src/
```

Fix any reported issues. Expected after fix: all clean.

- [ ] **Step 11.8: Commit**

```bash
cd ..
git add worker/
git commit -m "feat(worker): FastAPI entry + cron entry + Garmin connect/MFA flow"
```

---

## Task 12: Dockerfile + Fly.io configuration

**Files:**
- Create: `worker/Dockerfile`, `worker/fly.toml`

- [ ] **Step 12.1: Create `worker/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=3.12

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable || uv sync --no-dev --no-editable

FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=builder /app /app

EXPOSE 8080

CMD ["uvicorn", "garmin_sync.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 12.2: Create `worker/fly.toml`**

```toml
app = "garmin-sync"
primary_region = "cdg"  # Paris — close to eu-west-3 Supabase

[build]

[env]
  ENV = "prod"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0  # free tier — scale to zero
  processes = ["app"]

[[vm]]
  size = "shared-cpu-1x"
  memory = "256mb"

[processes]
  app = "uvicorn garmin_sync.main:app --host 0.0.0.0 --port 8080"
```

- [ ] **Step 12.3: Lock dependencies for reproducible builds**

```bash
cd worker
uv lock
```

This creates `worker/uv.lock`. Commit it.

- [ ] **Step 12.4: Local Docker build sanity check**

```bash
cd worker
docker build -t garmin-sync-test .
docker run --rm -p 8080:8080 \
  -e SUPABASE_URL=https://example.supabase.co \
  -e SUPABASE_SERVICE_ROLE_KEY=test \
  -e SUPABASE_JWT_SECRET=test \
  -e FERNET_KEY=Mk7-aBcDEfGhIjKlMnOpQrStUvWxYz0123456789abc= \
  -e WORKER_SHARED_TOKEN=test \
  garmin-sync-test &
sleep 5
curl -s http://localhost:8080/health
docker kill $(docker ps -lq)
```

Expected: `{"status":"ok","env":"dev"}` (env defaults to dev).

- [ ] **Step 12.5: Commit**

```bash
cd ..
git add worker/Dockerfile worker/fly.toml worker/uv.lock
git commit -m "feat(worker): Dockerfile + fly.toml + locked deps"
```

---

## Task 13: Deploy to Fly.io + secrets

This task involves manual operator actions on Fly.io.

- [ ] **Step 13.1: Create Fly.io app**

```bash
cd worker
flyctl apps create garmin-sync --org personal
```

If the name is taken, choose `garmin-sync-<your-handle>` and update `fly.toml`'s `app` field accordingly.

- [ ] **Step 13.2: Generate a Fernet key**

```bash
cd worker
uv run python -c "from garmin_sync.crypto import generate_fernet_key; print(generate_fernet_key())"
```

Copy the output — this is the production `FERNET_KEY`. **Store it in your password manager** because losing it means all encrypted tokens become unrecoverable.

- [ ] **Step 13.3: Generate a shared token**

```bash
openssl rand -base64 32
```

Copy the output — this is the `WORKER_SHARED_TOKEN`. The Fly.io scheduled machine (cron) and any operator scripts use it.

- [ ] **Step 13.4: Set Fly.io secrets**

Replace placeholders with real values (from your Supabase Dashboard → Project Settings → API):

```bash
flyctl secrets set \
  SUPABASE_URL="https://peiyrqplymdlmlpsbqzu.supabase.co" \
  SUPABASE_SERVICE_ROLE_KEY="<your-service-role-key>" \
  SUPABASE_JWT_SECRET="<your-jwt-secret>" \
  FERNET_KEY="<the-fernet-key-from-step-13.2>" \
  WORKER_SHARED_TOKEN="<the-shared-token-from-step-13.3>" \
  ENV="prod" \
  --app garmin-sync
```

- [ ] **Step 13.5: First deploy**

```bash
flyctl deploy --app garmin-sync
```

Watch the build output. Should succeed in ~3-5 minutes.

- [ ] **Step 13.6: Verify health**

```bash
flyctl status --app garmin-sync
curl -s https://garmin-sync.fly.dev/health
```

Expected: `{"status":"ok","env":"prod"}`.

- [ ] **Step 13.7: Set up scheduled machine for daily cron**

```bash
flyctl machine run . \
  --schedule daily \
  --command "python -m garmin_sync.cron" \
  --region cdg \
  --vm-memory 256 \
  --app garmin-sync
```

Note: this creates a machine that runs once a day at the time you ran the command. To run at 05:00 UTC specifically, see https://fly.io/docs/reference/scheduled-machines/.

Verify via `flyctl machine list --app garmin-sync`. There should now be two machines: the always-on (scale to zero) HTTP one and the scheduled cron one.

- [ ] **Step 13.8: Commit deployment notes**

Update `worker/README.md`:

```markdown
# garmin-sync worker

Python worker for the Garmin Training Coach project.

## Local dev

```bash
cd worker
uv sync --all-groups
cp .env.example .env  # see below
uv run uvicorn garmin_sync.main:app --reload --port 8080
```

`.env.example` should contain (do NOT commit real values):

```
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_SECRET=...
FERNET_KEY=...  # generate via `uv run python -c "from garmin_sync.crypto import generate_fernet_key; print(generate_fernet_key())"`
WORKER_SHARED_TOKEN=...
ENV=dev
```

## Tests

```bash
uv run pytest -v
uv run ruff check . && uv run ruff format --check . && uv run mypy src/
```

## Deploy

```bash
flyctl deploy --app garmin-sync
```

Secrets are managed via `flyctl secrets set`. Never commit them.

## Daily cron

Runs `python -m garmin_sync.cron` once a day on a scheduled machine. See `flyctl machine list --app garmin-sync`.
```

Also create `worker/.env.example`:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret
FERNET_KEY=generate-via-crypto-module
WORKER_SHARED_TOKEN=generate-via-openssl-rand-base64-32
ENV=dev
```

Commit:

```bash
git add worker/README.md worker/.env.example
git commit -m "docs(worker): README + .env.example"
```

---

## Task 14: Frontend — Garmin connect UI

**Files:**
- Create: `lib/worker.ts`, `app/actions/garmin-auth.ts`, `app/(app)/profile/garmin/page.tsx`, `components/garmin/connect-form.tsx`, `components/garmin/mfa-form.tsx`
- Modify: `lib/env.ts` (add WORKER_URL + WORKER_SHARED_TOKEN as server-side env vars)

- [ ] **Step 14.1: Extend `lib/env.ts` with worker config**

Replace `lib/env.ts` with:

```ts
import { z } from 'zod'

// Public env vars (exposed to the browser bundle)
const publicSchema = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(1),
})

// Server-only env vars (NEVER exposed to the browser)
const serverSchema = z.object({
  WORKER_URL: z.url().default('http://localhost:8080'),
})

const publicParsed = publicSchema.safeParse({
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
})

if (!publicParsed.success) {
  const issues = publicParsed.error.issues
    .map((i) => `- ${i.path.join('.')}: ${i.message}`)
    .join('\n')
  throw new Error(`Invalid public environment variables:\n${issues}`)
}

export const env = publicParsed.data

// Lazy server-only access — throws if called from a client bundle context where
// process.env.WORKER_URL is undefined.
export function getServerEnv() {
  const parsed = serverSchema.safeParse({
    WORKER_URL: process.env.WORKER_URL,
  })
  if (!parsed.success) {
    throw new Error('Invalid server env: ' + JSON.stringify(parsed.error.issues))
  }
  return parsed.data
}
```

The existing `tests/unit/env.test.ts` should keep passing because (1) the `env` export still throws on missing public vars at module init (publicParsed.safeParse), and (2) the test only exercises public vars. No changes needed to that test file. Run `pnpm test` after this step to confirm.

- [ ] **Step 14.2: Create `lib/worker.ts` — HTTP client**

```ts
import { getServerEnv } from './env'

export type ConnectResult =
  | { status: 'connected' }
  | { status: 'mfa_required'; challenge_id: string }
  | { status: 'invalid_credentials' }

export type MfaResult =
  | { status: 'connected' }
  | { status: 'invalid_code' }
  | { status: 'challenge_expired' }

export async function workerPost<T>(
  path: string,
  body: unknown,
  userJwt: string
): Promise<T> {
  const { WORKER_URL } = getServerEnv()
  const res = await fetch(`${WORKER_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${userJwt}`,
    },
    body: JSON.stringify(body),
    cache: 'no-store',
  })
  if (!res.ok) {
    throw new Error(`Worker error ${res.status}: ${await res.text()}`)
  }
  return res.json() as Promise<T>
}
```

- [ ] **Step 14.3: Create Server Actions `app/actions/garmin-auth.ts`**

```ts
'use server'

import { createClient } from '@/lib/supabase/server'
import { workerPost, type ConnectResult, type MfaResult } from '@/lib/worker'

async function getUserJwt(): Promise<string> {
  const supabase = await createClient()
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) {
    throw new Error('Not authenticated')
  }
  return session.access_token
}

export async function connectGarmin(
  email: string,
  password: string
): Promise<ConnectResult> {
  const jwt = await getUserJwt()
  return workerPost<ConnectResult>('/garmin/connect', { email, password }, jwt)
}

export async function submitGarminMfa(
  challenge_id: string,
  code: string
): Promise<MfaResult> {
  const jwt = await getUserJwt()
  return workerPost<MfaResult>('/garmin/mfa', { challenge_id, code }, jwt)
}
```

- [ ] **Step 14.4: Create `components/garmin/connect-form.tsx`**

```tsx
'use client'

import { useState } from 'react'
import { connectGarmin } from '@/app/actions/garmin-auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'

type Props = {
  onMfaRequired: (challengeId: string) => void
  onConnected: () => void
}

export function ConnectForm({ onMfaRequired, onConnected }: Readonly<Props>) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    try {
      const result = await connectGarmin(email, password)
      if (result.status === 'connected') {
        toast.success('Compte Garmin connecté !')
        onConnected()
      } else if (result.status === 'mfa_required') {
        onMfaRequired(result.challenge_id)
      } else {
        toast.error('Identifiants Garmin invalides')
      }
    } catch (err) {
      toast.error(`Erreur: ${(err as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="w-full max-w-sm space-y-4">
      <div className="space-y-2">
        <Label htmlFor="garmin-email">Email Garmin Connect</Label>
        <Input
          id="garmin-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          disabled={loading}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="garmin-password">Mot de passe Garmin</Label>
        <Input
          id="garmin-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          disabled={loading}
        />
      </div>
      <Button type="submit" disabled={loading || !email || !password} className="w-full">
        {loading ? 'Connexion...' : 'Connecter Garmin'}
      </Button>
    </form>
  )
}
```

- [ ] **Step 14.5: Create `components/garmin/mfa-form.tsx`**

```tsx
'use client'

import { useState } from 'react'
import { submitGarminMfa } from '@/app/actions/garmin-auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'

type Props = {
  challengeId: string
  onConnected: () => void
  onCancel: () => void
}

export function MfaForm({ challengeId, onConnected, onCancel }: Readonly<Props>) {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    try {
      const result = await submitGarminMfa(challengeId, code)
      if (result.status === 'connected') {
        toast.success('Compte Garmin connecté !')
        onConnected()
      } else if (result.status === 'invalid_code') {
        toast.error('Code MFA invalide')
      } else {
        toast.error('Challenge expiré, réessaye depuis le début')
        onCancel()
      }
    } catch (err) {
      toast.error(`Erreur: ${(err as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="w-full max-w-sm space-y-4">
      <div className="space-y-2">
        <Label htmlFor="mfa-code">Code à 6 chiffres reçu par email/SMS</Label>
        <Input
          id="mfa-code"
          inputMode="numeric"
          maxLength={8}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          required
          disabled={loading}
        />
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={loading || code.length < 4} className="flex-1">
          {loading ? 'Vérification...' : 'Valider'}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel} disabled={loading}>
          Annuler
        </Button>
      </div>
    </form>
  )
}
```

- [ ] **Step 14.6: Create `app/(app)/profile/garmin/page.tsx`**

```tsx
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ConnectForm } from '@/components/garmin/connect-form'
import { MfaForm } from '@/components/garmin/mfa-form'
import { Toaster } from '@/components/ui/sonner'

type Stage = { kind: 'form' } | { kind: 'mfa'; challengeId: string }

export default function GarminConnectPage() {
  const router = useRouter()
  const [stage, setStage] = useState<Stage>({ kind: 'form' })

  function handleConnected() {
    router.push('/profile?garmin=connected')
    router.refresh()
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Connecter Garmin</h1>
        <p className="text-sm text-muted-foreground">
          Tes identifiants Garmin sont envoyés au serveur via HTTPS, utilisés une seule fois
          pour obtenir un token OAuth, puis effacés. Seul le token est conservé, chiffré.
        </p>
      </header>
      <section className="border rounded-lg p-6">
        {stage.kind === 'form' ? (
          <ConnectForm
            onMfaRequired={(challengeId) => setStage({ kind: 'mfa', challengeId })}
            onConnected={handleConnected}
          />
        ) : (
          <MfaForm
            challengeId={stage.challengeId}
            onConnected={handleConnected}
            onCancel={() => setStage({ kind: 'form' })}
          />
        )}
      </section>
      <Toaster />
    </div>
  )
}
```

- [ ] **Step 14.7: Add link from `/profile` to `/profile/garmin`**

Modify `app/(app)/profile/page.tsx` — add after the existing section:

```tsx
import Link from 'next/link'
import { Button } from '@/components/ui/button'
// ... existing imports

// In the JSX, append after the existing section:
      <section className="border rounded-lg p-6 space-y-3">
        <h2 className="text-lg font-semibold">Garmin Connect</h2>
        <p className="text-sm text-muted-foreground">
          Connecte ton compte Garmin pour synchroniser tes activités et métriques.
        </p>
        <Button asChild variant="outline">
          <Link href="/profile/garmin">Connecter Garmin</Link>
        </Button>
      </section>
```

- [ ] **Step 14.8: Add Vercel env var**

Set `WORKER_URL` on Vercel (Dashboard → Project Settings → Environment Variables) to the Fly.io URL (e.g. `https://garmin-sync.fly.dev`). Apply to Production + Preview + Development.

- [ ] **Step 14.9: Build + lint**

```bash
pnpm lint && pnpm typecheck && pnpm build
```

Expected: all green.

- [ ] **Step 14.10: Commit**

```bash
git add -A
git commit -m "feat(app): Garmin connect UI with MFA support + Server Actions"
```

---

## Task 15: GitHub Actions CI for worker

**Files:**
- Create: `.github/workflows/worker-ci.yml`

- [ ] **Step 15.1: Create the workflow**

```yaml
name: Worker CI

on:
  pull_request:
    branches: [main, master]
    paths: ['worker/**']
  push:
    branches: [main, master]
    paths: ['worker/**']

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    name: Test + lint + typecheck
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: worker
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with: { version: "0.5.x" }
      - name: Install Python
        run: uv python install 3.12
      - name: Install deps
        run: uv sync --all-groups --frozen
      - name: Ruff lint
        run: uv run ruff check .
      - name: Ruff format check
        run: uv run ruff format --check .
      - name: Mypy
        run: uv run mypy src/
      - name: Pytest
        run: uv run pytest -v --cov=garmin_sync --cov-report=lcov:coverage/lcov.info
      - name: Upload coverage to SonarQube via main CI
        uses: actions/upload-artifact@v4
        with:
          name: worker-coverage-lcov
          path: worker/coverage/lcov.info
          retention-days: 1

  docker:
    name: Docker build
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: worker
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Build image
        run: docker build -t garmin-sync:ci .
```

- [ ] **Step 15.2: Update `sonar-project.properties` to include worker**

Add to `sonar-project.properties`:

```
sonar.sources=app,lib,components,supabase/functions,worker/src
sonar.tests=tests,worker/tests
sonar.python.coverage.reportPaths=worker/coverage/lcov.info
```

- [ ] **Step 15.3: Commit**

```bash
git add .github/workflows/worker-ci.yml sonar-project.properties
git commit -m "ci: worker pipeline (lint+typecheck+test+coverage+docker)"
```

---

## Task 16: E2E sanity test — connect a real Garmin account

This task involves real user actions.

- [ ] **Step 16.1: Local end-to-end smoke test**

Make sure `.env.local` (Next.js) has `WORKER_URL=http://localhost:8080`. Start both services:

```bash
# Terminal 1
cd worker
uv run uvicorn garmin_sync.main:app --reload --port 8080

# Terminal 2 (project root)
pnpm dev
```

Open the app at http://localhost:3000, sign in via magic link, then navigate to `/profile/garmin`. Enter your real Garmin credentials. If MFA is enabled on your Garmin account, enter the code Garmin emails you.

Expected:
- After "Compte Garmin connecté !" toast, redirect to `/profile?garmin=connected`.
- In Supabase, `garmin_credentials` for your user_id has `oauth_tokens_encrypted` populated (non-null).

- [ ] **Step 16.2: Trigger a manual sync**

```bash
curl -X POST https://garmin-sync.fly.dev/sync/<your-user-uuid> \
  -H "Authorization: Bearer <WORKER_SHARED_TOKEN>"
```

Expected: `{"status":"ok","days_synced":91}` (90-day backfill).

Verify in Supabase:
- `activities` has rows for your Garmin activities of the last 90 days
- `daily_metrics`, `sleep`, `hrv`, `body_composition` have rows where data is available

- [ ] **Step 16.3: Verify RLS protects other users' data**

As the signed-in user in the browser, run via the Supabase JS client (in console):

```js
const { data, error } = await window.supabase.from('activities').select('*').limit(5)
console.log({ rows: data?.length, error })
```

Expected: only YOUR activities returned. If you try to query another user's id, RLS denies.

---

## Definition of Done (E2)

- [ ] All worker tests pass: `cd worker && uv run pytest -v` — at least 25 tests across config, crypto, auth, transformers, sync, main.
- [ ] Worker lint clean: `uv run ruff check .` + `uv run ruff format --check .` + `uv run mypy src/`.
- [ ] All 6 new migrations applied via Supabase MCP, advisors clean (`mcp__supabase__get_advisors security` returns 0 lints).
- [ ] Worker deployed on Fly.io, `https://garmin-sync.fly.dev/health` returns 200.
- [ ] Scheduled cron machine exists (`flyctl machine list --app garmin-sync`).
- [ ] Frontend `/profile/garmin` page works: connect with email/pwd, handle MFA, redirect on success.
- [ ] Vercel env var `WORKER_URL` set.
- [ ] One real end-to-end test: connect a real Garmin account, run manual sync, see ≥1 row in `activities`.
- [ ] CI passes for both the Next.js app and the worker.
- [ ] No Garmin tokens visible in plain text anywhere in DB.
- [ ] Working tree clean, all commits pushed.

---

## Notes for the engineer

- **The MFA in-memory store** (`worker/src/garmin_sync/connect.py`) is single-instance. When we scale to multi-machine on Fly.io later, swap for Redis or persist the challenge token in Supabase with a short TTL. For MVP with 5-10 users, single instance is plenty.
- **`auto_stop_machines = 'stop'` + `min_machines_running = 0`** means the worker scales to zero when idle. Cold start is ~2-3 seconds. Acceptable for daily cron + occasional manual sync. If you want zero cold-start, set `min_machines_running = 1` — costs ~$3/mo on Fly free trial overage.
- **`get_body_composition` is paged**: we pass start=end same date and process all returned items. Some users won't have body comp data at all — that's fine, the table allows 0 rows.
- **Activities pagination**: `get_activities_by_date(start, end)` returns ALL activities in the range in one call (Garmin sets no page limit for date ranges). For users with 100+ activities in 90 days, the response stays well under 1 MB.
- **Sentry**: setting `SENTRY_DSN` in Fly.io secrets enables Sentry automatically (via `sentry-sdk[fastapi]` auto-instrumentation in `main.py` — TODO: wire up Sentry init explicitly if SENTRY_DSN is set, possibly in a Task 17 follow-up).
- **Cron scheduling**: Fly.io's `--schedule daily` runs daily at the time of creation. To pin to 05:00 UTC explicitly, schedule it deliberately at 05:00 UTC. If you need cron-syntax flexibility, switch to GitHub Actions cron calling `/sync/all` instead.
- **Token refresh failure email**: not implemented in this EPIC. When `token_refresh_failed_at` is set, future EPICs can hook a Supabase Edge Function that emails the user. For MVP, you'll see the flag in the DB and can prompt the user manually.
- **TSS calculation**: left as null in `activities`. Computed in E4 from HR/power/duration via algorithm.
