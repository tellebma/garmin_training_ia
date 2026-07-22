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
from httpx import HTTPStatusError

from garmin_sync.config import get_settings
from garmin_sync.observability import capture
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger("garmin_sync")

_COSTS_URL = "https://api.openai.com/v1/organization/costs"
# Fenêtre re-pullée à chaque run. 4 jours ne rattrapaient jamais les trous
# historiques (snapshot démarré le 05/07 alors que la facturation courait depuis
# mi-juin) : un mois glissant rend le snapshot auto-réparant, pour un seul appel
# API (upsert idempotent par billing_date).
_LOOKBACK_DAYS = 30
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


def _bucket_to_row(bucket: dict[str, Any]) -> dict[str, Any]:
    billing_date = datetime.fromtimestamp(bucket["start_time"], tz=UTC).date().isoformat()
    # amount.value is a string on the real Costs API (decimal-as-string, avoids
    # float precision issues on currency) — confirmed empirically against a
    # live account; cast explicitly since a bare sum() of strings crashes.
    total = sum(float(r.get("amount", {}).get("value") or 0.0) for r in bucket.get("results", []))
    return {"billing_date": billing_date, "cost_usd": round(total, 6)}


def run_billing_sync_cron() -> dict[str, Any]:
    settings = get_settings()
    api_key = settings.openai_admin_api_key.get_secret_value()
    if not api_key:
        return {"status": "skipped_no_key"}

    # Aligné sur minuit UTC : avec un start_time à l'heure du cron (05:00), les
    # buckets `1d` d'OpenAI courent de 05:00 à 05:00 et chevauchent deux jours
    # calendaires. Comme billing_date est dérivé de bucket["start_time"], le coût
    # de 00:00-05:00 était attribué à la veille et des journées ressortaient à
    # 0,00 $ alors que llm_usage prouvait un usage.
    midnight_utc = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start_time = int((midnight_utc - timedelta(days=_LOOKBACK_DAYS)).timestamp())
    try:
        buckets = _fetch_daily_costs(api_key, start_time)
        rows = [_bucket_to_row(b) for b in buckets]
        if rows:
            db = get_admin_client()
            db.table("openai_billing_snapshot").upsert(rows, on_conflict="billing_date").execute()
        return {"status": "ok", "days_upserted": len(rows)}
    except HTTPStatusError as exc:
        # The response body carries OpenAI's actual error message (e.g. which
        # permission/scope is missing) — the exception's own str() doesn't
        # include it, so log it explicitly or a 403 is undiagnosable from logs.
        log.exception(
            "billing_sync failed: HTTP %s — %s",
            exc.response.status_code,
            exc.response.text[:2000],
        )
        capture(exc, where="billing_sync", status_code=exc.response.status_code)
        return {"status": "error"}
    except Exception as exc:
        log.exception("billing_sync failed")
        capture(exc, where="billing_sync")
        return {"status": "error"}
