"""Tests for cron.run_sync_for_user — token encoding round-trip + auth failure paths
+ tests for run_daily_cron orchestration."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from garmin_sync.crypto import TokenCipher
from garmin_sync.garmin_client import GarminAuthError


def _make_creds_row(
    token_plain: str, *, initial_sync_completed_at: str | None = None
) -> dict[str, object]:
    cipher = TokenCipher()
    ciphertext = cipher.encrypt(token_plain)
    return {
        "oauth_tokens_encrypted": ciphertext.decode("ascii"),
        "initial_sync_completed_at": initial_sync_completed_at,
    }


def _setup_fake_db(creds_data: object) -> MagicMock:
    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = creds_data  # noqa: E501
    return fake_db


def test_run_sync_for_user_decodes_token_from_text_column() -> None:
    """The token is stored as TEXT (ASCII base64). cron.run_sync_for_user must
    encode it back to bytes before passing to Fernet.decrypt.
    """
    from garmin_sync.cron import run_sync_for_user

    fake_db = _setup_fake_db(_make_creds_row('{"oauth": "ok"}'))
    fake_garmin = MagicMock()

    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.login_with_tokens", return_value=fake_garmin) as login_mock,
        patch("garmin_sync.cron.sync_user_for_date_range") as sync_mock,
    ):
        result = run_sync_for_user("u1", initial=False)

    assert result["status"] == "ok"
    # Critical: login_with_tokens received the decrypted plaintext, NOT raw ciphertext
    login_mock.assert_called_once_with('{"oauth": "ok"}')
    sync_mock.assert_called_once()


def test_run_sync_for_user_returns_no_credentials_when_missing() -> None:
    from garmin_sync.cron import run_sync_for_user

    fake_db = _setup_fake_db(None)

    with patch("garmin_sync.cron.get_admin_client", return_value=fake_db):
        result = run_sync_for_user("u1", initial=False)

    assert result == {"status": "no_credentials"}


def test_run_sync_for_user_returns_no_credentials_when_token_field_empty() -> None:
    """A row exists but the token field is empty — treat as no credentials."""
    from garmin_sync.cron import run_sync_for_user

    fake_db = _setup_fake_db({"oauth_tokens_encrypted": None, "initial_sync_completed_at": None})

    with patch("garmin_sync.cron.get_admin_client", return_value=fake_db):
        result = run_sync_for_user("u1", initial=False)

    assert result == {"status": "no_credentials"}


def test_run_sync_for_user_returns_auth_failed_when_login_with_tokens_fails() -> None:
    """If the encrypted token is no longer valid (Garmin invalidated it),
    login_with_tokens raises GarminAuthError. The cron must mark the credential
    row with token_refresh_failed_at and return {"status": "auth_failed"}.
    """
    from garmin_sync.cron import run_sync_for_user

    fake_db = _setup_fake_db(_make_creds_row('{"oauth": "ok"}'))

    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.login_with_tokens", side_effect=GarminAuthError("expired")),
    ):
        result = run_sync_for_user("u1", initial=False)

    assert result == {"status": "auth_failed"}
    # We must have called update with token_refresh_failed_at set
    update_calls = [
        c
        for c in fake_db.table.return_value.update.call_args_list
        if "token_refresh_failed_at" in (c.args[0] if c.args else {})
    ]
    assert len(update_calls) >= 1


def test_run_sync_for_user_uses_initial_backfill_window_when_initial_true() -> None:
    """initial=True → start = today - 90 days."""
    from garmin_sync.cron import INITIAL_BACKFILL_DAYS, run_sync_for_user

    fake_db = _setup_fake_db(_make_creds_row('{"oauth": "ok"}'))

    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.login_with_tokens", return_value=MagicMock()),
        patch("garmin_sync.cron.sync_user_for_date_range") as sync_mock,
    ):
        result = run_sync_for_user("u1", initial=True)

    assert result["status"] == "ok"
    # days_synced = 90 + 1 (inclusive)
    assert result["days_synced"] == INITIAL_BACKFILL_DAYS + 1
    kwargs = sync_mock.call_args.kwargs
    assert (kwargs["end"] - kwargs["start"]).days == INITIAL_BACKFILL_DAYS


def test_run_sync_for_user_uses_incremental_window_when_initial_done() -> None:
    """initial=False AND initial_sync_completed_at is set → 2-day window."""
    from garmin_sync.cron import run_sync_for_user

    fake_db = _setup_fake_db(
        _make_creds_row('{"oauth": "ok"}', initial_sync_completed_at="2025-01-01T00:00:00+00:00")
    )

    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.login_with_tokens", return_value=MagicMock()),
        patch("garmin_sync.cron.sync_user_for_date_range") as sync_mock,
    ):
        result = run_sync_for_user("u1", initial=False)

    # 2 days back + today = 3 days inclusive
    assert result["days_synced"] == 3
    kwargs = sync_mock.call_args.kwargs
    assert (kwargs["end"] - kwargs["start"]).days == 2


def test_run_sync_for_user_handles_rate_limit_during_sync() -> None:
    """If sync_user_for_date_range raises GarminConnectTooManyRequestsError,
    cron must mark last_sync_status='rate_limited' and return rate_limited."""
    from garmin_sync.cron import run_sync_for_user

    fake_db = _setup_fake_db(_make_creds_row('{"oauth": "ok"}'))

    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.login_with_tokens", return_value=MagicMock()),
        patch(
            "garmin_sync.cron.sync_user_for_date_range",
            side_effect=GarminConnectTooManyRequestsError("429"),
        ),
    ):
        result = run_sync_for_user("u1", initial=False)

    assert result == {"status": "rate_limited"}
    # last_sync_status should be in the update payload
    update_calls = fake_db.table.return_value.update.call_args_list
    found = any(
        c.args and c.args[0].get("last_sync_status") == "rate_limited" for c in update_calls
    )
    assert found, f"Expected last_sync_status=rate_limited in {update_calls}"


def test_run_sync_for_user_handles_auth_error_during_sync() -> None:
    """If sync_user_for_date_range raises GarminConnectAuthenticationError,
    cron must mark token_refresh_failed_at + last_sync_status='auth_failed'."""
    from garmin_sync.cron import run_sync_for_user

    fake_db = _setup_fake_db(_make_creds_row('{"oauth": "ok"}'))

    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.login_with_tokens", return_value=MagicMock()),
        patch(
            "garmin_sync.cron.sync_user_for_date_range",
            side_effect=GarminConnectAuthenticationError("401"),
        ),
    ):
        result = run_sync_for_user("u1", initial=False)

    assert result == {"status": "auth_failed"}
    update_calls = fake_db.table.return_value.update.call_args_list
    found = any(c.args and c.args[0].get("last_sync_status") == "auth_failed" for c in update_calls)
    assert found


def test_run_sync_for_user_preserves_initial_sync_completed_at_when_set() -> None:
    """If initial_sync_completed_at is already set, the success update must
    keep that value instead of overwriting it with 'now'."""
    from garmin_sync.cron import run_sync_for_user

    original_ts = "2025-01-01T00:00:00+00:00"
    fake_db = _setup_fake_db(
        _make_creds_row('{"oauth": "ok"}', initial_sync_completed_at=original_ts)
    )

    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.login_with_tokens", return_value=MagicMock()),
        patch("garmin_sync.cron.sync_user_for_date_range"),
    ):
        result = run_sync_for_user("u1", initial=False)

    assert result["status"] == "ok"
    update_calls = fake_db.table.return_value.update.call_args_list
    ok_updates = [c for c in update_calls if c.args and c.args[0].get("last_sync_status") == "ok"]
    assert ok_updates
    payload = ok_updates[0].args[0]
    assert payload["initial_sync_completed_at"] == original_ts


def test_run_daily_cron_iterates_all_users() -> None:
    """run_daily_cron must list users with non-null tokens and call run_sync_for_user
    for each. Returned dict aggregates per-user results."""
    from garmin_sync.cron import run_daily_cron

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = [
        {"user_id": "u1"},
        {"user_id": "u2"},
    ]

    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.run_sync_for_user") as run_user_mock,
    ):
        run_user_mock.side_effect = [{"status": "ok"}, {"status": "no_credentials"}]
        result = run_daily_cron()

    assert result["total_users"] == 2
    assert result["results"]["u1"] == {"status": "ok"}
    assert result["results"]["u2"] == {"status": "no_credentials"}
    assert run_user_mock.call_count == 2


def test_run_daily_cron_catches_per_user_exceptions() -> None:
    """If one user crashes, run_daily_cron must keep going for the others
    and mark the crashed user with status='exception'."""
    from garmin_sync.cron import run_daily_cron

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = [
        {"user_id": "u1"},
        {"user_id": "u2"},
        {"user_id": "u3"},
    ]

    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.run_sync_for_user") as run_user_mock,
    ):
        run_user_mock.side_effect = [
            {"status": "ok"},
            RuntimeError("boom"),
            {"status": "ok"},
        ]
        result = run_daily_cron()

    assert result["total_users"] == 3
    assert result["results"]["u1"] == {"status": "ok"}
    assert result["results"]["u2"] == {"status": "exception"}
    assert result["results"]["u3"] == {"status": "ok"}


def test_run_daily_cron_handles_no_users() -> None:
    from garmin_sync.cron import run_daily_cron

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = []

    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.run_sync_for_user") as run_user_mock,
    ):
        result = run_daily_cron()

    assert result == {"mode": "full", "total_users": 0, "results": {}}
    run_user_mock.assert_not_called()


def test_cron_main_block_prints_json(capsys: object, monkeypatch: object) -> None:
    """Smoke-test the ``if __name__ == '__main__'`` block by executing the
    cron module as a script via runpy with run_daily_cron and get_admin_client
    mocked.

    This covers lines 113-117 (the CLI entry point).
    """
    import runpy
    import sys

    # runpy re-imports the module under __main__, so we need to ensure
    # get_admin_client doesn't try to hit Supabase. We do this by patching
    # the SOURCE module (garmin_sync.supabase_client) so the re-import resolves
    # the already-patched symbol.
    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = []

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "garmin_sync.supabase_client.get_admin_client",
        lambda: fake_db,
    )

    # Drop the cached cron module so runpy re-imports it freshly under __main__.
    # The CLI now takes an optional mode arg; default ("full") matches the
    # legacy daily cron behaviour.
    original_argv = sys.argv
    sys.argv = ["garmin_sync.cron"]
    try:
        sys.modules.pop("garmin_sync.cron", None)
        runpy.run_module("garmin_sync.cron", run_name="__main__")
    finally:
        sys.argv = original_argv

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert payload == {"mode": "full", "total_users": 0, "results": {}}


def test_run_sleep_cron_uses_sleep_only_mode() -> None:
    from garmin_sync.cron import run_sleep_cron

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = [
        {"user_id": "u1"}
    ]
    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.run_sync_for_user") as run_user_mock,
    ):
        run_user_mock.return_value = {"status": "ok"}
        result = run_sleep_cron()

    assert result["mode"] == "sleep_only"
    assert result["total_users"] == 1
    call_kwargs = run_user_mock.call_args.kwargs
    assert call_kwargs["mode"] == "sleep_only"


def test_run_activities_cron_uses_activities_only_mode() -> None:
    from garmin_sync.cron import run_activities_cron

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = [
        {"user_id": "u1"}
    ]
    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.run_sync_for_user") as run_user_mock,
    ):
        run_user_mock.return_value = {"status": "ok"}
        result = run_activities_cron()

    assert result["mode"] == "activities_only"
    call_kwargs = run_user_mock.call_args.kwargs
    assert call_kwargs["mode"] == "activities_only"


def test_run_profile_sync_cron_calls_sync_garmin_profile() -> None:
    from garmin_sync.cron import run_profile_sync_cron

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = [
        {"user_id": "u1"},
        {"user_id": "u2"},
    ]
    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.profile_sync.sync_garmin_profile") as profile_mock,
    ):
        profile_mock.return_value = {"status": "ok", "fetched": {}}
        result = run_profile_sync_cron()

    assert result["mode"] == "profile"
    assert result["total_users"] == 2
    assert profile_mock.call_count == 2


def test_run_cron_with_unknown_user_returns_exception_status() -> None:
    """Generic resilience: if run_sync_for_user raises, cron records exception status."""
    from garmin_sync.cron import run_daily_cron

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = [
        {"user_id": "u-broken"}
    ]
    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.run_sync_for_user", side_effect=RuntimeError("boom")),
    ):
        result = run_daily_cron()

    assert result["results"]["u-broken"] == {"status": "exception"}
