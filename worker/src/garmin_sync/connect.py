"""Garmin connect/MFA flow. Stores encrypted tokens on success."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from garmin_sync.crypto import TokenCipher
from garmin_sync.garmin_client import (
    GarminAuthError,
    GarminMFARequired,
    login_with_credentials,
    submit_mfa_code,
)
from garmin_sync.supabase_client import get_admin_client

_MFA_EXPIRY_S = 300
_pending_mfa: dict[str, tuple[float, str, Any]] = {}


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, (ts, _u, _c) in _pending_mfa.items() if now - ts > _MFA_EXPIRY_S]
    for k in expired:
        _pending_mfa.pop(k, None)


def start_connect_flow(*, user_id: str, email: str, password: str) -> dict[str, Any]:
    _purge_expired()
    try:
        tokens_json = login_with_credentials(email, password)
    except GarminMFARequired as e:
        challenge_id = uuid.uuid4().hex
        _pending_mfa[challenge_id] = (time.time(), user_id, e.challenge)
        return {"status": "mfa_required", "challenge_id": challenge_id}
    except GarminAuthError:
        return {"status": "invalid_credentials"}

    _persist_tokens(user_id=user_id, tokens_json=tokens_json)
    return {"status": "connected"}


def resume_connect_flow(*, user_id: str, challenge_id: str, code: str) -> dict[str, Any]:
    _purge_expired()
    entry = _pending_mfa.pop(challenge_id, None)
    if not entry:
        return {"status": "challenge_expired"}

    _ts, owner, challenge = entry
    if owner != user_id:
        return {"status": "challenge_user_mismatch"}

    try:
        tokens_json = submit_mfa_code(challenge, code)
    except GarminAuthError:
        return {"status": "invalid_code"}

    _persist_tokens(user_id=user_id, tokens_json=tokens_json)
    return {"status": "connected"}


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
