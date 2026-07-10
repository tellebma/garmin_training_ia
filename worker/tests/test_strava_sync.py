from __future__ import annotations

import json
from unittest.mock import MagicMock

from garmin_sync import strava_sync
from garmin_sync.crypto import TokenCipher


def _encrypted_tokens(
    *, access_token="at", refresh_token="rt", expires_at=None  # noqa: S107
) -> str:
    import time

    expires_at = expires_at if expires_at is not None else int(time.time()) + 3600
    blob = json.dumps(
        {"access_token": access_token, "refresh_token": refresh_token, "expires_at": expires_at}
    )
    return TokenCipher().encrypt(blob).decode("ascii")


def _mock_db_with_credentials(encrypted: str | None) -> MagicMock:
    db = MagicMock()
    data = {"oauth_tokens_encrypted": encrypted} if encrypted else None
    chain = db.table.return_value.select.return_value.eq.return_value.single.return_value
    chain.execute.return_value = MagicMock(data=data)
    return db


def test_get_valid_access_token_returns_token_when_not_expired(monkeypatch):
    encrypted = _encrypted_tokens()
    db = _mock_db_with_credentials(encrypted)
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    token = strava_sync.get_valid_access_token("u1")

    assert token == "at"


def test_get_valid_access_token_refreshes_when_expired(monkeypatch):
    import time

    encrypted = _encrypted_tokens(expires_at=int(time.time()) - 10)
    db = _mock_db_with_credentials(encrypted)
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)
    monkeypatch.setattr(
        "garmin_sync.strava_client.refresh_access_token",
        lambda rt: {"access_token": "new-at", "refresh_token": "new-rt", "expires_at": 9999999999},
    )
    check_mock = MagicMock()
    record_mock = MagicMock()
    monkeypatch.setattr("garmin_sync.strava_rate_limit.check_or_raise", check_mock)
    monkeypatch.setattr("garmin_sync.strava_rate_limit.record_call", record_mock)

    token = strava_sync.get_valid_access_token("u1")

    assert token == "new-at"
    assert db.table.return_value.update.called
    assert check_mock.called
    assert record_mock.called


def test_get_valid_access_token_does_not_record_call_when_rate_limited(monkeypatch):
    import time

    encrypted = _encrypted_tokens(expires_at=int(time.time()) - 10)
    db = _mock_db_with_credentials(encrypted)
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)
    record_mock = MagicMock()
    monkeypatch.setattr("garmin_sync.strava_rate_limit.record_call", record_mock)

    def raise_rate_limited() -> None:
        from garmin_sync.strava_rate_limit import StravaRateLimitExceeded

        raise StravaRateLimitExceeded("budget exhausted")

    monkeypatch.setattr("garmin_sync.strava_rate_limit.check_or_raise", raise_rate_limited)

    token = strava_sync.get_valid_access_token("u1")

    assert token is None
    assert not record_mock.called
    update_call = db.table.return_value.update
    assert "token_refresh_failed_at" in update_call.call_args[0][0]


def test_get_valid_access_token_returns_none_when_no_credentials(monkeypatch):
    db = _mock_db_with_credentials(None)
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    assert strava_sync.get_valid_access_token("u1") is None


def test_get_valid_access_token_sets_failure_flag_on_refresh_error(monkeypatch):
    import time

    encrypted = _encrypted_tokens(expires_at=int(time.time()) - 10)
    db = _mock_db_with_credentials(encrypted)
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    def raise_error(rt: str):
        from garmin_sync.strava_client import StravaAuthError

        raise StravaAuthError("refresh rejected")

    monkeypatch.setattr("garmin_sync.strava_client.refresh_access_token", raise_error)

    token = strava_sync.get_valid_access_token("u1")

    assert token is None
    update_call = db.table.return_value.update
    assert update_call.called
    assert "token_refresh_failed_at" in update_call.call_args[0][0]


def test_run_strava_backfill_inserts_non_duplicate_activities(monkeypatch):
    encrypted = _encrypted_tokens()
    db = _mock_db_with_credentials(encrypted)
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)
    monkeypatch.setattr("garmin_sync.dedup.is_likely_garmin_duplicate", lambda *a, **k: False)

    pages = [
        [{"id": 1, "type": "Run", "start_date": "2026-06-01T06:00:00Z", "elapsed_time": 600}],
        [],
    ]
    monkeypatch.setattr(
        "garmin_sync.strava_client.list_activities",
        lambda token, *, after_epoch, page, per_page=100: pages[page - 1],
    )

    result = strava_sync.run_strava_backfill("u1", since_days=90)

    assert result["status"] == "ok"
    assert result["inserted"] == 1
    upsert_call = db.table.return_value.upsert
    assert upsert_call.called


def test_run_strava_backfill_skips_dedup_matches(monkeypatch):
    encrypted = _encrypted_tokens()
    db = _mock_db_with_credentials(encrypted)
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)
    monkeypatch.setattr("garmin_sync.dedup.is_likely_garmin_duplicate", lambda *a, **k: True)

    pages = [
        [{"id": 1, "type": "Run", "start_date": "2026-06-01T06:00:00Z", "elapsed_time": 600}],
        [],
    ]
    monkeypatch.setattr(
        "garmin_sync.strava_client.list_activities",
        lambda token, *, after_epoch, page, per_page=100: pages[page - 1],
    )

    result = strava_sync.run_strava_backfill("u1", since_days=90)

    assert result["inserted"] == 0


def test_run_strava_backfill_stops_and_reports_rate_limited(monkeypatch):
    encrypted = _encrypted_tokens()
    db = _mock_db_with_credentials(encrypted)
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    def raise_rate_limited() -> None:
        from garmin_sync.strava_rate_limit import StravaRateLimitExceeded

        raise StravaRateLimitExceeded("budget exhausted")

    monkeypatch.setattr("garmin_sync.strava_rate_limit.check_or_raise", raise_rate_limited)
    list_activities_mock = MagicMock()
    monkeypatch.setattr("garmin_sync.strava_client.list_activities", list_activities_mock)

    result = strava_sync.run_strava_backfill("u1", since_days=90)

    assert result == {"status": "rate_limited", "inserted": 0}
    assert not list_activities_mock.called
    update_call = db.table.return_value.update
    assert update_call.called
    payload = update_call.call_args[0][0]
    assert payload["last_sync_status"] == "rate_limited"
    assert "initial_sync_completed_at" not in payload


def test_run_strava_backfill_returns_no_credentials_when_missing(monkeypatch):
    db = _mock_db_with_credentials(None)
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    result = strava_sync.run_strava_backfill("u1")

    assert result == {"status": "no_credentials"}


def test_store_activity_from_webhook_upserts_single_row(monkeypatch):
    encrypted = _encrypted_tokens()
    db = _mock_db_with_credentials(encrypted)
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)
    monkeypatch.setattr("garmin_sync.dedup.is_likely_garmin_duplicate", lambda *a, **k: False)
    monkeypatch.setattr(
        "garmin_sync.strava_client.get_activity",
        lambda token, activity_id: {
            "id": activity_id,
            "type": "Run",
            "start_date": "2026-07-01T06:00:00Z",
            "elapsed_time": 600,
        },
    )

    result = strava_sync.store_activity_from_webhook("u1", 555)

    assert result == {"status": "stored"}
    assert db.table.return_value.upsert.called


def test_delete_activity_from_webhook_deletes_row(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    result = strava_sync.delete_activity_from_webhook("u1", 555)

    assert result == {"status": "deleted"}
    delete_chain = db.table.return_value.delete.return_value.eq.return_value.eq.return_value.eq
    assert delete_chain.return_value.execute.called
