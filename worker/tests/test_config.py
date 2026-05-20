"""Tests for config.Settings — env var loading and validation."""

from __future__ import annotations

import pytest

from garmin_sync.config import Settings, get_settings


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


def test_settings_loads_openai_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_TIMEOUT_S", "30")
    get_settings.cache_clear()
    s = get_settings()
    assert s.openai_api_key == "sk-test"
    assert s.openai_model == "gpt-4o-mini"
    assert s.openai_timeout_s == 30


def test_settings_openai_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_TIMEOUT_S", raising=False)
    get_settings.cache_clear()
    s = get_settings()
    assert s.openai_model == "gpt-4o-mini"
    assert s.openai_timeout_s == 30
