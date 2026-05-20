"""Per-user rate limit for coach LLM endpoints, backed by a Postgres RPC.

The RPC `check_and_log_coach_rate_limit(user_id, action, max_count, window_seconds)`
performs an atomic check-and-insert and also enforces a hard daily cap of 1000
calls per user (regardless of action).
"""

from __future__ import annotations

from dataclasses import dataclass

from garmin_sync.supabase_client import get_admin_client


class RateLimited(Exception):
    """Raised when a user exceeds the per-action sliding-window quota."""


@dataclass(frozen=True)
class RateLimit:
    """Per-action sliding-window quota."""

    action: str
    max_count: int
    window_seconds: int


# Tuned for MVP scale (1 owner + 5-10 friends). Numbers should hold for E5 cost
# while letting normal usage proceed without hiccups.
#   - ensure_sessions: called on every /today open. 60/hour = a tab refresh every minute.
#   - regenerate_session: explicit user click. 10/hour is plenty for sanity-checks.
#   - daily_briefing: called on every /today open. Same cadence as ensure_sessions.
ENSURE_SESSIONS = RateLimit(action="ensure_sessions", max_count=60, window_seconds=3600)
REGENERATE_SESSION = RateLimit(action="regenerate_session", max_count=10, window_seconds=3600)
DAILY_BRIEFING = RateLimit(action="daily_briefing", max_count=60, window_seconds=3600)


def check_or_raise(*, user_id: str, limit: RateLimit) -> None:
    """Check rate limit, insert log row atomically. Raises RateLimited when exceeded."""
    db = get_admin_client()
    allowed = (
        db.rpc(
            "check_and_log_coach_rate_limit",
            {
                "p_user_id": user_id,
                "p_action": limit.action,
                "p_max_count": limit.max_count,
                "p_window_seconds": limit.window_seconds,
            },
        )
        .execute()
        .data
    )
    if not allowed:
        msg = (
            f"rate limited: {limit.action} > {limit.max_count}/"
            f"{limit.window_seconds}s for user {user_id}"
        )
        raise RateLimited(msg)
