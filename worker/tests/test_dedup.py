from __future__ import annotations

from unittest.mock import MagicMock

from garmin_sync.dedup import is_likely_garmin_duplicate


def _mock_db(rows: list[dict]) -> MagicMock:
    db = MagicMock()
    execute = MagicMock(return_value=MagicMock(data=rows))
    query = MagicMock()
    query.execute = execute
    (
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.lte.return_value
    ) = query
    return db


def test_returns_true_when_garmin_activity_within_window():
    db = _mock_db([{"id": "a1"}])
    result = is_likely_garmin_duplicate(
        db, user_id="u1", start_time="2026-07-01T06:30:00+00:00", sport="run"
    )
    assert result is True


def test_returns_false_when_no_garmin_activity():
    db = _mock_db([])
    result = is_likely_garmin_duplicate(
        db, user_id="u1", start_time="2026-07-01T06:30:00+00:00", sport="run"
    )
    assert result is False


def test_queries_expected_time_window_and_filters():
    db = _mock_db([])
    is_likely_garmin_duplicate(
        db, user_id="u1", start_time="2026-07-01T06:30:00+00:00", sport="run"
    )
    select_call = db.table.return_value.select
    eq_calls = select_call.return_value.eq
    assert db.table.call_args[0][0] == "activities"
    assert eq_calls.call_args_list[0][0] == ("user_id", "u1")
    second_eq = eq_calls.return_value.eq
    assert second_eq.call_args[0] == ("sport", "run")
    gte_call = second_eq.return_value.gte
    assert gte_call.call_args[0][0] == "start_time"
    assert gte_call.call_args[0][1] == "2026-07-01T06:25:00+00:00"
    lte_call = gte_call.return_value.lte
    assert lte_call.call_args[0][0] == "start_time"
    assert lte_call.call_args[0][1] == "2026-07-01T06:35:00+00:00"
