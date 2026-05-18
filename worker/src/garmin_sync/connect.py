"""Garmin connect/MFA flow. Stores encrypted tokens on success.

Server-side cooldown
--------------------
``python-garminconnect 0.3.x`` runs a 5-strategy cascade on every ``login()``
call (each strategy can itself iterate over multiple TLS impersonations), so a
single user click can produce 10-15 requests to Garmin SSO. Spamming the
connect form a few times is enough to get the worker's IP banned for hours.

We track recent per-user failures in a short-lived in-memory dict and reject
follow-up attempts during a cooldown window — same lifetime semantics as
``_pending_mfa`` (lost on worker restart, acceptable for MVP single-instance).

Reasons we cool down on:
- ``rate_limited``  → 30 minutes (Garmin already told us to back off)
- ``invalid_credentials`` → 60 seconds (slow down brute-force / typos without
  blocking the user for ages)
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from garmin_sync.crypto import TokenCipher
from garmin_sync.garmin_client import (
    GarminAuthError,
    GarminError,
    GarminMFARequired,
    GarminRateLimitError,
    login_with_credentials,
    submit_mfa_code,
)
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

_MFA_EXPIRY_S = 300
_pending_mfa: dict[str, tuple[float, str, Any]] = {}

_COOLDOWN_RATE_LIMITED_S = 30 * 60
_COOLDOWN_INVALID_CREDS_S = 60
# {user_id: (cooldown_until_ts, reason)}
_cooldowns: dict[str, tuple[float, str]] = {}


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, (ts, _u, _c) in _pending_mfa.items() if now - ts > _MFA_EXPIRY_S]
    for k in expired:
        _pending_mfa.pop(k, None)
    expired_cd = [k for k, (until, _r) in _cooldowns.items() if until <= now]
    for k in expired_cd:
        _cooldowns.pop(k, None)


def _check_cooldown(user_id: str) -> dict[str, Any] | None:
    """Return a cooldown response if user is currently rate-limited locally."""
    entry = _cooldowns.get(user_id)
    if not entry:
        return None
    until, reason = entry
    remaining = int(until - time.time())
    if remaining <= 0:
        _cooldowns.pop(user_id, None)
        return None
    return {"status": reason, "retry_after_seconds": remaining}


def _set_cooldown(user_id: str, reason: str, seconds: int) -> int:
    _cooldowns[user_id] = (time.time() + seconds, reason)
    return seconds


def _new_error_id() -> str:
    return uuid.uuid4().hex[:8]


def start_connect_flow(*, user_id: str, email: str, password: str) -> dict[str, Any]:
    _purge_expired()
    cooled = _check_cooldown(user_id)
    if cooled is not None:
        return cooled
    try:
        try:
            tokens_json = login_with_credentials(email, password)
        except GarminMFARequired as e:
            challenge_id = uuid.uuid4().hex
            _pending_mfa[challenge_id] = (time.time(), user_id, e.challenge)
            return {"status": "mfa_required", "challenge_id": challenge_id}
        except GarminAuthError:
            retry = _set_cooldown(user_id, "invalid_credentials", _COOLDOWN_INVALID_CREDS_S)
            return {"status": "invalid_credentials", "retry_after_seconds": retry}
        except GarminRateLimitError:
            retry = _set_cooldown(user_id, "rate_limited", _COOLDOWN_RATE_LIMITED_S)
            return {"status": "rate_limited", "retry_after_seconds": retry}
        except GarminError as e:
            error_id = _new_error_id()
            log.exception("[%s] Garmin error during connect for user=%s", error_id, user_id)
            return {
                "status": "garmin_error",
                "error_id": error_id,
                "type": type(e).__name__,
            }

        _cooldowns.pop(user_id, None)
        _persist_tokens(user_id=user_id, tokens_json=tokens_json)
        return {"status": "connected"}
    except Exception as e:
        error_id = _new_error_id()
        log.exception("[%s] Unexpected error during connect for user=%s", error_id, user_id)
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }


def resume_connect_flow(*, user_id: str, challenge_id: str, code: str) -> dict[str, Any]:
    _purge_expired()
    cooled = _check_cooldown(user_id)
    if cooled is not None:
        return cooled
    try:
        entry = _pending_mfa.pop(challenge_id, None)
        if not entry:
            return {"status": "challenge_expired"}

        _ts, owner, challenge = entry
        if owner != user_id:
            return {"status": "challenge_user_mismatch"}

        try:
            tokens_json = submit_mfa_code(challenge, code)
        except GarminAuthError:
            retry = _set_cooldown(user_id, "invalid_code", _COOLDOWN_INVALID_CREDS_S)
            return {"status": "invalid_code", "retry_after_seconds": retry}
        except GarminRateLimitError:
            retry = _set_cooldown(user_id, "rate_limited", _COOLDOWN_RATE_LIMITED_S)
            return {"status": "rate_limited", "retry_after_seconds": retry}
        except GarminError as e:
            error_id = _new_error_id()
            log.exception("[%s] Garmin error during MFA resume for user=%s", error_id, user_id)
            return {
                "status": "garmin_error",
                "error_id": error_id,
                "type": type(e).__name__,
            }

        _cooldowns.pop(user_id, None)
        _persist_tokens(user_id=user_id, tokens_json=tokens_json)
        return {"status": "connected"}
    except Exception as e:
        error_id = _new_error_id()
        log.exception("[%s] Unexpected error during MFA resume for user=%s", error_id, user_id)
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }


def _persist_tokens(*, user_id: str, tokens_json: str) -> None:
    cipher = TokenCipher()
    encrypted = cipher.encrypt(tokens_json)
    db = get_admin_client()
    db.table("garmin_credentials").upsert(
        {
            "user_id": user_id,
            "oauth_tokens_encrypted": encrypted.decode("ascii"),
            "token_refresh_failed_at": None,
            "last_sync_status": None,
            "updated_at": datetime.now(UTC).isoformat(),
        },
        on_conflict="user_id",
    ).execute()
