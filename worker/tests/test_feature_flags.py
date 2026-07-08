from unittest.mock import MagicMock

from garmin_sync.feature_flags import is_flag_active


def _db_with_flag(row):
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.maybe_single
    chain.return_value.execute.return_value.data = row
    return db


def test_is_flag_active_true_no_expiry():
    db = _db_with_flag({"enabled": True, "expires_at": None})
    assert is_flag_active(db, "llm_generation_enabled") is True


def test_is_flag_active_false_when_disabled():
    db = _db_with_flag({"enabled": False, "expires_at": None})
    assert is_flag_active(db, "llm_generation_enabled") is False


def test_is_flag_active_false_when_expired():
    db = _db_with_flag({"enabled": True, "expires_at": "2020-01-01T00:00:00+00:00"})
    assert is_flag_active(db, "public_registration_enabled") is False


def test_is_flag_active_true_when_expiry_in_future():
    db = _db_with_flag({"enabled": True, "expires_at": "2999-01-01T00:00:00+00:00"})
    assert is_flag_active(db, "public_registration_enabled") is True


def test_is_flag_active_false_when_row_missing():
    db = _db_with_flag(None)
    assert is_flag_active(db, "unknown_key") is False
