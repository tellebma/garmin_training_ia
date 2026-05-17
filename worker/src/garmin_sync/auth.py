"""Authentication for inbound requests.

User JWTs (issued by Supabase Auth) are verified via JWKS — Supabase signs
them with ECC P-256 (ES256). We use PyJWKClient to fetch and cache the JWKS
from the project's auth/v1/.well-known/jwks.json endpoint.

Cron/admin requests carry the WORKER_SHARED_TOKEN secret, compared with
hmac.compare_digest.
"""

from __future__ import annotations

import hmac
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from garmin_sync.config import get_settings


class AuthError(Exception):
    """Raised when authentication fails."""


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    """Cached JWKS client (refreshes keys automatically on cache miss).

    The PyJWKClient caches keys in-memory by `kid`. When a JWT carries a new
    `kid`, the client refetches the JWKS once and caches.
    """
    supabase_url = str(get_settings().supabase_url).rstrip("/")
    jwks_uri = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_uri, cache_keys=True, lifespan=600)  # 10-minute key cache


def verify_supabase_jwt(token: str) -> str:
    """Verify a Supabase-issued user JWT (ES256 via JWKS).

    Returns the `sub` claim (user UUID). Raises AuthError on any failure.
    """
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["ES256"],
            audience="authenticated",  # Supabase user tokens have aud=authenticated
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as e:
        msg = "jwt expired"
        raise AuthError(msg) from e
    except jwt.InvalidAudienceError as e:
        msg = "jwt audience invalid"
        raise AuthError(msg) from e
    except jwt.InvalidTokenError as e:
        msg = "jwt invalid"
        raise AuthError(msg) from e
    except AuthError:
        raise
    except Exception as e:
        # JWKS fetch failure, kid not found, etc. — treat as auth failure.
        msg = f"jwt verification failed: {e}"
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
