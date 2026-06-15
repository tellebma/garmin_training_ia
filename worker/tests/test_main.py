"""Tests for FastAPI HTTP endpoints."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI


class ASGITestClient:
    """Small sync wrapper around httpx.ASGITransport.

    FastAPI's TestClient currently hangs in this dependency set when dispatching
    requests. ASGITransport exercises the same app routes without Starlette's
    blocking test portal.
    """

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def get(self, path: str, **kwargs: object) -> httpx.Response:
        return asyncio.run(self._request("GET", path, **kwargs))

    def post(self, path: str, **kwargs: object) -> httpx.Response:
        return asyncio.run(self._request("POST", path, **kwargs))

    async def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)


@pytest.fixture
def client() -> ASGITestClient:
    from garmin_sync.main import app

    return ASGITestClient(app)


def test_health_ok(client: ASGITestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_app_can_disable_scheduler_lifespan() -> None:
    from garmin_sync.main import create_app

    with (
        patch("garmin_sync.scheduler.init_scheduler") as init_scheduler,
        patch("garmin_sync.scheduler.shutdown_scheduler") as shutdown_scheduler,
    ):
        r = ASGITestClient(create_app(enable_scheduler=False)).get("/health")

    assert r.status_code == 200
    init_scheduler.assert_not_called()
    shutdown_scheduler.assert_not_called()


def test_create_app_can_enable_scheduler_lifespan() -> None:
    from garmin_sync.main import create_app

    async def run_lifespan(app: FastAPI) -> None:
        async with app.router.lifespan_context(app):
            pass

    with (
        patch("garmin_sync.scheduler.init_scheduler") as init_scheduler,
        patch("garmin_sync.scheduler.shutdown_scheduler") as shutdown_scheduler,
    ):
        asyncio.run(run_lifespan(create_app(enable_scheduler=True)))

    init_scheduler.assert_called_once()
    shutdown_scheduler.assert_called_once()


def test_sync_endpoint_requires_shared_token(client: ASGITestClient) -> None:
    r = client.post("/sync/u1", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_sync_endpoint_with_valid_token(client: ASGITestClient) -> None:
    with patch("garmin_sync.main.run_sync_for_user") as fake:
        fake.return_value = {"activities": 5}
        r = client.post(
            "/sync/u1",
            headers={"Authorization": "Bearer shared-token-test"},
        )
    assert r.status_code == 200
    assert r.json() == {"activities": 5}
    fake.assert_called_once_with("u1", initial=False)


def test_garmin_connect_endpoint_requires_jwt(client: ASGITestClient) -> None:
    r = client.post("/garmin/connect", json={"email": "a@b.c", "password": "p"})
    assert r.status_code == 401


def test_garmin_profile_sync_requires_jwt(client: ASGITestClient) -> None:
    """No Authorization header → 401."""
    r = client.post("/garmin/profile-sync")
    assert r.status_code == 401


def test_garmin_profile_sync_returns_status_dict(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")

    def fake_sync(user_id: str) -> dict:
        assert user_id == "u1"
        return {"status": "ok", "fetched": {"ftp_watts": 245}}

    monkeypatch.setattr("garmin_sync.profile_sync.sync_garmin_profile", fake_sync)

    r = client.post("/garmin/profile-sync", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "fetched": {"ftp_watts": 245}}


def test_garmin_profile_sync_catches_unexpected(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")
    monkeypatch.setattr(
        "garmin_sync.profile_sync.sync_garmin_profile",
        lambda _u: (_ for _ in ()).throw(RuntimeError("kaboom")),
    )

    r = client.post("/garmin/profile-sync", headers={"Authorization": "Bearer x"})
    body = r.json()
    assert body["status"] == "unexpected_error"
    assert body["type"] == "RuntimeError"
    assert "error_id" in body
    assert "detail" not in body
    assert "traceback" not in body


def test_coach_generate_plan_requires_jwt(client: ASGITestClient) -> None:
    r = client.post("/coach/generate-plan")
    assert r.status_code == 401


def test_coach_generate_plan_returns_status_dict(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")

    def fake(user_id: str) -> dict:
        return {"status": "ok", "plan_id": "p1", "weeks_count": 8, "sessions_count": 56}

    monkeypatch.setattr("garmin_sync.coach.planner.generate_plan", fake)
    r = client.post("/coach/generate-plan", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["sessions_count"] == 56


def test_coach_generate_plan_catches_unexpected(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")

    monkeypatch.setattr(
        "garmin_sync.coach.planner.generate_plan",
        lambda _u: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    r = client.post("/coach/generate-plan", headers={"Authorization": "Bearer x"})
    body = r.json()
    assert body["status"] == "unexpected_error"
    assert body["type"] == "RuntimeError"


@patch("garmin_sync.coach.rate_limit.check_or_raise")
@patch("garmin_sync.coach.sessions.ensure_sessions")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_ensure_sessions_endpoint_ok(mock_jwt, mock_ensure, mock_rl):
    mock_jwt.return_value = "user-1"
    mock_ensure.return_value = {"generated_count": 3, "failed_count": 0, "skipped_count": 0}
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post(
        "/coach/ensure-sessions",
        json={"days": 7},
        headers={"Authorization": "Bearer fake.jwt"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["generated_count"] == 3
    mock_ensure.assert_called_once_with(user_id="user-1", days=7)
    mock_rl.assert_called_once()


@patch("garmin_sync.coach.rate_limit.check_or_raise")
@patch("garmin_sync.coach.sessions.ensure_sessions")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_ensure_sessions_default_days(mock_jwt, mock_ensure, mock_rl):
    mock_jwt.return_value = "user-1"
    mock_ensure.return_value = {"generated_count": 0, "failed_count": 0, "skipped_count": 0}
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post("/coach/ensure-sessions", json={}, headers={"Authorization": "Bearer fake.jwt"})
    assert r.status_code == 200
    mock_ensure.assert_called_once_with(user_id="user-1", days=7)


@patch("garmin_sync.main.verify_supabase_jwt")
def test_ensure_sessions_rejects_days_out_of_bounds(mock_jwt):
    mock_jwt.return_value = "user-1"
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    # days=0 rejected (ge=1)
    r1 = client.post(
        "/coach/ensure-sessions",
        json={"days": 0},
        headers={"Authorization": "Bearer fake.jwt"},
    )
    assert r1.status_code == 422
    # days=100 rejected (le=30) — prevents DoS by forcing a huge planned_sessions scan
    r2 = client.post(
        "/coach/ensure-sessions",
        json={"days": 100},
        headers={"Authorization": "Bearer fake.jwt"},
    )
    assert r2.status_code == 422


@patch("garmin_sync.coach.rate_limit.check_or_raise")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_ensure_sessions_returns_rate_limited_status(mock_jwt, mock_rl):
    from garmin_sync.coach.rate_limit import RateLimited

    mock_jwt.return_value = "user-1"
    mock_rl.side_effect = RateLimited("too many calls")
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post(
        "/coach/ensure-sessions",
        json={"days": 7},
        headers={"Authorization": "Bearer fake.jwt"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rate_limited"
    assert body["retry_after_seconds"] >= 1


@patch("garmin_sync.coach.rate_limit.check_or_raise")
@patch("garmin_sync.coach.sessions.regenerate_session")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_regenerate_session_endpoint_ok(mock_jwt, mock_regen, mock_rl):
    mock_jwt.return_value = "user-1"
    mock_regen.return_value = {"status": "ok", "workout": {"summary_md": "x"}}
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post(
        "/coach/regenerate-session/sess-1",
        headers={"Authorization": "Bearer fake.jwt"},
    )
    assert r.status_code == 200
    mock_regen.assert_called_once_with(user_id="user-1", session_id="sess-1")
    mock_rl.assert_called_once()


@patch("garmin_sync.coach.rate_limit.check_or_raise")
@patch("garmin_sync.coach.sessions.regenerate_session")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_regenerate_session_not_found(mock_jwt, mock_regen, mock_rl):
    from garmin_sync.coach.sessions import SessionNotFound

    mock_jwt.return_value = "user-1"
    mock_regen.side_effect = SessionNotFound("nope")
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post(
        "/coach/regenerate-session/sess-1",
        headers={"Authorization": "Bearer fake.jwt"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "session_not_found"


@patch("garmin_sync.coach.rate_limit.check_or_raise")
@patch("garmin_sync.coach.briefing.compute_briefing")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_daily_briefing_endpoint_ok(mock_jwt, mock_compute, mock_rl):
    from garmin_sync.coach.activity_review import build_activity_review
    from garmin_sync.coach.briefing import (
        CoachRecommendation,
        DailyBriefing,
        ReadinessFactor,
        SuggestedSession,
    )

    mock_jwt.return_value = "user-1"
    mock_compute.return_value = DailyBriefing(
        date="2026-05-20",
        readiness_score=55,
        status="caution",
        explanation_md="Quelques signes de fatigue.",
        factors=[ReadinessFactor("hrv_low", -10, "HRV bas")],
        planned_session={"sport": "run", "session_type": "intervals"},
        suggested_session=SuggestedSession(sport="run", session_type="threshold", note="ok"),
        activity_review=build_activity_review([]),
        last_session_feedback=None,
        coach_recommendation=CoachRecommendation(
            action="ease",
            title="Séance allégée",
            rationale="ok",
            instruction="Z2 facile.",
        ),
    )
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post("/coach/daily-briefing", headers={"Authorization": "Bearer fake.jwt"})
    assert r.status_code == 200
    body = r.json()
    assert body["readiness_score"] == 55
    assert body["status"] == "caution"
    assert body["suggested_session"]["session_type"] == "threshold"
    mock_rl.assert_called_once()


@patch("garmin_sync.coach.rate_limit.check_or_raise")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_daily_briefing_returns_rate_limited(mock_jwt, mock_rl):
    from garmin_sync.coach.rate_limit import RateLimited

    mock_jwt.return_value = "user-1"
    mock_rl.side_effect = RateLimited("too many")
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post("/coach/daily-briefing", headers={"Authorization": "Bearer fake.jwt"})
    assert r.status_code == 200
    assert r.json()["status"] == "rate_limited"


@patch("garmin_sync.coach.rate_limit.check_or_raise")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_regenerate_session_returns_rate_limited_status(mock_jwt, mock_rl):
    from garmin_sync.coach.rate_limit import RateLimited

    mock_jwt.return_value = "user-1"
    mock_rl.side_effect = RateLimited("too many calls")
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post(
        "/coach/regenerate-session/sess-1",
        headers={"Authorization": "Bearer fake.jwt"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rate_limited"
