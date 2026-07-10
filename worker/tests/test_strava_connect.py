# worker/tests/test_strava_connect.py
from __future__ import annotations

import json
from unittest.mock import MagicMock

from garmin_sync.strava_client import StravaAuthError
from garmin_sync.strava_connect import disconnect, start_connect_flow


def test_start_connect_flow_persists_encrypted_tokens(monkeypatch):
    monkeypatch.setattr(
        "garmin_sync.strava_client.exchange_code",
        lambda code: {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_at": 111,
            "athlete": {"id": 42},
        },
    )
    db = MagicMock()
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)
    monkeypatch.setattr("garmin_sync.strava_connect._trigger_initial_backfill", lambda _u: None)

    result = start_connect_flow(user_id="u1", code="abc")

    assert result == {"status": "connected"}
    upsert_call = db.table.return_value.upsert
    assert upsert_call.called
    row = upsert_call.call_args[0][0]
    assert row["user_id"] == "u1"
    assert row["strava_athlete_id"] == 42
    stored = json.loads(_decrypt(row["oauth_tokens_encrypted"]))
    assert stored == {"access_token": "at", "refresh_token": "rt", "expires_at": 111}


def _decrypt(ciphertext: str) -> str:
    from garmin_sync.crypto import TokenCipher

    return TokenCipher().decrypt(ciphertext.encode("ascii"))


def test_start_connect_flow_returns_error_on_bad_code(monkeypatch):
    def raise_auth_error(code: str):
        raise StravaAuthError("bad code")

    monkeypatch.setattr("garmin_sync.strava_client.exchange_code", raise_auth_error)

    result = start_connect_flow(user_id="u1", code="bad")

    assert result["status"] == "strava_auth_error"


def test_start_connect_flow_triggers_backfill(monkeypatch):
    monkeypatch.setattr(
        "garmin_sync.strava_client.exchange_code",
        lambda code: {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_at": 111,
            "athlete": {"id": 42},
        },
    )
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: MagicMock())
    triggered = []
    monkeypatch.setattr("garmin_sync.strava_connect._trigger_initial_backfill", triggered.append)

    start_connect_flow(user_id="u1", code="abc")

    assert triggered == ["u1"]


def test_disconnect_deletes_credentials_and_revokes_token(monkeypatch):
    from garmin_sync.crypto import TokenCipher

    tokens = json.dumps({"access_token": "at", "refresh_token": "rt", "expires_at": 1})
    encrypted = TokenCipher().encrypt(tokens).decode("ascii")

    db = MagicMock()
    single_result = MagicMock(data={"oauth_tokens_encrypted": encrypted})
    select_chain = db.table.return_value.select.return_value.eq.return_value.single
    select_chain.return_value.execute.return_value = single_result
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    revoked = []
    monkeypatch.setattr("garmin_sync.strava_client.deauthorize", revoked.append)

    result = disconnect(user_id="u1")

    assert result == {"status": "disconnected"}
    assert revoked == ["at"]
    delete_call = db.table.return_value.delete
    assert delete_call.called


def test_disconnect_succeeds_even_if_revoke_fails(monkeypatch):
    from garmin_sync.crypto import TokenCipher

    tokens = json.dumps({"access_token": "at", "refresh_token": "rt", "expires_at": 1})
    encrypted = TokenCipher().encrypt(tokens).decode("ascii")

    db = MagicMock()
    single_result = MagicMock(data={"oauth_tokens_encrypted": encrypted})
    select_chain = db.table.return_value.select.return_value.eq.return_value.single
    select_chain.return_value.execute.return_value = single_result
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    def raise_error(_token: str) -> None:
        raise RuntimeError("strava down")

    monkeypatch.setattr("garmin_sync.strava_client.deauthorize", raise_error)

    result = disconnect(user_id="u1")

    assert result == {"status": "disconnected"}
    assert db.table.return_value.delete.called


def test_disconnect_when_no_credentials_row(monkeypatch):
    db = MagicMock()
    single_result = MagicMock(data=None)
    select_chain = db.table.return_value.select.return_value.eq.return_value.single
    select_chain.return_value.execute.return_value = single_result
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    result = disconnect(user_id="u1")

    assert result == {"status": "not_connected"}
