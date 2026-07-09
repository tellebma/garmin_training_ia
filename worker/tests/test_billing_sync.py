from unittest.mock import MagicMock, patch

import httpx

from garmin_sync import billing_sync


def _settings():
    m = MagicMock()
    m.openai_admin_api_key.get_secret_value.return_value = "sk-admin-test"
    return m


def _openai_response(buckets):
    return MagicMock(
        status_code=200,
        json=lambda: {"data": buckets},
        raise_for_status=lambda: None,
    )


@patch("garmin_sync.billing_sync.get_admin_client")
@patch("garmin_sync.billing_sync.get_settings", return_value=_settings())
@patch.object(billing_sync, "httpx")
def test_billing_sync_upserts_daily_cost(mock_httpx, _mock_settings, mock_get_client):  # noqa: PT019
    # amount.value is a string on the real Costs API (decimal-as-string) —
    # confirmed empirically against a live account (int/str TypeError on sum()
    # before this was cast explicitly). Test the real shape, not a float.
    mock_httpx.get.return_value = _openai_response(
        [
            {"start_time": 1735689600, "results": [{"amount": {"value": "0.42"}}]},
        ]
    )
    mock_db = MagicMock()
    mock_get_client.return_value = mock_db

    result = billing_sync.run_billing_sync_cron()

    mock_db.table.assert_called_with("openai_billing_snapshot")
    upsert_call = mock_db.table.return_value.upsert
    assert upsert_call.called
    rows = upsert_call.call_args.args[0]
    assert any(row["cost_usd"] == 0.42 for row in rows)
    assert result["status"] == "ok"


@patch("garmin_sync.billing_sync.get_admin_client")
@patch("garmin_sync.billing_sync.get_settings", return_value=_settings())
@patch.object(billing_sync, "httpx")
def test_billing_sync_handles_numeric_amount_value_too(
    mock_httpx,
    _mock_settings,  # noqa: PT019
    mock_get_client,
):
    """Defensive: also accept a plain float, in case OpenAI's shape varies by field."""
    mock_httpx.get.return_value = _openai_response(
        [
            {"start_time": 1735689600, "results": [{"amount": {"value": 0.42}}]},
        ]
    )
    mock_db = MagicMock()
    mock_get_client.return_value = mock_db

    result = billing_sync.run_billing_sync_cron()

    rows = mock_db.table.return_value.upsert.call_args.args[0]
    assert any(row["cost_usd"] == 0.42 for row in rows)
    assert result["status"] == "ok"


@patch("garmin_sync.billing_sync.get_admin_client")
@patch("garmin_sync.billing_sync.get_settings", return_value=_settings())
@patch.object(billing_sync, "httpx")
@patch("garmin_sync.billing_sync.capture")
def test_billing_sync_logs_response_body_on_http_error(
    mock_capture,
    mock_httpx,
    _mock_settings,  # noqa: PT019
    mock_get_client,
):
    """A 403/permission error must surface OpenAI's actual message, not just 'error'."""
    error_response = MagicMock(status_code=403, text='{"error": {"message": "missing scope"}}')
    mock_httpx.get.return_value = MagicMock(
        raise_for_status=MagicMock(
            side_effect=httpx.HTTPStatusError("403", request=MagicMock(), response=error_response)
        )
    )

    result = billing_sync.run_billing_sync_cron()

    assert result["status"] == "error"
    mock_capture.assert_called_once()
    assert mock_capture.call_args.kwargs["status_code"] == 403
    mock_get_client.return_value.table.assert_not_called()


@patch("garmin_sync.billing_sync.get_admin_client")
@patch("garmin_sync.billing_sync.get_settings", return_value=_settings())
@patch.object(billing_sync, "httpx")
@patch("garmin_sync.billing_sync.capture")
def test_billing_sync_swallows_openai_failure(
    mock_capture,
    mock_httpx,
    _mock_settings,  # noqa: PT019
    mock_get_client,
):
    mock_httpx.get.side_effect = RuntimeError("network down")

    result = billing_sync.run_billing_sync_cron()

    mock_capture.assert_called_once()
    assert result["status"] == "error"
    mock_get_client.return_value.table.assert_not_called()


@patch("garmin_sync.billing_sync.get_settings")
def test_billing_sync_skips_when_key_unset(mock_get_settings):
    m = MagicMock()
    m.openai_admin_api_key.get_secret_value.return_value = ""
    mock_get_settings.return_value = m

    result = billing_sync.run_billing_sync_cron()

    assert result["status"] == "skipped_no_key"
