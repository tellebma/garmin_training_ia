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


@patch("garmin_sync.coach.llm_usage.get_admin_client")
def test_record_llm_usage_persists_error_reason_on_failure(mock_get_client):
    mock_db = MagicMock()
    mock_get_client.return_value = mock_db

    record_llm_usage(
        user_id="u1",
        feature="session_workout",
        model="gpt-5.4-mini",
        prompt_tokens=900,
        completion_tokens=300,
        attempts=3,
        status="failed",
        session_id="s1",
        error_reason="warmup 1800s exceeds cap 900s",
    )

    payload = mock_db.table.return_value.insert.call_args.args[0]
    assert payload["error_reason"] == "warmup 1800s exceeds cap 900s"


@patch("garmin_sync.coach.llm_usage.get_admin_client")
def test_record_llm_usage_omits_error_reason_when_none(mock_get_client):
    """Clé absente (pas null) quand pas de motif : l'insert reste compatible tant
    que la migration error_reason n'est pas appliquée."""
    mock_db = MagicMock()
    mock_get_client.return_value = mock_db

    record_llm_usage(
        user_id="u1",
        feature="session_workout",
        model="gpt-5.4-mini",
        prompt_tokens=10,
        completion_tokens=5,
    )

    payload = mock_db.table.return_value.insert.call_args.args[0]
    assert "error_reason" not in payload


def _usage_rows(ok: int, failed: int) -> list[dict]:
    return [{"status": "ok"} for _ in range(ok)] + [{"status": "failed"} for _ in range(failed)]


def _failure_rate_db(rows: list[dict]) -> MagicMock:
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.gte.return_value
    chain.execute.return_value.data = rows
    return db


@patch("garmin_sync.coach.llm_usage.capture")
@patch("garmin_sync.coach.llm_usage.get_admin_client")
def test_failure_rate_alert_fires_above_threshold(mock_get_client, mock_capture):
    import garmin_sync.coach.llm_usage as llm_usage_mod
    from garmin_sync.coach.llm_usage import maybe_alert_generation_failure_rate

    llm_usage_mod._last_failure_rate_alert_at = None
    mock_get_client.return_value = _failure_rate_db(_usage_rows(ok=6, failed=4))  # 40 %

    assert maybe_alert_generation_failure_rate() is True
    mock_capture.assert_called_once()
    kwargs = mock_capture.call_args.kwargs
    assert kwargs["where"] == "llm_generation_failure_rate"
    assert kwargs["level"] == "warning"
    assert kwargs["failed"] == 4
    assert kwargs["total"] == 10


@patch("garmin_sync.coach.llm_usage.capture")
@patch("garmin_sync.coach.llm_usage.get_admin_client")
def test_failure_rate_alert_silent_below_threshold(mock_get_client, mock_capture):
    import garmin_sync.coach.llm_usage as llm_usage_mod
    from garmin_sync.coach.llm_usage import maybe_alert_generation_failure_rate

    llm_usage_mod._last_failure_rate_alert_at = None
    mock_get_client.return_value = _failure_rate_db(_usage_rows(ok=9, failed=1))  # 10 %

    assert maybe_alert_generation_failure_rate() is False
    mock_capture.assert_not_called()


@patch("garmin_sync.coach.llm_usage.capture")
@patch("garmin_sync.coach.llm_usage.get_admin_client")
def test_failure_rate_alert_needs_min_samples(mock_get_client, mock_capture):
    """2 échecs sur 2 générations = pas assez de signal pour alerter."""
    import garmin_sync.coach.llm_usage as llm_usage_mod
    from garmin_sync.coach.llm_usage import maybe_alert_generation_failure_rate

    llm_usage_mod._last_failure_rate_alert_at = None
    mock_get_client.return_value = _failure_rate_db(_usage_rows(ok=0, failed=2))

    assert maybe_alert_generation_failure_rate() is False
    mock_capture.assert_not_called()


@patch("garmin_sync.coach.llm_usage.capture")
@patch("garmin_sync.coach.llm_usage.get_admin_client")
def test_failure_rate_alert_throttled_within_cooldown(mock_get_client, mock_capture):
    import garmin_sync.coach.llm_usage as llm_usage_mod
    from garmin_sync.coach.llm_usage import maybe_alert_generation_failure_rate

    llm_usage_mod._last_failure_rate_alert_at = None
    mock_get_client.return_value = _failure_rate_db(_usage_rows(ok=0, failed=10))

    assert maybe_alert_generation_failure_rate() is True
    assert maybe_alert_generation_failure_rate() is False  # cooldown
    mock_capture.assert_called_once()


@patch("garmin_sync.coach.llm_usage.capture")
@patch("garmin_sync.coach.llm_usage.get_admin_client")
def test_failure_rate_alert_never_raises(mock_get_client, mock_capture):
    import garmin_sync.coach.llm_usage as llm_usage_mod
    from garmin_sync.coach.llm_usage import maybe_alert_generation_failure_rate

    llm_usage_mod._last_failure_rate_alert_at = None
    mock_get_client.side_effect = RuntimeError("db down")

    assert maybe_alert_generation_failure_rate() is False
    mock_capture.assert_not_called()
