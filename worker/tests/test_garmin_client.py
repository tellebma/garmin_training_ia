"""Tests for the Garmin client wrapper — happy path + MFA + auth failure."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.garmin_client import (
    GarminAuthError,
    GarminMFARequired,
    login_with_credentials,
    login_with_tokens,
    submit_mfa_code,
)


@pytest.fixture
def fake_garmin() -> Iterator[MagicMock]:
    with patch("garmin_sync.garmin_client.Garmin") as cls:
        yield cls


def test_login_with_credentials_no_mfa_returns_token_dict(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    instance.login.return_value = (None, None)  # no MFA
    instance.garth.dumps.return_value = '{"oauth_token": "abc"}'

    tokens = login_with_credentials("user@example.com", "pwd")

    assert tokens == '{"oauth_token": "abc"}'
    fake_garmin.assert_called_once_with(email="user@example.com", password="pwd", is_cn=False)
    instance.login.assert_called_once_with()


def test_login_with_credentials_mfa_required_raises(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    instance.login.return_value = ("needs_mfa", instance)  # tuple shape signals MFA

    with pytest.raises(GarminMFARequired) as exc:
        login_with_credentials("user@example.com", "pwd")
    assert exc.value.challenge is not None  # opaque continuation object


def test_submit_mfa_code_completes_login(fake_garmin: MagicMock) -> None:
    challenge = MagicMock()
    challenge.resume_login.return_value = None
    challenge.garth.dumps.return_value = '{"oauth_token": "xyz"}'

    tokens = submit_mfa_code(challenge, "123456")

    assert tokens == '{"oauth_token": "xyz"}'
    challenge.resume_login.assert_called_once_with("123456")


def test_login_with_tokens_restores_session(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    client = login_with_tokens('{"oauth_token": "abc"}')
    assert client is instance
    instance.garth.loads.assert_called_once_with('{"oauth_token": "abc"}')
    instance.login.assert_called_once_with()  # confirms session validity


def test_login_with_credentials_invalid_creds_raises(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    # python-garminconnect raises GarminConnectAuthenticationError on bad creds;
    # we wrap it in our own GarminAuthError.
    from garminconnect import GarminConnectAuthenticationError
    instance.login.side_effect = GarminConnectAuthenticationError("nope")

    with pytest.raises(GarminAuthError):
        login_with_credentials("user@example.com", "pwd")


def test_get_activities_calls_lib(fake_garmin: MagicMock) -> None:
    instance = fake_garmin.return_value
    instance.get_activities_by_date.return_value = [{"activityId": 1}]
    client = login_with_tokens("{}")
    result: list[dict[str, Any]] = client.get_activities_by_date("2026-01-01", "2026-01-31")
    assert result == [{"activityId": 1}]
