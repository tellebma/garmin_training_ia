"""Tests for the Garmin connect/MFA flow error handling."""

from __future__ import annotations

import re
from unittest.mock import patch

_ERROR_ID_RE = re.compile(r"^[0-9a-f]{8}$")


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

    assert result == {"status": "invalid_credentials"}


def test_start_connect_flow_returns_rate_limited() -> None:
    from garmin_sync.connect import start_connect_flow
    from garmin_sync.garmin_client import GarminRateLimitError

    with patch("garmin_sync.connect.login_with_credentials") as fake_login:
        fake_login.side_effect = GarminRateLimitError("slow down")
        result = start_connect_flow(user_id="u1", email="a@b.c", password="p")

    assert result == {"status": "rate_limited"}


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
