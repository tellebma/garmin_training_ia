"""Sentry error tracking + shared error-reporting helpers.

Sentry is wired up but only *activates* when ``SENTRY_DSN`` is configured, so
local/dev and tests stay offline. The capture helpers are safe no-ops when
Sentry is not initialised (the SDK simply drops events), which lets us sprinkle
``capture(...)`` at every silent-failure point without guarding each call.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import sentry_sdk

from garmin_sync.alerting import notify_discord_error
from garmin_sync.config import get_settings

log = logging.getLogger("garmin_sync")


def init_sentry() -> bool:
    """Initialise Sentry if a DSN is configured. Returns True when enabled."""
    settings = get_settings()
    dsn = settings.sentry_dsn.get_secret_value() if settings.sentry_dsn else ""
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )
    log.info("sentry: initialised (env=%s)", settings.env)
    return True


def new_error_id() -> str:
    """Short correlation id surfaced to the browser and tagged on the event."""
    return uuid.uuid4().hex[:8]


def capture(exc: BaseException, *, where: str, level: str = "error", **tags: Any) -> None:
    """Send an exception to Sentry with contextual tags.

    No-op when Sentry is disabled. ``where`` identifies the failing operation;
    extra keyword tags (user_id, session_id, error_id…) are attached when set.
    Also fans out to Discord when a webhook is configured (independent of Sentry).
    """
    with sentry_sdk.new_scope() as scope:
        scope.level = level
        scope.set_tag("where", where)
        for key, value in tags.items():
            if value is not None:
                scope.set_tag(key, str(value))
        sentry_sdk.capture_exception(exc)
    notify_discord_error(exc, where=where, level=level, **tags)


def report_endpoint_error(exc: Exception, *, endpoint: str, **context: Any) -> dict[str, Any]:
    """Log + capture an unexpected endpoint error, return the JSON error body.

    Centralises the ``{status, error_id, type}`` contract so every endpoint
    reports to Sentry with the *same* error_id used in the browser response —
    grep ``docker logs`` or click the Sentry event from one id.
    """
    error_id = new_error_id()
    ctx = " ".join(f"{key}={value}" for key, value in context.items())
    log.exception("[%s] %s crashed %s", error_id, endpoint, ctx)
    capture(exc, where=endpoint, error_id=error_id, **context)
    return {"status": "unexpected_error", "error_id": error_id, "type": type(exc).__name__}
