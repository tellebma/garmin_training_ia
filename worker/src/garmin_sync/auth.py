"""Authentication for inbound requests.

Two modes:
  1. End-user requests (from Next.js Server Action on behalf of the user) carry
     a Supabase-issued JWT in the Authorization header. We verify the signature
     using SUPABASE_JWT_SECRET and trust the `sub` claim as the user id.
  2. Cron/admin requests (from the host's systemd timer or operator) carry the
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
