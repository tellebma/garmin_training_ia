"""Worker-side feature flag reads. Service-role bypasses RLS, so this reads the
table directly rather than going through the is_feature_flag_active() RPC."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)


def is_flag_active(db: Any, key: str) -> bool:
    try:
        resp = (
            db.table("feature_flags")
            .select("enabled, expires_at")
            .eq("key", key)
            .maybe_single()
            .execute()
        )
        row = resp.data
    except Exception:
        log.exception("feature flag read failed key=%s — treating as inactive", key)
        return False
    if not row or not row.get("enabled"):
        return False
    expires_at = row.get("expires_at")
    if expires_at is None:
        return True
    return datetime.fromisoformat(expires_at) > datetime.now(UTC)
