"""Persists LLM token usage for finops (E18). Best-effort — never raises."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from garmin_sync.coach.llm_pricing import compute_cost_usd
from garmin_sync.observability import capture
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger("garmin_sync")

# Longueur max du motif d'échec persisté (les messages de validation sont courts,
# mais une erreur réseau peut embarquer un payload entier).
_ERROR_REASON_MAX_LEN = 500

# Alerte taux d'échec de génération : fenêtre glissante, seuil et volume minimal
# (en dessous, 1-2 échecs isolés déclencheraient du bruit). Issue #124 : 34 %
# d'échec en prod sont restés invisibles pendant 3 semaines.
_FAILURE_RATE_WINDOW = timedelta(hours=24)
_FAILURE_RATE_THRESHOLD = 0.30
_FAILURE_RATE_MIN_SAMPLES = 5
_FAILURE_RATE_ALERT_COOLDOWN = timedelta(hours=24)

# Anti-spam par process (le worker FastAPI est long-vivant ; le cron est un
# process séparé) : au plus une alerte Discord/Sentry par cooldown.
_last_failure_rate_alert_at: datetime | None = None


class GenerationFailureRateExceeded(Exception):
    """Signal (pas une erreur d'exécution) : trop d'échecs de génération sur 24 h."""


def record_llm_usage(
    *,
    user_id: str,
    feature: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    attempts: int = 1,
    status: str = "ok",
    session_id: str | None = None,
    error_reason: str | None = None,
) -> None:
    try:
        db = get_admin_client()
        row: dict[str, str | int | float | None] = {
            "user_id": user_id,
            "feature": feature,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_usd": compute_cost_usd(model, prompt_tokens, completion_tokens),
            "attempts": attempts,
            "status": status,
            "session_id": session_id,
        }
        if error_reason is not None:
            row = {**row, "error_reason": error_reason[:_ERROR_REASON_MAX_LEN]}
        db.table("llm_usage").insert(row).execute()
    except Exception as exc:
        log.exception("record_llm_usage failed user=%s feature=%s", user_id, feature)
        capture(exc, where="record_llm_usage", user_id=user_id, feature=feature)


def maybe_alert_generation_failure_rate(now: datetime | None = None) -> bool:
    """Alerte (Sentry + Discord via ``capture``) si le taux d'échec de génération
    sur 24 h dépasse le seuil. Best-effort, jamais bloquant. Retourne True si
    une alerte a été émise.
    """
    global _last_failure_rate_alert_at
    try:
        current = now or datetime.now(UTC)
        if (
            _last_failure_rate_alert_at is not None
            and current - _last_failure_rate_alert_at < _FAILURE_RATE_ALERT_COOLDOWN
        ):
            return False

        db = get_admin_client()
        since = (current - _FAILURE_RATE_WINDOW).isoformat()
        resp = (
            db.table("llm_usage")
            .select("status")
            .eq("feature", "session_workout")
            .gte("created_at", since)
            .execute()
        )
        rows = resp.data if isinstance(resp.data, list) else []
        total = len(rows)
        failed = sum(1 for r in rows if isinstance(r, dict) and r.get("status") == "failed")
        if total < _FAILURE_RATE_MIN_SAMPLES or failed / total < _FAILURE_RATE_THRESHOLD:
            return False

        _last_failure_rate_alert_at = current
        rate_pct = round(100 * failed / total)
        capture(
            GenerationFailureRateExceeded(
                f"{failed}/{total} générations de séance en échec sur 24 h ({rate_pct} %)"
            ),
            where="llm_generation_failure_rate",
            level="warning",
            failed=failed,
            total=total,
        )
        return True
    except Exception:
        log.exception("maybe_alert_generation_failure_rate failed")
        return False
