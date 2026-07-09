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
    assert s.openai_api_key.get_secret_value() == "sk-test"
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


def test_gps_backfill_batch_defaults_to_8() -> None:
    from garmin_sync.config import Settings

    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="x",
        fernet_key="a" * 43 + "=",
        worker_shared_token="t",
    )
    assert settings.gps_backfill_batch == 8


def test_fernet_key_chain_falls_back_to_single_key_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FERNET_KEYS absent → chain is exactly [fernet_key] (pre-rotation behaviour)."""
    monkeypatch.delenv("FERNET_KEYS", raising=False)
    s = Settings()
    assert s.fernet_keys is None
    assert s.fernet_key_chain() == [s.fernet_key.get_secret_value()]


def test_fernet_key_chain_uses_first_key_as_active(monkeypatch: pytest.MonkeyPatch) -> None:
    key_a = "a" * 43 + "="
    key_b = "b" * 43 + "="
    monkeypatch.setenv("FERNET_KEYS", f"{key_a},{key_b}")
    s = Settings()
    assert s.fernet_key_chain() == [key_a, key_b]


def test_fernet_key_chain_strips_whitespace_around_commas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_a = "a" * 43 + "="
    key_b = "b" * 43 + "="
    monkeypatch.setenv("FERNET_KEYS", f" {key_a} , {key_b} ")
    s = Settings()
    assert s.fernet_key_chain() == [key_a, key_b]


def test_settings_rejects_invalid_key_in_fernet_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FERNET_KEYS", "too-short,also-too-short")
    with pytest.raises(ValueError, match="fernet key"):
        Settings()


def test_settings_rejects_empty_fernet_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FERNET_KEYS", "  ,  ")
    with pytest.raises(ValueError, match="fernet_keys"):
        Settings()


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
