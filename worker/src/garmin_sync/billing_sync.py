"""Daily ground-truth pull of OpenAI's real invoiced cost (E18 finops).

Best-effort, mirrors alerting.py's style: never raises into the cron caller.
Re-pulls the last few days on every run (upsert by billing_date) because
OpenAI's Costs API has ~24-48h of billing delay — a day fetched "final" at
05:00 UTC can still be revised the next run.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from garmin_sync.config import get_settings
from garmin_sync.observability import capture
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger("garmin_sync")

_COSTS_URL = "https://api.openai.com/v1/organization/costs"
_LOOKBACK_DAYS = 4
_TIMEOUT_S = 15.0


def _fetch_daily_costs(api_key: str, start_time: int) -> list[dict[str, Any]]:
    response = httpx.get(
        _COSTS_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        params={"start_time": start_time, "bucket_width": "1d", "limit": _LOOKBACK_DAYS + 1},
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    data: list[dict[str, Any]] = response.json().get("data", [])
    return data


# NOTE: bucket["start_time"] / bucket["results"][].amount.value shape is an assumption,
# not yet verified against live OpenAI Costs API docs — confirm before relying in prod.
def _bucket_to_row(bucket: dict[str, Any]) -> dict[str, Any]:
    billing_date = datetime.fromtimestamp(bucket["start_time"], tz=UTC).date().isoformat()
    total = sum(r.get("amount", {}).get("value", 0.0) for r in bucket.get("results", []))
    return {"billing_date": billing_date, "cost_usd": round(total, 6)}


def run_billing_sync_cron() -> dict[str, Any]:
    settings = get_settings()
    api_key = settings.openai_admin_api_key.get_secret_value()
    if not api_key:
        return {"status": "skipped_no_key"}

    start_time = int((datetime.now(UTC) - timedelta(days=_LOOKBACK_DAYS)).timestamp())
    try:
        buckets = _fetch_daily_costs(api_key, start_time)
        rows = [_bucket_to_row(b) for b in buckets]
        if rows:
            db = get_admin_client()
            db.table("openai_billing_snapshot").upsert(rows, on_conflict="billing_date").execute()
        return {"status": "ok", "days_upserted": len(rows)}
    except Exception as exc:
        log.exception("billing_sync failed")
        capture(exc, where="billing_sync")
        return {"status": "error"}
