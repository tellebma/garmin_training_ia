"""Tests for the Garmin connect/MFA flow error handling."""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

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
        with (
            patch("garmin_sync.connect._persist_tokens"),
            patch("garmin_sync.connect._trigger_initial_sync"),
        ):
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
        patch("garmin_sync.connect._trigger_initial_sync"),
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


def test_start_connect_flow_returns_mfa_required_when_garmin_demands_it() -> None:
    """If Garmin demands an MFA code, start_connect_flow must:
    1. Store the (challenge_id, user_id, challenge) tuple in _pending_mfa
    2. Return ``status: mfa_required`` + challenge_id to the caller

    Covers connect.py lines 91-93."""
    from garmin_sync.connect import _pending_mfa, start_connect_flow
    from garmin_sync.garmin_client import GarminMFARequired

    sentinel_challenge = object()
    with patch("garmin_sync.connect.login_with_credentials") as fake_login:
        fake_login.side_effect = GarminMFARequired(challenge=sentinel_challenge)
        result = start_connect_flow(user_id="u1", email="a@b.c", password="p")

    assert result["status"] == "mfa_required"
    challenge_id = result["challenge_id"]
    assert challenge_id in _pending_mfa
    _ts, owner, stored = _pending_mfa[challenge_id]
    assert owner == "u1"
    assert stored is sentinel_challenge


def test_resume_connect_flow_returns_connected_and_persists_tokens() -> None:
    """Happy path: a previously stored challenge resolves successfully with a
    valid MFA code; the worker decrypts/persists fresh tokens.

    Covers connect.py lines 153-155 + the _persist_tokens helper (167-170)."""
    from garmin_sync.connect import _pending_mfa, resume_connect_flow

    challenge = object()
    _pending_mfa["cid_ok"] = (9999999999.0, "u1", challenge)

    with (
        patch("garmin_sync.connect.submit_mfa_code", return_value='{"oauth": "fresh"}'),
        patch("garmin_sync.connect._persist_tokens") as persist_mock,
        patch("garmin_sync.connect._trigger_initial_sync"),
    ):
        result = resume_connect_flow(user_id="u1", challenge_id="cid_ok", code="123456")

    assert result == {"status": "connected"}
    persist_mock.assert_called_once_with(user_id="u1", tokens_json='{"oauth": "fresh"}')
    assert "cid_ok" not in _pending_mfa


def test_resume_connect_flow_returns_invalid_code() -> None:
    """A bad MFA code → GarminAuthError → invalid_code response + cooldown.

    Covers connect.py lines 139-140."""
    from garmin_sync.connect import _pending_mfa, resume_connect_flow
    from garmin_sync.garmin_client import GarminAuthError

    challenge = object()
    _pending_mfa["cid_bad"] = (9999999999.0, "u1", challenge)

    with patch("garmin_sync.connect.submit_mfa_code", side_effect=GarminAuthError("nope")):
        result = resume_connect_flow(user_id="u1", challenge_id="cid_bad", code="000000")

    assert result["status"] == "invalid_code"
    assert isinstance(result["retry_after_seconds"], int)
    assert result["retry_after_seconds"] > 0


def test_resume_connect_flow_returns_rate_limited() -> None:
    """If submit_mfa_code hits a 429, surface rate_limited + cooldown.

    Covers connect.py lines 142-143."""
    from garmin_sync.connect import _pending_mfa, resume_connect_flow
    from garmin_sync.garmin_client import GarminRateLimitError

    challenge = object()
    _pending_mfa["cid_rl"] = (9999999999.0, "u1", challenge)

    with patch("garmin_sync.connect.submit_mfa_code", side_effect=GarminRateLimitError("429")):
        result = resume_connect_flow(user_id="u1", challenge_id="cid_rl", code="123456")

    assert result["status"] == "rate_limited"
    assert isinstance(result["retry_after_seconds"], int)
    assert result["retry_after_seconds"] > 0


def test_resume_connect_flow_returns_challenge_user_mismatch() -> None:
    """If user B tries to redeem user A's challenge, reject without leaking
    that the challenge exists.

    Covers connect.py line 134."""
    from garmin_sync.connect import _pending_mfa, resume_connect_flow

    challenge = object()
    _pending_mfa["cid_x"] = (9999999999.0, "userA", challenge)

    result = resume_connect_flow(user_id="userB", challenge_id="cid_x", code="123456")
    assert result == {"status": "challenge_user_mismatch"}


def test_resume_connect_flow_blocked_by_cooldown() -> None:
    """A cooldown on user1 must block any resume attempts as well — not just
    the initial connect.

    Covers connect.py line 126 (the _check_cooldown early return in resume)."""
    import time

    from garmin_sync.connect import _cooldowns, resume_connect_flow

    # Set an active cooldown
    _cooldowns["u1"] = (time.time() + 300, "rate_limited")

    result = resume_connect_flow(user_id="u1", challenge_id="anything", code="123456")
    assert result["status"] == "rate_limited"
    assert isinstance(result["retry_after_seconds"], int)


def test_check_cooldown_returns_none_for_expired_entry() -> None:
    """When a cooldown row exists but is in the past, _check_cooldown must
    pop it and return None so the user is unblocked.

    Covers connect.py lines 67-69 (the `remaining <= 0` branch)."""
    import time

    from garmin_sync.connect import _check_cooldown, _cooldowns

    _cooldowns["uX"] = (time.time() - 1, "invalid_credentials")
    assert _check_cooldown("uX") is None
    assert "uX" not in _cooldowns


def test_purge_expired_removes_old_mfa_challenges() -> None:
    """An MFA challenge older than _MFA_EXPIRY_S must be evicted on the next
    call to start/resume_connect_flow.

    Covers connect.py line 54 (the actual ``pop`` inside _purge_expired)."""
    from garmin_sync.connect import _MFA_EXPIRY_S, _pending_mfa, _purge_expired

    # Insert an MFA entry with a timestamp older than the expiry window
    _pending_mfa["old_cid"] = (1.0, "u1", object())  # ts way in the past
    _purge_expired()
    assert "old_cid" not in _pending_mfa
    # Sanity: the expiry threshold is the value advertised by the module
    assert _MFA_EXPIRY_S > 0


def test_start_connect_flow_triggers_initial_sync_on_success() -> None:
    """E15.4: a successful connect must fire a first sync so the athlete sees
    data immediately, instead of waiting for the next cron run."""
    from garmin_sync.connect import start_connect_flow

    with (
        patch("garmin_sync.connect.login_with_credentials", return_value='{"oauth": "ok"}'),
        patch("garmin_sync.connect._persist_tokens"),
        patch("garmin_sync.connect._trigger_initial_sync") as trigger,
    ):
        result = start_connect_flow(user_id="u1", email="a@b.c", password="p")

    assert result == {"status": "connected"}
    trigger.assert_called_once_with("u1")


def test_start_connect_flow_does_not_trigger_sync_on_invalid_credentials() -> None:
    from garmin_sync.connect import start_connect_flow
    from garmin_sync.garmin_client import GarminAuthError

    with (
        patch("garmin_sync.connect.login_with_credentials", side_effect=GarminAuthError("nope")),
        patch("garmin_sync.connect._trigger_initial_sync") as trigger,
    ):
        result = start_connect_flow(user_id="u1", email="a@b.c", password="wrong")

    assert result["status"] == "invalid_credentials"
    trigger.assert_not_called()


def test_start_connect_flow_does_not_trigger_sync_on_mfa_required() -> None:
    """MFA is not a completed connect — the sync must wait for resume."""
    from garmin_sync.connect import start_connect_flow
    from garmin_sync.garmin_client import GarminMFARequired

    with (
        patch(
            "garmin_sync.connect.login_with_credentials",
            side_effect=GarminMFARequired(challenge=object()),
        ),
        patch("garmin_sync.connect._trigger_initial_sync") as trigger,
    ):
        result = start_connect_flow(user_id="u1", email="a@b.c", password="p")

    assert result["status"] == "mfa_required"
    trigger.assert_not_called()


def test_resume_connect_flow_triggers_initial_sync_on_success() -> None:
    from garmin_sync.connect import _pending_mfa, resume_connect_flow

    _pending_mfa["cid_sync"] = (9999999999.0, "u1", object())

    with (
        patch("garmin_sync.connect.submit_mfa_code", return_value='{"oauth": "fresh"}'),
        patch("garmin_sync.connect._persist_tokens"),
        patch("garmin_sync.connect._trigger_initial_sync") as trigger,
    ):
        result = resume_connect_flow(user_id="u1", challenge_id="cid_sync", code="123456")

    assert result == {"status": "connected"}
    trigger.assert_called_once_with("u1")


def test_resume_connect_flow_does_not_trigger_sync_on_invalid_code() -> None:
    from garmin_sync.connect import _pending_mfa, resume_connect_flow
    from garmin_sync.garmin_client import GarminAuthError

    _pending_mfa["cid_bad_sync"] = (9999999999.0, "u1", object())

    with (
        patch("garmin_sync.connect.submit_mfa_code", side_effect=GarminAuthError("nope")),
        patch("garmin_sync.connect._trigger_initial_sync") as trigger,
    ):
        result = resume_connect_flow(user_id="u1", challenge_id="cid_bad_sync", code="000000")

    assert result["status"] == "invalid_code"
    trigger.assert_not_called()


def test_trigger_initial_sync_runs_sync_in_daemon_thread() -> None:
    """_trigger_initial_sync must spawn a daemon thread whose target runs
    run_sync_for_user for the given user — non-blocking for the HTTP response."""
    from garmin_sync.connect import _trigger_initial_sync

    with patch("garmin_sync.connect.threading.Thread") as fake_thread:
        _trigger_initial_sync("u1")

    fake_thread.assert_called_once()
    assert fake_thread.call_args.kwargs["daemon"] is True
    fake_thread.return_value.start.assert_called_once()

    # Running the captured target must drive the real sync for that user.
    target = fake_thread.call_args.kwargs["target"]
    with patch("garmin_sync.cron.run_sync_for_user") as fake_sync:
        target()
    fake_sync.assert_called_once_with("u1")


def test_trigger_initial_sync_target_swallows_sync_errors() -> None:
    """A failing first sync must never bubble up — the user stays connected and
    the cron will retry."""
    from garmin_sync.connect import _trigger_initial_sync

    with patch("garmin_sync.connect.threading.Thread") as fake_thread:
        _trigger_initial_sync("u1")

    target = fake_thread.call_args.kwargs["target"]
    with patch("garmin_sync.cron.run_sync_for_user", side_effect=RuntimeError("boom")):
        target()  # must not raise


def test_persist_tokens_upserts_encrypted_payload() -> None:
    """Smoke-test _persist_tokens: it should encrypt, base64-encode and call
    upsert on the garmin_credentials table with the expected shape.

    Covers connect.py lines 167-179."""
    from garmin_sync.connect import _persist_tokens

    fake_db = MagicMock()
    with patch("garmin_sync.connect.get_admin_client", return_value=fake_db):
        _persist_tokens(user_id="u1", tokens_json='{"oauth": "ok"}')

    fake_db.table.assert_called_with("garmin_credentials")
    upsert_call = fake_db.table.return_value.upsert.call_args
    payload = upsert_call.args[0]
    assert payload["user_id"] == "u1"
    assert payload["token_refresh_failed_at"] is None
    assert payload["last_sync_status"] is None
    # encrypted payload is a str (ASCII base64 from Fernet)
    assert isinstance(payload["oauth_tokens_encrypted"], str)
    assert payload["oauth_tokens_encrypted"]  # non-empty
    assert upsert_call.kwargs.get("on_conflict") == "user_id"
