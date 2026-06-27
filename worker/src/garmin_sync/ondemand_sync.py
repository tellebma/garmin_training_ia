"""On-demand Garmin sync (E15.3): atomic claim guard + activities-only delta.

Triggered from the app (auto on open + manual button). The guard lives here,
right in front of the Garmin API, so any caller is throttled. Cooldowns:
auto 1800s, manual 300s. The claim is atomic (single RPC) so two concurrent
opens trigger at most one sync.
"""

from __future__ import annotations

import logging
from typing import Any

from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)

WINDOW_BY_TRIGGER: dict[str, int] = {"auto": 1800, "manual": 300}


def try_claim_sync(user_id: str, window_seconds: int) -> dict[str, Any]:
    """Atomically claim a sync slot. Returns the RPC tri-state jsonb.

    {"outcome": "claimed"} | {"outcome": "cooldown", "retry_after_seconds": int}
    | {"outcome": "no_credentials"}.
    """
    db = get_admin_client()
    resp = db.rpc(
        "try_claim_garmin_sync",
        {"p_user_id": user_id, "p_window_seconds": window_seconds},
    ).execute()
    data = resp.data
    if not isinstance(data, dict) or "outcome" not in data:
        log.warning("try_claim_garmin_sync returned unexpected payload for user=%s", user_id)
        return {"outcome": "no_credentials"}
    return data
