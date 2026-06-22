"""FastAPI HTTP entry point: health, manual sync, Garmin connect/MFA."""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from garmin_sync.auth import AuthError, verify_shared_token, verify_supabase_jwt
from garmin_sync.config import get_settings
from garmin_sync.cron import run_sync_for_user
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
    app_lifespan = scheduler_lifespan if enable_scheduler else None
    created = FastAPI(title="garmin-sync", version="0.1.0", lifespan=app_lifespan)
    created.include_router(router)
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


def _new_error_id() -> str:
    return uuid.uuid4().hex[:8]


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
        error_id = _new_error_id()
        log.exception("[%s] garmin_connect endpoint crashed for user=%s", error_id, user_id)
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }


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
        error_id = _new_error_id()
        log.exception("[%s] garmin_mfa endpoint crashed for user=%s", error_id, user_id)
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }


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
        error_id = _new_error_id()
        log.exception("[%s] garmin_profile_sync endpoint crashed for user=%s", error_id, user_id)
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }


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
        error_id = _new_error_id()
        log.exception("[%s] coach_generate_plan crashed for user=%s", error_id, user_id)
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }


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
        error_id = _new_error_id()
        log.exception(
            "[%s] coach_discipline_levels crashed for user=%s",
            error_id,
            user_id,
        )
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }


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
        error_id = _new_error_id()
        log.exception("[%s] coach_ensure_sessions crashed for user=%s", error_id, user_id)
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }


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
        error_id = _new_error_id()
        log.exception("[%s] coach_daily_briefing crashed for user=%s", error_id, user_id)
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }


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
        error_id = _new_error_id()
        log.exception(
            "[%s] coach_regenerate_session crashed for user=%s session=%s",
            error_id,
            user_id,
            session_id,
        )
        return {
            "status": "unexpected_error",
            "error_id": error_id,
            "type": type(e).__name__,
        }


app = create_app()
