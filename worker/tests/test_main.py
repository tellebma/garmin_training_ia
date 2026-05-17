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
