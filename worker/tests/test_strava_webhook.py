from __future__ import annotations

from unittest.mock import MagicMock

from garmin_sync import strava_webhook


def test_verify_challenge_returns_challenge_on_match(monkeypatch):
    from garmin_sync.config import get_settings

    token = get_settings().strava_webhook_verify_token.get_secret_value()

    result = strava_webhook.verify_challenge(mode="subscribe", token=token, challenge="abc123")

    assert result == "abc123"


def test_verify_challenge_returns_none_on_mismatch():
    result = strava_webhook.verify_challenge(
        mode="subscribe", token="wrong-token", challenge="abc123"
    )
    assert result is None


def test_verify_challenge_returns_none_on_missing_params():
    assert strava_webhook.verify_challenge(mode=None, token=None, challenge=None) is None


def _mock_db_with_athlete(user_id: str | None) -> MagicMock:
    db = MagicMock()
    data = {"user_id": user_id} if user_id else None
    chain = db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value
    chain.execute.return_value = MagicMock(data=data)
    return db


def test_handle_event_create_stores_activity(monkeypatch):
    db = _mock_db_with_athlete("u1")
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)
    stored = []
    monkeypatch.setattr(
        "garmin_sync.strava_sync.store_activity_from_webhook",
        lambda user_id, activity_id: stored.append((user_id, activity_id)) or {"status": "stored"},
    )

    result = strava_webhook.handle_event(
        {"object_type": "activity", "aspect_type": "create", "object_id": 555, "owner_id": 42}
    )

    assert result == {"status": "stored"}
    assert stored == [("u1", 555)]


def test_handle_event_update_stores_activity(monkeypatch):
    db = _mock_db_with_athlete("u1")
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)
    monkeypatch.setattr(
        "garmin_sync.strava_sync.store_activity_from_webhook",
        lambda user_id, activity_id: {"status": "stored"},
    )

    result = strava_webhook.handle_event(
        {"object_type": "activity", "aspect_type": "update", "object_id": 555, "owner_id": 42}
    )

    assert result == {"status": "stored"}


def test_handle_event_delete_removes_activity(monkeypatch):
    db = _mock_db_with_athlete("u1")
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)
    deleted = []
    monkeypatch.setattr(
        "garmin_sync.strava_sync.delete_activity_from_webhook",
        lambda user_id, activity_id: (
            deleted.append((user_id, activity_id)) or {"status": "deleted"}
        ),
    )

    result = strava_webhook.handle_event(
        {"object_type": "activity", "aspect_type": "delete", "object_id": 555, "owner_id": 42}
    )

    assert result == {"status": "deleted"}
    assert deleted == [("u1", 555)]


def test_handle_event_deauthorization_clears_credentials(monkeypatch):
    db = _mock_db_with_athlete("u1")
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    result = strava_webhook.handle_event(
        {
            "object_type": "athlete",
            "aspect_type": "update",
            "object_id": 42,
            "owner_id": 42,
            "updates": {"authorized": "false"},
        }
    )

    assert result == {"status": "deauthorized"}
    assert db.table.return_value.delete.called


def test_handle_event_ignores_unknown_owner(monkeypatch):
    db = _mock_db_with_athlete(None)
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    result = strava_webhook.handle_event(
        {"object_type": "activity", "aspect_type": "create", "object_id": 555, "owner_id": 999}
    )

    assert result == {"status": "unknown_athlete"}


def test_handle_event_ignores_non_activity_non_deauth_events(monkeypatch):
    db = _mock_db_with_athlete("u1")
    monkeypatch.setattr("garmin_sync.supabase_client.get_admin_client", lambda: db)

    result = strava_webhook.handle_event(
        {
            "object_type": "athlete",
            "aspect_type": "update",
            "object_id": 42,
            "owner_id": 42,
            "updates": {},
        }
    )

    assert result == {"status": "ignored"}
