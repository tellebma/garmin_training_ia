"""Persists LLM token usage for finops (E18). Best-effort — never raises."""

from __future__ import annotations

import logging

from garmin_sync.coach.llm_pricing import compute_cost_usd
from garmin_sync.observability import capture
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger("garmin_sync")


def record_llm_usage(
    *,
    user_id: str,
    feature: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    try:
        db = get_admin_client()
        db.table("llm_usage").insert(
            {
                "user_id": user_id,
                "feature": feature,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "cost_usd": compute_cost_usd(model, prompt_tokens, completion_tokens),
            }
        ).execute()
    except Exception as exc:
        log.exception("record_llm_usage failed user=%s feature=%s", user_id, feature)
        capture(exc, where="record_llm_usage", user_id=user_id, feature=feature)
