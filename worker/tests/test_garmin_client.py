"""Tests for the Garmin client wrapper — happy path + MFA + auth failure
+ rate-limit detection (both raised and silent-failure shapes)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.garmin_client import (
    GarminAuthError,
    GarminMFARequired,
    GarminRateLimitError,
    login_with_credentials,
    login_with_tokens,
    submit_mfa_code,
)


@pytest.fixture
def fake_garmin() -> Iterator[MagicMock]:
    with patch("garmin_sync.garmin_client.Garmin") as cls:
        # Default: the inner ``client`` looks authenticated so _serialize_session
        # is happy. Individual tests override this when they need to simulate
        # a silent-429.
        cls.return_value.client.is_authenticated = True
        yield cls


def test_login_with_credentials_no_mfa_returns_token_dict(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    instance.login.return_value = (None, None)  # no MFA
    instance.client.is_authenticated = True
    instance.client.dumps.return_value = '{"di_token": "abc"}'

    tokens = login_with_credentials("user@example.com", "pwd")

    assert tokens == '{"di_token": "abc"}'
    fake_garmin.assert_called_once_with(
        email="user@example.com",
        password="pwd",
        is_cn=False,
        return_on_mfa=True,
    )
    instance.login.assert_called_once_with()
    instance.client.dumps.assert_called_once_with()


def test_login_with_credentials_mfa_required_raises(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    instance.login.return_value = ("needs_mfa", None)

    with pytest.raises(GarminMFARequired) as exc:
        login_with_credentials("user@example.com", "pwd")
    # The challenge carries the Garmin instance so we can resume on it later.
    assert exc.value.challenge is instance


def test_submit_mfa_code_completes_login(fake_garmin: MagicMock) -> None:
    challenge = MagicMock()
    challenge.resume_login.return_value = (None, None)
    challenge.client.is_authenticated = True
    challenge.client.dumps.return_value = '{"di_token": "xyz"}'

    tokens = submit_mfa_code(challenge, "123456")

    assert tokens == '{"di_token": "xyz"}'
    challenge.resume_login.assert_called_once_with({}, "123456")


def test_login_with_tokens_restores_session(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    client = login_with_tokens('{"di_token": "abc"}')
    assert client is instance
    instance.client.loads.assert_called_once_with('{"di_token": "abc"}')


def test_login_with_credentials_invalid_creds_raises(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    # python-garminconnect raises GarminConnectAuthenticationError on bad creds;
    # we wrap it in our own GarminAuthError.
    from garminconnect import GarminConnectAuthenticationError

    instance.login.side_effect = GarminConnectAuthenticationError("nope")

    with pytest.raises(GarminAuthError):
        login_with_credentials("user@example.com", "pwd")


def test_login_with_credentials_explicit_429_raises_rate_limit(
    fake_garmin: MagicMock,
) -> None:
    """All login strategies 429'd → library raises GarminConnectTooManyRequestsError."""
    from garminconnect import GarminConnectTooManyRequestsError

    instance = fake_garmin.return_value
    instance.login.side_effect = GarminConnectTooManyRequestsError(
        "All login strategies rate limited (429)."
    )

    with pytest.raises(GarminRateLimitError):
        login_with_credentials("user@example.com", "pwd")


def test_login_with_credentials_429_buried_in_connection_error(
    fake_garmin: MagicMock,
) -> None:
    """Mixed failure — library raises GarminConnectConnectionError whose
    message contains "429". We classify that as a rate limit too."""
    from garminconnect import GarminConnectConnectionError

    instance = fake_garmin.return_value
    instance.login.side_effect = GarminConnectConnectionError(
        "All login strategies exhausted: Mobile login returned 429 — IP rate limited"
    )

    with pytest.raises(GarminRateLimitError):
        login_with_credentials("user@example.com", "pwd")


def test_login_with_credentials_silent_failure_raises_rate_limit(
    fake_garmin: MagicMock,
) -> None:
    """Reproduces the production crash: login() returned (None, None) but the
    inner client never got an auth token (silent-429 / cloudflare). We must
    detect that and raise GarminRateLimitError instead of crashing on
    ``client.client.dumps()`` of an empty token bundle."""
    instance = fake_garmin.return_value
    instance.login.return_value = (None, None)  # looks like success
    instance.client.is_authenticated = False  # ...but no token actually set

    with pytest.raises(GarminRateLimitError):
        login_with_credentials("user@example.com", "pwd")


def test_get_activities_calls_lib(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    instance.get_activities_by_date.return_value = [{"activityId": 1}]
    client = login_with_tokens("{}")
    result: list[dict[str, Any]] = client.get_activities_by_date("2026-01-01", "2026-01-31")
    assert result == [{"activityId": 1}]
