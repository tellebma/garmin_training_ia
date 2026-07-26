"""FastAPI HTTP entry point: health, manual sync, Garmin connect/MFA.

CORS: this worker is only ever called server-to-server — the Next.js app talks
to it via Server Actions using the worker shared token or a forwarded Supabase
user JWT, never directly from a browser. No browser origin is ever legitimate,
so ``create_app`` attaches an explicit deny-all ``CORSMiddleware``
(``allow_origins=[]``). Without this middleware, Starlette's default (no CORS
headers at all) already blocks cross-origin browser reads — the middleware
below exists to make that a documented, testable decision instead of an
accident of omission (SEC-2).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from garmin_sync.auth import AuthError, verify_shared_token, verify_supabase_jwt
from garmin_sync.config import get_settings
from garmin_sync.cron import run_sync_for_user
from garmin_sync.observability import init_sentry, report_endpoint_error
from garmin_sync.supabase_client import get_admin_client

_BEARER_PREFIX = "Bearer "

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)

log = logging.getLogger(__name__)


router = APIRouter()


@asynccontextmanager
async def scheduler_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start the in-container scheduler on app startup, stop it on shutdown."""
    from garmin_sync.scheduler import init_scheduler, shutdown_scheduler

    init_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


def create_app(*, enable_scheduler: bool | None = None) -> FastAPI:
    """Build the FastAPI app.

    Tests default to no scheduler via ENV=test, while runtime keeps the scheduler
    attached through the lifespan hook.
    """
    if enable_scheduler is None:
        enable_scheduler = get_settings().env != "test"
    init_sentry()
    app_lifespan = scheduler_lifespan if enable_scheduler else None
    created = FastAPI(title="garmin-sync", version="0.1.0", lifespan=app_lifespan)
    created.include_router(router)
    # SEC-2: explicit, intentional cross-origin deny (see module docstring).
    created.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=False,
        allow_methods=[],
        allow_headers=[],
    )
    return created


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": get_settings().env}


def _require_shared_token(authorization: str | None) -> None:
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.removeprefix(_BEARER_PREFIX)
    if not verify_shared_token(token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


def _require_user_jwt(authorization: str | None) -> str:
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.removeprefix(_BEARER_PREFIX)
    try:
        return verify_supabase_jwt(token)
    except AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e


_AuthHeader = Annotated[str | None, Header()]


@router.post("/sync/{user_id}")
async def sync_user(
    user_id: str,
    authorization: _AuthHeader = None,
    initial: bool = False,
) -> dict[str, Any]:
    """Sync a single user. Pass ?initial=true to force a 90-day backfill."""
    _require_shared_token(authorization)
    return run_sync_for_user(user_id, initial=initial)


@router.post("/garmin/sync")
async def garmin_sync(
    trigger: str,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    """On-demand sync triggered by the app (E15.3). trigger = auto | manual."""
    user_id = _require_user_jwt(authorization)
    if trigger not in ("auto", "manual"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid trigger")
    try:
        from garmin_sync.ondemand_sync import run_ondemand_sync

        return run_ondemand_sync(user_id, trigger)
    except Exception as e:
        return report_endpoint_error(e, endpoint="garmin_sync", user_id=user_id)


class GarminConnectRequest(BaseModel):
    email: str
    password: str


class GarminMFARequest(BaseModel):
    challenge_id: str
    code: str


@router.post("/garmin/connect")
async def garmin_connect(
    body: GarminConnectRequest,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    """Initiate Garmin login. Called by Next.js Server Action on behalf of user."""
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.connect import start_connect_flow

        return start_connect_flow(user_id=user_id, email=body.email, password=body.password)
    except Exception as e:
        return report_endpoint_error(e, endpoint="garmin_connect", user_id=user_id)


@router.post("/garmin/mfa")
async def garmin_mfa(
    body: GarminMFARequest,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.connect import resume_connect_flow

        return resume_connect_flow(user_id=user_id, challenge_id=body.challenge_id, code=body.code)
    except Exception as e:
        return report_endpoint_error(e, endpoint="garmin_mfa", user_id=user_id)


class StravaConnectRequest(BaseModel):
    code: str


def _require_strava_enabled() -> None:
    """404 the whole Strava surface when the integration isn't configured.

    ``POST /strava/webhook`` is unauthenticated by design (Strava signs nothing),
    so on a deployment without Strava secrets it is a free, internet-reachable
    way to spawn daemon threads and to delete ``athlete_strava_credentials``
    rows via a forged ``authorized: false`` event. Refusing every Strava route
    unless the secrets are present makes the attack surface disappear with the
    configuration instead of depending on a reverse-proxy allowlist.
    """
    if not get_settings().strava_configured:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


@router.post("/strava/connect")
async def strava_connect(
    body: StravaConnectRequest,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    _require_strava_enabled()
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.strava_connect import start_connect_flow

        return start_connect_flow(user_id=user_id, code=body.code)
    except Exception as e:
        return report_endpoint_error(e, endpoint="strava_connect", user_id=user_id)


@router.post("/strava/disconnect")
async def strava_disconnect(
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    _require_strava_enabled()
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.strava_connect import disconnect

        return disconnect(user_id=user_id)
    except Exception as e:
        return report_endpoint_error(e, endpoint="strava_disconnect", user_id=user_id)


@router.get("/strava/webhook")
async def strava_webhook_verify(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> dict[str, str]:
    _require_strava_enabled()
    from garmin_sync.strava_webhook import verify_challenge

    challenge = verify_challenge(mode=hub_mode, token=hub_verify_token, challenge=hub_challenge)
    if challenge is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid verify token")
    return {"hub.challenge": challenge}


@router.post("/strava/webhook")
async def strava_webhook_event(payload: dict[str, Any]) -> dict[str, str]:
    """Ack immediately (Strava requires <2s); process in the background.

    Errors are swallowed here on purpose — Strava does not retry on 200, and
    we never want a transient DB hiccup to make Strava disable the
    subscription after repeated non-2xx responses.
    """
    _require_strava_enabled()
    import threading

    def _run() -> None:
        try:
            from garmin_sync.strava_webhook import handle_event

            handle_event(payload)
        except Exception:
            log.exception("Strava webhook event processing failed: %s", payload)

    threading.Thread(target=_run, name="strava-webhook-event", daemon=True).start()
    return {"status": "received"}


@router.post("/garmin/profile-sync")
async def garmin_profile_sync(
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    """Pull FTP/VMA/FCmax from Garmin and upsert into athlete_profiles.

    Called by the wizard step Perf (first arrival only) and by the manual
    'Sync Garmin' button on /profile. Idempotent — safe to call repeatedly.
    """
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.profile_sync import sync_garmin_profile

        return sync_garmin_profile(user_id)
    except Exception as e:
        return report_endpoint_error(e, endpoint="garmin_profile_sync", user_id=user_id)


@router.post("/coach/generate-plan")
async def coach_generate_plan(
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    """Generate or regenerate a Banister training plan for the calling user."""
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.coach.planner import generate_plan

        return generate_plan(user_id)
    except Exception as e:
        return report_endpoint_error(e, endpoint="coach_generate_plan", user_id=user_id)


@router.post("/coach/discipline-levels")
async def coach_discipline_levels(
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    """Return declared vs history-adjusted level per discipline for the user."""
    user_id = _require_user_jwt(authorization)
    try:
        from datetime import date
        from typing import cast

        from garmin_sync.coach.discipline_level import compute_discipline_levels
        from garmin_sync.coach.planner import _load_today_banister_state

        db = get_admin_client()
        profile: dict[str, Any] = (
            cast(
                "dict[str, Any]",
                db.table("athlete_profiles")
                .select("sports_strengths")
                .eq("user_id", user_id)
                .single()
                .execute()
                .data,
            )
            or {}
        )
        today = date.today()
        _tss, _state, _review, activities = _load_today_banister_state(
            db=db, user_id=user_id, profile=profile, today=today
        )
        declared: dict[str, int] = profile.get("sports_strengths") or {
            "swim": 3,
            "bike": 3,
            "run": 3,
        }
        return compute_discipline_levels(declared, activities, today=today).to_dict()
    except Exception as e:
        return report_endpoint_error(e, endpoint="coach_discipline_levels", user_id=user_id)


class EnsureSessionsRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=30)


@router.post("/coach/ensure-sessions")
async def coach_ensure_sessions(
    body: EnsureSessionsRequest,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    """Generate workout structures for planned_sessions where workout IS NULL.

    Covers period [today, today+days]. Rate-limited per user.
    """
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.coach.rate_limit import ENSURE_SESSIONS, RateLimited, check_or_raise
        from garmin_sync.coach.sessions import ensure_sessions

        try:
            check_or_raise(user_id=user_id, limit=ENSURE_SESSIONS)
        except RateLimited:
            return {"status": "rate_limited", "retry_after_seconds": 60}
        return ensure_sessions(user_id=user_id, days=body.days)
    except Exception as e:
        return report_endpoint_error(e, endpoint="coach_ensure_sessions", user_id=user_id)


@router.post("/coach/daily-briefing")
async def coach_daily_briefing(
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    """Compute the readiness briefing for today and return adjusted session if needed."""
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.coach.briefing import (
            compute_and_cache_daily_briefing,
            get_cached_daily_briefing,
        )
        from garmin_sync.coach.rate_limit import DAILY_BRIEFING, RateLimited, check_or_raise

        cached = get_cached_daily_briefing(user_id=user_id)
        if cached is not None:
            return cached

        try:
            check_or_raise(user_id=user_id, limit=DAILY_BRIEFING)
        except RateLimited:
            return {"status": "rate_limited", "retry_after_seconds": 60}
        return compute_and_cache_daily_briefing(user_id=user_id)
    except Exception as e:
        return report_endpoint_error(e, endpoint="coach_daily_briefing", user_id=user_id)


@router.post("/coach/regenerate-session/{session_id}")
async def coach_regenerate_session(
    session_id: str,
    authorization: _AuthHeader = None,
) -> dict[str, Any]:
    """Force regenerate a workout for one session (user-triggered). Rate-limited."""
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.coach.rate_limit import REGENERATE_SESSION, RateLimited, check_or_raise
        from garmin_sync.coach.sessions import SessionNotFound, regenerate_session

        try:
            check_or_raise(user_id=user_id, limit=REGENERATE_SESSION)
        except RateLimited:
            return {"status": "rate_limited", "retry_after_seconds": 600}
        return regenerate_session(user_id=user_id, session_id=session_id)
    except SessionNotFound:
        return {"status": "session_not_found"}
    except Exception as e:
        return report_endpoint_error(
            e, endpoint="coach_regenerate_session", user_id=user_id, session_id=session_id
        )


app = create_app()
