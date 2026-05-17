"""FastAPI HTTP entry point: health, manual sync, Garmin connect/MFA."""

from __future__ import annotations

import logging
import sys
import traceback
from typing import Any

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from garmin_sync.auth import AuthError, verify_shared_token, verify_supabase_jwt
from garmin_sync.config import get_settings
from garmin_sync.cron import run_sync_for_user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)

log = logging.getLogger(__name__)
app = FastAPI(title="garmin-sync", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": get_settings().env}


def _require_shared_token(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    if not verify_shared_token(token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


def _require_user_jwt(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        return verify_supabase_jwt(token)
    except AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e


@app.post("/sync/{user_id}")
def sync_user(
    user_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_shared_token(authorization)
    return run_sync_for_user(user_id, initial=False)


class GarminConnectRequest(BaseModel):
    email: str
    password: str


class GarminMFARequest(BaseModel):
    challenge_id: str
    code: str


@app.post("/garmin/connect")
def garmin_connect(
    body: GarminConnectRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Initiate Garmin login. Called by Next.js Server Action on behalf of user."""
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.connect import start_connect_flow

        return start_connect_flow(user_id=user_id, email=body.email, password=body.password)
    except Exception as e:
        log.exception("garmin_connect endpoint crashed for user=%s", user_id)
        return {
            "status": "unexpected_error",
            "detail": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }


@app.post("/garmin/mfa")
def garmin_mfa(
    body: GarminMFARequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.connect import resume_connect_flow

        return resume_connect_flow(user_id=user_id, challenge_id=body.challenge_id, code=body.code)
    except Exception as e:
        log.exception("garmin_mfa endpoint crashed for user=%s", user_id)
        return {
            "status": "unexpected_error",
            "detail": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }
