"""Discord webhook alerting — proactive push for captured errors.

Decoupled from Sentry: fires whenever ``DISCORD_WEBHOOK_URL`` is set, even with
Sentry off, so the owner gets a phone notification the moment something breaks.
Alerting must NEVER raise into the caller — every failure here is swallowed and
logged. Volume is fine for the small beta; fine-grained routing/thresholds live
in Sentry alert rules, this is the always-on direct push.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from garmin_sync.config import get_settings

log = logging.getLogger("garmin_sync")

_TIMEOUT_S = 5.0
# Discord embed colours (decimal) per severity.
_LEVEL_COLORS = {"error": 0xE01E5A, "warning": 0xECB22E, "info": 0x2EB67D}
_MAX_DESCRIPTION = 1500
_MAX_FIELD_VALUE = 256


def _build_payload(
    exc: BaseException, *, where: str, env: str, level: str, tags: dict[str, Any]
) -> dict[str, Any]:
    fields = [{"name": "env", "value": env, "inline": True}]
    fields += [
        {"name": key, "value": str(value)[:_MAX_FIELD_VALUE], "inline": True}
        for key, value in tags.items()
        if value is not None
    ]
    return {
        "embeds": [
            {
                "title": f"⚠️ {type(exc).__name__} — {where}"[:256],
                "description": f"```{str(exc)[:_MAX_DESCRIPTION]}```",
                "color": _LEVEL_COLORS.get(level, _LEVEL_COLORS["error"]),
                "fields": fields[:25],
            }
        ]
    }


def notify_discord_error(
    exc: BaseException, *, where: str, level: str = "error", **tags: Any
) -> None:
    """POST an error embed to the configured Discord webhook. No-op when unset."""
    settings = get_settings()
    url = settings.discord_webhook_url.get_secret_value() if settings.discord_webhook_url else ""
    if not url:
        return
    payload = _build_payload(exc, where=where, env=settings.env, level=level, tags=tags)
    try:
        response = httpx.post(url, json=payload, timeout=_TIMEOUT_S)
        response.raise_for_status()
    except Exception as alert_exc:  # alerting must never break the caller
        log.warning("discord alert failed for where=%s: %s", where, alert_exc)
