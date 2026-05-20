"""Tests for JWT verification of Supabase-issued user tokens (ES256 via JWKS)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from garmin_sync.auth import (
    AuthError,
    verify_shared_token,
    verify_supabase_jwt,
)


def _generate_key_pair() -> tuple[ec.EllipticCurvePrivateKey, dict[str, Any]]:
    """Generate an ECC P-256 key pair, return (private_key, public_jwk)."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    public_jwk = json.loads(ECAlgorithm.to_jwk(public_key))
    public_jwk["kid"] = "test-key-1"
    public_jwk["alg"] = "ES256"
    public_jwk["use"] = "sig"
    return private_key, public_jwk


def _make_jwt(
    private_key: ec.EllipticCurvePrivateKey,
    kid: str = "test-key-1",
    *,
    sub: str = "user-abc-123",
    exp_offset: int = 3600,
    aud: str = "authenticated",
) -> str:
    """Encode a test JWT with the given private key (ES256)."""
    payload = {"sub": sub, "exp": int(time.time()) + exp_offset, "aud": aud}
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(payload, pem, algorithm="ES256", headers={"kid": kid})


@pytest.fixture
def jwks_setup() -> Iterator[tuple[ec.EllipticCurvePrivateKey, dict[str, Any]]]:
    """Provide a private key and patch _jwks_client to return its public key.

    Clears the lru_cache before yielding so each test gets a fresh client.
    """
    from garmin_sync import auth as auth_module

    auth_module._jwks_client.cache_clear()

    private_key, public_jwk = _generate_key_pair()
    jwks = {"keys": [public_jwk]}

    # Patch PyJWKClient.fetch_data so the client returns our in-memory JWKS
    # instead of making an HTTP request.
    with patch("garmin_sync.auth.PyJWKClient.fetch_data", return_value=jwks):
        yield private_key, public_jwk


def test_verify_supabase_jwt_returns_user_id(
    jwks_setup: tuple[ec.EllipticCurvePrivateKey, dict[str, Any]],
) -> None:
    private_key, _ = jwks_setup
    token = _make_jwt(private_key, sub="user-abc-123")
    assert verify_supabase_jwt(token) == "user-abc-123"


def test_verify_supabase_jwt_rejects_expired_token(
    jwks_setup: tuple[ec.EllipticCurvePrivateKey, dict[str, Any]],
) -> None:
    private_key, _ = jwks_setup
    token = _make_jwt(private_key, exp_offset=-60)
    with pytest.raises(AuthError, match="expired"):
        verify_supabase_jwt(token)


def test_verify_supabase_jwt_rejects_wrong_signature(
    jwks_setup: tuple[ec.EllipticCurvePrivateKey, dict[str, Any]],
) -> None:
    # Sign with a different (unrelated) private key — JWKS won't match
    other_key, _ = _generate_key_pair()
    token = _make_jwt(other_key, kid="test-key-1")
    with pytest.raises(AuthError):
        verify_supabase_jwt(token)


def test_verify_supabase_jwt_rejects_wrong_audience(
    jwks_setup: tuple[ec.EllipticCurvePrivateKey, dict[str, Any]],
) -> None:
    private_key, _ = jwks_setup
    token = _make_jwt(private_key, aud="anon")  # not "authenticated"
    with pytest.raises(AuthError, match="audience"):
        verify_supabase_jwt(token)


def test_verify_shared_token_accepts_match() -> None:
    assert verify_shared_token("shared-token-test") is True


def test_verify_shared_token_rejects_mismatch() -> None:
    assert verify_shared_token("nope") is False


def test_verify_supabase_jwt_wraps_jwks_fetch_error_as_auth_error() -> None:
    """If the JWKS endpoint is unreachable or returns a key we can't load, we
    must convert the underlying exception into our AuthError so callers only
    have to catch one error type.

    Covers auth.py lines 63-66 (the generic Exception handler)."""
    from garmin_sync import auth as auth_module

    auth_module._jwks_client.cache_clear()

    with (
        patch(
            "garmin_sync.auth.PyJWKClient.get_signing_key_from_jwt",
            side_effect=RuntimeError("network blew up"),
        ),
        pytest.raises(AuthError, match="jwt verification failed"),
    ):
        verify_supabase_jwt("any-token-value")


def test_verify_supabase_jwt_rejects_token_missing_sub_claim(
    jwks_setup: tuple[ec.EllipticCurvePrivateKey, dict[str, Any]],
) -> None:
    """A JWT signed with the right key but where `sub` is empty/missing
    must be rejected — the verifier returns the `sub` so we can't tolerate
    None there.

    Covers auth.py lines 68-71 (the `not isinstance(sub, str) or not sub` branch)."""
    private_key, _ = jwks_setup
    # Encode a token where sub is explicitly empty
    token = _make_jwt(private_key, sub="")
    with pytest.raises(AuthError, match="missing 'sub'"):
        verify_supabase_jwt(token)


def test_verify_supabase_jwt_rejects_malformed_token(
    jwks_setup: tuple[ec.EllipticCurvePrivateKey, dict[str, Any]],
) -> None:
    """A token that doesn't even decode as JWT must raise AuthError
    via the InvalidTokenError branch.

    Covers auth.py lines 58-60."""
    with pytest.raises(AuthError):
        verify_supabase_jwt("not.a.jwt")
