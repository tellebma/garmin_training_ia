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
