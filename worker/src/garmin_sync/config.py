"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All secrets come from env vars (never committed)."""

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    supabase_url: HttpUrl
    supabase_service_role_key: SecretStr
    fernet_key: SecretStr
    worker_shared_token: SecretStr
    env: Literal["dev", "test", "staging", "prod"] = Field(default="dev")
    sentry_dsn: SecretStr | None = Field(default=None)
    openai_api_key: SecretStr = Field(default=SecretStr(""))
    openai_model: str = Field(default="gpt-4o-mini")
    openai_timeout_s: int = Field(default=30)
    gps_backfill_batch: int = Field(default=8)

    @field_validator("fernet_key")
    @classmethod
    def _validate_fernet_key(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        # Fernet keys are 44-char url-safe base64-encoded 32-byte values
        if len(raw) != 44 or not raw.endswith("="):
            msg = f"fernet_key must be a 44-char url-safe base64 string, got len={len(raw)}"
            raise ValueError(msg)
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Convenience accessor — Pydantic re-reads env on construction."""
    return Settings()
