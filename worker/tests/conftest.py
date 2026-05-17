"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide deterministic env vars so config.Settings() always loads."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key-test")
    monkeypatch.setenv("FERNET_KEY", "Mk7-aBcDEfGhIjKlMnOpQrStUvWxYz0123456789abc=")
    monkeypatch.setenv("WORKER_SHARED_TOKEN", "shared-token-test")
    monkeypatch.setenv("ENV", "test")
    # Disable Sentry in tests
    monkeypatch.delenv("SENTRY_DSN", raising=False)
