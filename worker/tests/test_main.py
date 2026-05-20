"""Tests for FastAPI HTTP endpoints."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Iterator[TestClient]:
    from garmin_sync.main import app

    yield TestClient(app)  # noqa: PT022


def test_health_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_sync_endpoint_requires_shared_token(client: TestClient) -> None:
    r = client.post("/sync/u1", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_sync_endpoint_with_valid_token(client: TestClient) -> None:
    with patch("garmin_sync.main.run_sync_for_user") as fake:
        fake.return_value = {"activities": 5}
        r = client.post(
            "/sync/u1",
            headers={"Authorization": "Bearer shared-token-test"},
        )
    assert r.status_code == 200
    assert r.json() == {"activities": 5}
    fake.assert_called_once_with("u1", initial=False)


def test_garmin_connect_endpoint_requires_jwt(client: TestClient) -> None:
    r = client.post("/garmin/connect", json={"email": "a@b.c", "password": "p"})
    assert r.status_code == 401


def test_garmin_profile_sync_requires_jwt(client: TestClient) -> None:
    """No Authorization header → 401."""
    r = client.post("/garmin/profile-sync")
    assert r.status_code == 401


def test_garmin_profile_sync_returns_status_dict(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
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
    client: TestClient, monkeypatch: pytest.MonkeyPatch
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


def test_coach_generate_plan_requires_jwt(client: TestClient) -> None:
    r = client.post("/coach/generate-plan")
    assert r.status_code == 401


def test_coach_generate_plan_returns_status_dict(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
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
    client: TestClient, monkeypatch: pytest.MonkeyPatch
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
