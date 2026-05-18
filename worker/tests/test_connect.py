"""Tests for the Garmin connect/MFA flow error handling."""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

_ERROR_ID_RE = re.compile(r"^[0-9a-f]{8}$")


@pytest.fixture(autouse=True)
def _reset_cooldowns() -> None:
    """Each test starts with an empty cooldown table."""
    from garmin_sync.connect import _cooldowns, _pending_mfa

    _cooldowns.clear()
    _pending_mfa.clear()


def test_start_connect_flow_returns_unexpected_error_on_internal_crash() -> None:
    """If something blows up unexpectedly inside the flow, return a structured
    error response (not raise) so the FastAPI handler stays at HTTP 200.

    Response must only expose `error_id` + `type` — no `detail`, no `traceback`,
    so we never leak Python stack info to the browser.
    """
    from garmin_sync.connect import start_connect_flow

    with patch("garmin_sync.connect.login_with_credentials") as fake_login:
        fake_login.side_effect = RuntimeError("kaboom")
        result = start_connect_flow(user_id="u1", email="a@b.c", password="p")

    assert result["status"] == "unexpected_error"
    assert _ERROR_ID_RE.match(result["error_id"])
    assert result["type"] == "RuntimeError"
    assert "detail" not in result
    assert "traceback" not in result


def test_start_connect_flow_returns_invalid_credentials() -> None:
    from garmin_sync.connect import start_connect_flow
    from garmin_sync.garmin_client import GarminAuthError

    with patch("garmin_sync.connect.login_with_credentials") as fake_login:
        fake_login.side_effect = GarminAuthError("bad creds")
        result = start_connect_flow(user_id="u1", email="a@b.c", password="p")

    assert result["status"] == "invalid_credentials"
    assert isinstance(result["retry_after_seconds"], int)
    assert result["retry_after_seconds"] > 0


def test_start_connect_flow_returns_rate_limited() -> None:
    from garmin_sync.connect import start_connect_flow
    from garmin_sync.garmin_client import GarminRateLimitError

    with patch("garmin_sync.connect.login_with_credentials") as fake_login:
        fake_login.side_effect = GarminRateLimitError("slow down")
        result = start_connect_flow(user_id="u1", email="a@b.c", password="p")

    assert result["status"] == "rate_limited"
    assert isinstance(result["retry_after_seconds"], int)
    assert result["retry_after_seconds"] > 0


def test_start_connect_flow_blocks_immediate_retry_after_rate_limit() -> None:
    """After a rate_limited response, a follow-up call from the same user must
    be rejected locally WITHOUT calling Garmin again — this is the whole point
    of the cooldown (one Garmin 429 = ~12 SSO requests under the hood).
    """
    from garmin_sync.connect import start_connect_flow
    from garmin_sync.garmin_client import GarminRateLimitError

    with patch("garmin_sync.connect.login_with_credentials") as fake_login:
        fake_login.side_effect = GarminRateLimitError("slow down")
        first = start_connect_flow(user_id="u1", email="a@b.c", password="p")
        second = start_connect_flow(user_id="u1", email="a@b.c", password="p")

    assert first["status"] == "rate_limited"
    assert second["status"] == "rate_limited"
    # Second call MUST NOT have reached Garmin
    assert fake_login.call_count == 1


def test_start_connect_flow_blocks_immediate_retry_after_invalid_credentials() -> None:
    from garmin_sync.connect import start_connect_flow
    from garmin_sync.garmin_client import GarminAuthError

    with patch("garmin_sync.connect.login_with_credentials") as fake_login:
        fake_login.side_effect = GarminAuthError("bad creds")
        first = start_connect_flow(user_id="u1", email="a@b.c", password="wrong")
        second = start_connect_flow(user_id="u1", email="a@b.c", password="wrong")

    assert first["status"] == "invalid_credentials"
    assert second["status"] == "invalid_credentials"
    assert fake_login.call_count == 1


def test_cooldown_is_per_user() -> None:
    """A cooldown on user A must not block user B."""
    from garmin_sync.connect import start_connect_flow
    from garmin_sync.garmin_client import GarminRateLimitError

    with patch("garmin_sync.connect.login_with_credentials") as fake_login:
        fake_login.side_effect = [GarminRateLimitError("slow down"), '{"oauth": "ok"}']
        with patch("garmin_sync.connect._persist_tokens"):
            res_a = start_connect_flow(user_id="userA", email="a@b.c", password="p")
            res_b = start_connect_flow(user_id="userB", email="a@b.c", password="p")

    assert res_a["status"] == "rate_limited"
    assert res_b["status"] == "connected"
    assert fake_login.call_count == 2


def test_successful_connect_clears_cooldown() -> None:
    """If the user eventually succeeds (e.g. fixes their password), the cooldown
    should be lifted so a later legitimate retry isn't blocked.
    """
    from garmin_sync.connect import _cooldowns, start_connect_flow

    _cooldowns["u1"] = (0.0, "invalid_credentials")  # expired entry — should be wiped

    with (
        patch("garmin_sync.connect.login_with_credentials") as fake_login,
        patch("garmin_sync.connect._persist_tokens"),
    ):
        fake_login.return_value = '{"oauth": "ok"}'
        # Simulate the cooldown was wiped on expiry, then succeed
        result = start_connect_flow(user_id="u1", email="a@b.c", password="p")

    assert result == {"status": "connected"}
    assert "u1" not in _cooldowns


def test_start_connect_flow_returns_garmin_error() -> None:
    from garmin_sync.connect import start_connect_flow
    from garmin_sync.garmin_client import GarminError

    with patch("garmin_sync.connect.login_with_credentials") as fake_login:
        fake_login.side_effect = GarminError("connection refused")
        result = start_connect_flow(user_id="u1", email="a@b.c", password="p")

    assert result["status"] == "garmin_error"
    assert _ERROR_ID_RE.match(result["error_id"])
    assert result["type"] == "GarminError"
    assert "detail" not in result
    assert "traceback" not in result


def test_resume_connect_flow_returns_unexpected_error_on_internal_crash() -> None:
    from garmin_sync.connect import _pending_mfa, resume_connect_flow

    challenge = object()
    _pending_mfa["cid"] = (9999999999.0, "u1", challenge)

    with patch("garmin_sync.connect.submit_mfa_code") as fake_submit:
        fake_submit.side_effect = RuntimeError("kaboom")
        result = resume_connect_flow(user_id="u1", challenge_id="cid", code="123456")

    assert result["status"] == "unexpected_error"
    assert _ERROR_ID_RE.match(result["error_id"])
    assert result["type"] == "RuntimeError"
    assert "detail" not in result
    assert "traceback" not in result


def test_resume_connect_flow_returns_garmin_error() -> None:
    from garmin_sync.connect import _pending_mfa, resume_connect_flow
    from garmin_sync.garmin_client import GarminError

    challenge = object()
    _pending_mfa["cid2"] = (9999999999.0, "u1", challenge)

    with patch("garmin_sync.connect.submit_mfa_code") as fake_submit:
        fake_submit.side_effect = GarminError("connection refused")
        result = resume_connect_flow(user_id="u1", challenge_id="cid2", code="123456")

    assert result["status"] == "garmin_error"
    assert _ERROR_ID_RE.match(result["error_id"])
    assert result["type"] == "GarminError"
    assert "detail" not in result
    assert "traceback" not in result


def test_resume_connect_flow_challenge_expired() -> None:
    from garmin_sync.connect import resume_connect_flow

    result = resume_connect_flow(user_id="u1", challenge_id="missing", code="123456")
    assert result == {"status": "challenge_expired"}
