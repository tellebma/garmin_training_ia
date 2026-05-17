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
