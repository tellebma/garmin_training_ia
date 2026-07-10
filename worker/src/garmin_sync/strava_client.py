"""Thin httpx wrapper over the Strava v3 API.

Only the calls this integration needs: OAuth code exchange/refresh, fetching
a single activity, listing an athlete's activities (backfill pagination),
and best-effort deauthorization on disconnect.
"""

from __future__ import annotations

from typing import Any, cast

import httpx

from garmin_sync.config import get_settings

_AUTH_BASE = "https://www.strava.com"
_API_BASE = "https://www.strava.com/api/v3"
_TIMEOUT_S = 15.0


class StravaError(Exception):
    """Generic Strava API error."""


class StravaAuthError(StravaError):
    """Strava rejected the code/token (400/401)."""


class StravaRateLimitError(StravaError):
    """Strava returned 429 — application-wide rate limit hit."""


def _client() -> httpx.Client:
    return httpx.Client(timeout=_TIMEOUT_S)


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 429:
        raise StravaRateLimitError(f"rate limited: {response.text[:500]}")
    if response.status_code in (400, 401):
        raise StravaAuthError(f"auth error {response.status_code}: {response.text[:500]}")
    if response.status_code >= 400:
        raise StravaError(f"HTTP {response.status_code}: {response.text[:500]}")


def exchange_code(code: str) -> dict[str, Any]:
    settings = get_settings()
    with _client() as client:
        response = client.post(
            f"{_AUTH_BASE}/oauth/token",
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret.get_secret_value(),
                "code": code,
                "grant_type": "authorization_code",
            },
        )
    _raise_for_status(response)
    return cast(dict[str, Any], response.json())


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    with _client() as client:
        response = client.post(
            f"{_AUTH_BASE}/oauth/token",
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret.get_secret_value(),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    _raise_for_status(response)
    return cast(dict[str, Any], response.json())


def get_activity(access_token: str, activity_id: int) -> dict[str, Any]:
    with _client() as client:
        response = client.get(
            f"{_API_BASE}/activities/{activity_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    _raise_for_status(response)
    return cast(dict[str, Any], response.json())


def list_activities(
    access_token: str, *, after_epoch: int, page: int, per_page: int = 100
) -> list[dict[str, Any]]:
    with _client() as client:
        response = client.get(
            f"{_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"after": after_epoch, "page": page, "per_page": per_page},
        )
    _raise_for_status(response)
    return cast(list[dict[str, Any]], response.json())


def deauthorize(access_token: str) -> None:
    with _client() as client:
        response = client.post(
            f"{_AUTH_BASE}/oauth/deauthorize",
            data={"access_token": access_token},
        )
    _raise_for_status(response)
