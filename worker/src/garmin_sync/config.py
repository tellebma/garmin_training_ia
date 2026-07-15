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
    fernet_keys: SecretStr | None = Field(default=None)
    worker_shared_token: SecretStr
    env: Literal["dev", "test", "staging", "prod"] = Field(default="dev")
    sentry_dsn: SecretStr | None = Field(default=None)
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    discord_webhook_url: SecretStr | None = Field(default=None)
    openai_api_key: SecretStr = Field(default=SecretStr(""))
    openai_admin_api_key: SecretStr = Field(default=SecretStr(""))
    openai_model: str = Field(default="gpt-4o-mini")
    openai_timeout_s: int = Field(default=30)
    openai_max_attempts: int = Field(default=3, ge=1)
    gps_backfill_batch: int = Field(default=8)
    # Strava is an optional integration. Empty defaults keep the worker booting
    # (and Garmin sync running) on deployments where Strava isn't configured.
    strava_client_id: str = Field(default="")
    strava_client_secret: SecretStr = Field(default=SecretStr(""))
    strava_webhook_verify_token: SecretStr = Field(default=SecretStr(""))

    @staticmethod
    def _check_fernet_key_shape(raw: str) -> None:
        # Fernet keys are 44-char url-safe base64-encoded 32-byte values
        if len(raw) != 44 or not raw.endswith("="):
            msg = f"fernet key must be a 44-char url-safe base64 string, got len={len(raw)}"
            raise ValueError(msg)

    @field_validator("fernet_key")
    @classmethod
    def _validate_fernet_key(cls, v: SecretStr) -> SecretStr:
        cls._check_fernet_key_shape(v.get_secret_value())
        return v

    @field_validator("fernet_keys")
    @classmethod
    def _validate_fernet_keys(cls, v: SecretStr | None) -> SecretStr | None:
        if v is None:
            return v
        raw = v.get_secret_value()
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        if not keys:
            msg = "fernet_keys must contain at least one non-empty key"
            raise ValueError(msg)
        for key in keys:
            cls._check_fernet_key_shape(key)
        return v

    @property
    def strava_configured(self) -> bool:
        """True when all Strava OAuth/webhook secrets are present."""
        return bool(
            self.strava_client_id
            and self.strava_client_secret.get_secret_value()
            and self.strava_webhook_verify_token.get_secret_value()
        )

    def fernet_key_chain(self) -> list[str]:
        """Ordered list of Fernet keys: active key first, then legacy keys.

        Falls back to the single ``fernet_key`` when ``FERNET_KEYS`` is unset,
        preserving full backward compatibility with existing deployments. The
        first key in the chain is always the active encryption key; the rest
        are only used to decrypt ciphertext written before a rotation.
        """
        if self.fernet_keys is None:
            return [self.fernet_key.get_secret_value()]
        raw = self.fernet_keys.get_secret_value()
        return [k.strip() for k in raw.split(",") if k.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Convenience accessor — Pydantic re-reads env on construction."""
    return Settings()
