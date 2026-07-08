from unittest.mock import MagicMock, patch

from garmin_sync.coach.llm_usage import record_llm_usage


@patch("garmin_sync.coach.llm_usage.get_admin_client")
def test_record_llm_usage_writes_expected_row(mock_get_client):
    mock_db = MagicMock()
    mock_get_client.return_value = mock_db

    record_llm_usage(
        user_id="u1",
        feature="session_workout",
        model="gpt-4o-mini",
        prompt_tokens=1000,
        completion_tokens=200,
    )

    mock_db.table.assert_called_once_with("llm_usage")
    insert_call = mock_db.table.return_value.insert
    payload = insert_call.call_args.args[0]
    assert payload["user_id"] == "u1"
    assert payload["feature"] == "session_workout"
    assert payload["model"] == "gpt-4o-mini"
    assert payload["prompt_tokens"] == 1000
    assert payload["completion_tokens"] == 200
    assert payload["total_tokens"] == 1200
    assert payload["cost_usd"] > 0


@patch("garmin_sync.coach.llm_usage.capture")
@patch("garmin_sync.coach.llm_usage.get_admin_client")
def test_record_llm_usage_swallows_write_failure(mock_get_client, mock_capture):
    mock_get_client.side_effect = RuntimeError("db down")

    # must not raise
    record_llm_usage(
        user_id="u1",
        feature="session_workout",
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
    )

    mock_capture.assert_called_once()
    assert mock_capture.call_args.kwargs["where"] == "record_llm_usage"
