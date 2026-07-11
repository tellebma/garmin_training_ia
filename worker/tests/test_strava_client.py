from __future__ import annotations

import httpx
import pytest

from garmin_sync.strava_client import (
    StravaAuthError,
    StravaError,
    StravaRateLimitError,
    deauthorize,
    exchange_code,
    get_activity,
    list_activities,
    refresh_access_token,
)


def _mock_transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_exchange_code_returns_tokens(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/oauth/token"
        body = dict(x.split("=") for x in request.content.decode().split("&"))
        assert body["code"] == "abc123"
        assert body["grant_type"] == "authorization_code"
        return httpx.Response(
            200,
            json={
                "access_token": "at",
                "refresh_token": "rt",
                "expires_at": 1234567890,
                "athlete": {"id": 999},
            },
        )

    monkeypatch.setattr("garmin_sync.strava_client._client", lambda: _mock_transport(handler))
    result = exchange_code("abc123")
    assert result == {
        "access_token": "at",
        "refresh_token": "rt",
        "expires_at": 1234567890,
        "athlete": {"id": 999},
    }


def test_exchange_code_raises_auth_error_on_400(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "bad code"})

    monkeypatch.setattr("garmin_sync.strava_client._client", lambda: _mock_transport(handler))
    with pytest.raises(StravaAuthError):
        exchange_code("bad-code")


def test_refresh_access_token_returns_new_tokens(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = dict(x.split("=") for x in request.content.decode().split("&"))
        assert body["grant_type"] == "refresh_token"
        assert body["refresh_token"] == "old-rt"
        return httpx.Response(
            200, json={"access_token": "new-at", "refresh_token": "new-rt", "expires_at": 2}
        )

    monkeypatch.setattr("garmin_sync.strava_client._client", lambda: _mock_transport(handler))
    result = refresh_access_token("old-rt")
    assert result["access_token"] == "new-at"


def test_get_activity_returns_payload(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/activities/555"
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"id": 555, "type": "Run"})

    monkeypatch.setattr("garmin_sync.strava_client._client", lambda: _mock_transport(handler))
    result = get_activity("tok", 555)
    assert result == {"id": 555, "type": "Run"}


def test_get_activity_raises_rate_limit_on_429(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limit exceeded"})

    monkeypatch.setattr("garmin_sync.strava_client._client", lambda: _mock_transport(handler))
    with pytest.raises(StravaRateLimitError):
        get_activity("tok", 555)


def test_list_activities_passes_pagination_params(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[{"id": 1}, {"id": 2}])

    monkeypatch.setattr("garmin_sync.strava_client._client", lambda: _mock_transport(handler))
    result = list_activities("tok", after_epoch=1000, page=2, per_page=50)
    assert result == [{"id": 1}, {"id": 2}]
    assert captured["params"] == {"after": "1000", "page": "2", "per_page": "50"}


def test_deauthorize_raises_on_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    monkeypatch.setattr("garmin_sync.strava_client._client", lambda: _mock_transport(handler))
    with pytest.raises(StravaError):
        deauthorize("tok")


def test_deauthorize_sends_token_in_body_not_url(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "access_token" not in dict(request.url.params)
        body = dict(x.split("=") for x in request.content.decode().split("&"))
        assert body["access_token"] == "secret-tok"
        return httpx.Response(200, json={})

    monkeypatch.setattr("garmin_sync.strava_client._client", lambda: _mock_transport(handler))
    deauthorize("secret-tok")
