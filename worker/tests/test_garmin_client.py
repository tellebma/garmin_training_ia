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


def test_login_with_credentials_generic_connection_error_raises_garmin_error(
    fake_garmin: MagicMock,
) -> None:
    """A GarminConnectConnectionError without "429" in the message must be
    wrapped as a generic GarminError, not a rate-limit error.

    Covers lines 117-118 in garmin_client.py."""
    from garminconnect import GarminConnectConnectionError

    from garmin_sync.garmin_client import GarminError

    instance = fake_garmin.return_value
    instance.login.side_effect = GarminConnectConnectionError("DNS resolution failed")

    with pytest.raises(GarminError) as exc:
        login_with_credentials("user@example.com", "pwd")
    # Must NOT be the rate-limit subclass
    assert not isinstance(exc.value, GarminRateLimitError)


def test_submit_mfa_code_invalid_code_raises_auth_error(fake_garmin: MagicMock) -> None:
    """A bad MFA code → GarminConnectAuthenticationError → our GarminAuthError."""
    from garminconnect import GarminConnectAuthenticationError

    challenge = MagicMock()
    challenge.resume_login.side_effect = GarminConnectAuthenticationError("bad code")

    with pytest.raises(GarminAuthError):
        submit_mfa_code(challenge, "000000")


def test_submit_mfa_code_explicit_429_raises_rate_limit(fake_garmin: MagicMock) -> None:
    from garminconnect import GarminConnectTooManyRequestsError

    challenge = MagicMock()
    challenge.resume_login.side_effect = GarminConnectTooManyRequestsError("429")

    with pytest.raises(GarminRateLimitError):
        submit_mfa_code(challenge, "123456")


def test_submit_mfa_code_429_buried_in_connection_error(fake_garmin: MagicMock) -> None:
    """ConnectionError mentioning 429 must be classified as rate limit."""
    from garminconnect import GarminConnectConnectionError

    challenge = MagicMock()
    challenge.resume_login.side_effect = GarminConnectConnectionError("Mobile login returned 429")

    with pytest.raises(GarminRateLimitError):
        submit_mfa_code(challenge, "123456")


def test_submit_mfa_code_generic_connection_error_raises_garmin_error(
    fake_garmin: MagicMock,
) -> None:
    from garminconnect import GarminConnectConnectionError

    from garmin_sync.garmin_client import GarminError

    challenge = MagicMock()
    challenge.resume_login.side_effect = GarminConnectConnectionError("transient TLS issue")

    with pytest.raises(GarminError) as exc:
        submit_mfa_code(challenge, "123456")
    assert not isinstance(exc.value, GarminRateLimitError)


def test_login_with_tokens_invalid_session_raises_auth_error(fake_garmin: MagicMock) -> None:
    """If the persisted session JSON is missing required fields, the underlying
    library raises GarminConnectAuthenticationError. We surface that as
    GarminAuthError so the cron loop marks the credential row for refresh.

    Covers lines 162-164 in garmin_client.py."""
    from garminconnect import GarminConnectAuthenticationError

    instance = fake_garmin.return_value
    instance.client.loads.side_effect = GarminConnectAuthenticationError("missing token")

    with pytest.raises(GarminAuthError, match="expired"):
        login_with_tokens('{"di_token": null}')


def test_login_with_tokens_corrupt_json_raises_auth_error(fake_garmin: MagicMock) -> None:
    """The library wraps JSON parse errors in GarminConnectConnectionError.
    We surface those as GarminAuthError too (treat as 'session corrupted').

    Covers lines 165-168 in garmin_client.py."""
    from garminconnect import GarminConnectConnectionError

    instance = fake_garmin.return_value
    instance.client.loads.side_effect = GarminConnectConnectionError("invalid json")

    with pytest.raises(GarminAuthError, match="corrupted"):
        login_with_tokens("not-valid-json")


def test_submit_mfa_code_succeeds_returns_serialized_session(fake_garmin: MagicMock) -> None:
    """Happy-path coverage for the success branch after a clean resume."""
    challenge = MagicMock()
    challenge.resume_login.return_value = (None, None)
    challenge.client.is_authenticated = True
    challenge.client.dumps.return_value = '{"di_token": "fresh"}'

    tokens = submit_mfa_code(challenge, "654321")
    assert tokens == '{"di_token": "fresh"}'
