"""On-demand Garmin sync (E15.3): atomic claim guard + activities-only delta.

Triggered from the app (auto on open + manual button). The guard lives here,
right in front of the Garmin API, so any caller is throttled. Cooldowns:
auto 1800s, manual 300s. The claim is atomic (single RPC) so two concurrent
opens trigger at most one sync.
"""

from __future__ import annotations

import logging
import threading
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


def _start_sync_thread(user_id: str) -> None:
    """Spawn the activities-only sync in a daemon thread (non-blocking response).

    Mirrors the post-connect pattern: run_sync_for_user persists its own outcome
    to garmin_credentials.last_sync_status, so progress stays observable. A failure
    here must never surface — the cron retries.
    """

    def _run() -> None:
        try:
            from garmin_sync.cron import run_sync_for_user
            from garmin_sync.sync import SYNC_MODE_ACTIVITIES_ONLY

            run_sync_for_user(user_id, mode=SYNC_MODE_ACTIVITIES_ONLY)
        except Exception:
            log.exception("on-demand sync failed for user=%s", user_id)

    threading.Thread(target=_run, name=f"ondemand-sync-{user_id}", daemon=True).start()


def run_ondemand_sync(user_id: str, trigger: str) -> dict[str, Any]:
    """Validate trigger, claim a slot, and launch the sync if allowed."""
    window = WINDOW_BY_TRIGGER.get(trigger)
    if window is None:
        return {"status": "invalid_trigger"}

    claim = try_claim_sync(user_id, window)
    outcome = claim["outcome"]
    if outcome == "cooldown":
        return {"status": "cooldown", "retry_after_seconds": claim["retry_after_seconds"]}
    if outcome == "no_credentials":
        return {"status": "no_credentials"}

    _start_sync_thread(user_id)
    return {"status": "started"}
