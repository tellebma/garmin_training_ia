"""Tests for FastAPI HTTP endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
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


def test_cors_denies_cross_origin_request(client: ASGITestClient) -> None:
    """SEC-2: no browser origin is ever legitimate for this worker. A simple
    cross-origin GET must not come back with an Access-Control-Allow-Origin
    header — otherwise a browser would treat the response as readable."""
    r = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


def test_cors_denies_preflight_request(client: ASGITestClient) -> None:
    """A CORS preflight for a cross-origin POST must not be granted."""
    transport_kwargs = {
        "headers": {
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        }
    }
    r = asyncio.run(client._request("OPTIONS", "/sync/u1", **transport_kwargs))
    assert "access-control-allow-origin" not in r.headers


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
@patch("garmin_sync.coach.briefing.get_cached_daily_briefing")
@patch("garmin_sync.coach.briefing.compute_and_cache_daily_briefing")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_daily_briefing_endpoint_ok(mock_jwt, mock_compute_cache, mock_cached, mock_rl):
    mock_jwt.return_value = "user-1"
    mock_cached.return_value = None
    mock_compute_cache.return_value = {
        "date": "2026-05-20",
        "readiness_score": 55,
        "status": "caution",
        "explanation_md": "Quelques signes de fatigue.",
        "factors": [{"name": "hrv_low", "impact": -10, "explanation": "HRV bas"}],
        "planned_session": {"sport": "run", "session_type": "intervals"},
        "suggested_session": {"sport": "run", "session_type": "threshold", "note": "ok"},
        "activity_review": {"lookback_days": 90, "insights": []},
        "last_session_feedback": None,
        "coach_recommendation": {
            "action": "ease",
            "title": "Séance allégée",
            "rationale": "ok",
            "instruction": "Z2 facile.",
        },
    }
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post("/coach/daily-briefing", headers={"Authorization": "Bearer fake.jwt"})
    assert r.status_code == 200
    body = r.json()
    assert body["readiness_score"] == 55
    assert body["status"] == "caution"
    assert body["suggested_session"]["session_type"] == "threshold"
    mock_cached.assert_called_once_with(user_id="user-1")
    mock_rl.assert_called_once()
    mock_compute_cache.assert_called_once_with(user_id="user-1")


@patch("garmin_sync.coach.rate_limit.check_or_raise")
@patch("garmin_sync.coach.briefing.get_cached_daily_briefing")
@patch("garmin_sync.coach.briefing.compute_and_cache_daily_briefing")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_daily_briefing_endpoint_returns_cache_without_rate_limit(
    mock_jwt, mock_compute_cache, mock_cached, mock_rl
):
    mock_jwt.return_value = "user-1"
    mock_cached.return_value = {
        "date": "2026-05-20",
        "readiness_score": 80,
        "status": "ready",
        "explanation_md": "Bonne disponibilité.",
        "factors": [],
        "planned_session": None,
        "suggested_session": None,
        "activity_review": {"lookback_days": 90, "insights": []},
        "last_session_feedback": None,
        "coach_recommendation": {
            "action": "maintain",
            "title": "Séance maintenue",
            "rationale": "ok",
            "instruction": "Reste facile.",
        },
    }
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post("/coach/daily-briefing", headers={"Authorization": "Bearer fake.jwt"})

    assert r.status_code == 200
    assert r.json()["readiness_score"] == 80
    mock_rl.assert_not_called()
    mock_compute_cache.assert_not_called()


@patch("garmin_sync.coach.rate_limit.check_or_raise")
@patch("garmin_sync.coach.briefing.get_cached_daily_briefing")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_daily_briefing_returns_rate_limited(mock_jwt, mock_cached, mock_rl):
    from garmin_sync.coach.rate_limit import RateLimited

    mock_jwt.return_value = "user-1"
    mock_cached.return_value = None
    mock_rl.side_effect = RateLimited("too many")
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post("/coach/daily-briefing", headers={"Authorization": "Bearer fake.jwt"})
    assert r.status_code == 200
    assert r.json()["status"] == "rate_limited"


@patch("garmin_sync.coach.discipline_level.compute_discipline_levels")
@patch("garmin_sync.coach.planner._load_today_banister_state")
@patch("garmin_sync.main.get_admin_client")
@patch("garmin_sync.main.verify_supabase_jwt")
def test_discipline_levels_endpoint_ok(mock_jwt, mock_db, mock_state, mock_compute):
    from garmin_sync.coach.discipline_level import DisciplineLevel, DisciplineLevels

    mock_jwt.return_value = "user-1"
    mock_db.return_value.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {  # noqa: E501
        "sports_strengths": {"swim": 2, "bike": 3, "run": 4}
    }
    mock_state.return_value = ({}, None, None, [])
    mock_compute.return_value = DisciplineLevels(
        disciplines={
            "bike": DisciplineLevel(
                3, 4, 1, "high", "Vélo remonté à 4 : ...", {"activities_90d": 22}
            ),
        }
    )
    client = ASGITestClient(__import__("garmin_sync.main", fromlist=["app"]).app)
    r = client.post("/coach/discipline-levels", headers={"Authorization": "Bearer fake.jwt"})
    assert r.status_code == 200
    body = r.json()
    assert body["disciplines"]["bike"]["effective"] == 4


def test_discipline_levels_requires_jwt():
    from garmin_sync.main import app

    r = ASGITestClient(app).post("/coach/discipline-levels")
    assert r.status_code == 401


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


def test_garmin_sync_endpoint_requires_jwt(client: ASGITestClient) -> None:
    r = client.post("/garmin/sync?trigger=manual")
    assert r.status_code == 401


def test_garmin_sync_invalid_trigger(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")
    r = client.post("/garmin/sync?trigger=weekly", headers={"Authorization": "Bearer x"})
    assert r.status_code == 400


def test_garmin_sync_cooldown(client: ASGITestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")
    monkeypatch.setattr(
        "garmin_sync.ondemand_sync.run_ondemand_sync",
        lambda user_id, trigger: {"status": "cooldown", "retry_after_seconds": 99},
    )
    r = client.post("/garmin/sync?trigger=auto", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json() == {"status": "cooldown", "retry_after_seconds": 99}


def test_garmin_sync_catches_unexpected(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")

    def _boom(user_id: str, trigger: str) -> dict[str, Any]:
        raise RuntimeError("db down")

    monkeypatch.setattr("garmin_sync.ondemand_sync.run_ondemand_sync", _boom)
    r = client.post("/garmin/sync?trigger=manual", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json()["status"] == "unexpected_error"
    assert r.json()["error_id"]


def test_garmin_sync_started(client: ASGITestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")
    seen: dict[str, str] = {}

    def _run(user_id: str, trigger: str) -> dict[str, str]:
        seen["user_id"] = user_id
        seen["trigger"] = trigger
        return {"status": "started"}

    monkeypatch.setattr("garmin_sync.ondemand_sync.run_ondemand_sync", _run)
    r = client.post("/garmin/sync?trigger=manual", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json() == {"status": "started"}
    assert seen == {"user_id": "u1", "trigger": "manual"}


def test_strava_connect_requires_jwt(client: ASGITestClient) -> None:
    r = client.post("/strava/connect", json={"code": "abc"})
    assert r.status_code == 401


def test_strava_connect_returns_worker_status(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")
    monkeypatch.setattr(
        "garmin_sync.strava_connect.start_connect_flow",
        lambda *, user_id, code: {"status": "connected"},
    )

    r = client.post("/strava/connect", json={"code": "abc"}, headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json() == {"status": "connected"}


def test_strava_disconnect_requires_jwt(client: ASGITestClient) -> None:
    r = client.post("/strava/disconnect")
    assert r.status_code == 401


def test_strava_disconnect_returns_worker_status(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from garmin_sync import main as main_mod

    monkeypatch.setattr(main_mod, "verify_supabase_jwt", lambda _t: "u1")
    monkeypatch.setattr(
        "garmin_sync.strava_connect.disconnect", lambda *, user_id: {"status": "disconnected"}
    )

    r = client.post("/strava/disconnect", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json() == {"status": "disconnected"}


def test_strava_webhook_get_echoes_challenge(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "garmin_sync.strava_webhook.verify_challenge",
        lambda *, mode, token, challenge: challenge,
    )

    r = client.get(
        "/strava/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "t", "hub.challenge": "xyz"},
    )
    assert r.status_code == 200
    assert r.json() == {"hub.challenge": "xyz"}


def test_strava_webhook_get_rejects_bad_token(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "garmin_sync.strava_webhook.verify_challenge",
        lambda *, mode, token, challenge: None,
    )

    r = client.get(
        "/strava/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "xyz"},
    )
    assert r.status_code == 403


def test_strava_webhook_post_dispatches_event(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    received = []
    monkeypatch.setattr(
        "garmin_sync.strava_webhook.handle_event",
        lambda payload: received.append(payload) or {"status": "stored"},
    )

    r = client.post(
        "/strava/webhook",
        json={"object_type": "activity", "aspect_type": "create", "object_id": 1, "owner_id": 2},
    )
    assert r.status_code == 200
    assert r.json() == {"status": "received"}
    assert received == [
        {"object_type": "activity", "aspect_type": "create", "object_id": 1, "owner_id": 2}
    ]


@pytest.fixture
def _strava_disabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run the app as a deployment with no Strava secrets at all.

    ``get_settings`` is ``lru_cache``d, so the cache has to be dropped on both
    sides — otherwise the settings another test warmed up leak in here, and the
    ones built here leak back out.
    """
    from garmin_sync.config import get_settings

    monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
    monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("STRAVA_WEBHOOK_VERIFY_TOKEN", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.usefixtures("_strava_disabled")
def test_strava_routes_404_when_integration_not_configured(client: ASGITestClient) -> None:
    """Strava paused: with no secrets configured, the whole surface must be gone.

    ``POST /strava/webhook`` is unauthenticated by design, so leaving it live on
    a deployment without Strava lets anyone spawn daemon threads and delete
    ``athlete_strava_credentials`` rows with a forged deauthorization event.
    """
    assert client.post("/strava/connect", json={"code": "abc"}).status_code == 404
    assert client.post("/strava/disconnect").status_code == 404
    assert (
        client.get(
            "/strava/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "t", "hub.challenge": "xyz"},
        ).status_code
        == 404
    )
    assert client.post("/strava/webhook", json={"object_type": "activity"}).status_code == 404


@pytest.mark.usefixtures("_strava_disabled")
def test_strava_webhook_does_not_dispatch_when_disabled(
    client: ASGITestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 404 must happen before the background thread is spawned."""
    received = []
    monkeypatch.setattr(
        "garmin_sync.strava_webhook.handle_event",
        lambda payload: received.append(payload) or {"status": "stored"},
    )

    r = client.post(
        "/strava/webhook",
        json={"object_type": "athlete", "owner_id": 2, "updates": {"authorized": "false"}},
    )

    assert r.status_code == 404
    assert received == []


@pytest.mark.usefixtures("_strava_disabled")
def test_garmin_routes_unaffected_when_strava_disabled(client: ASGITestClient) -> None:
    """Gating Strava must not take Garmin down with it."""
    assert client.get("/health").status_code == 200
    # 401 (not 404): the route still exists, it just needs a JWT.
    r = client.post("/garmin/connect", json={"email": "a@b.c", "password": "x"})
    assert r.status_code == 401
