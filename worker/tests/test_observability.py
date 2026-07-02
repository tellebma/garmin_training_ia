from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from garmin_sync import observability


def test_init_sentry_skips_when_no_dsn():
    settings = MagicMock(sentry_dsn=None, env="dev", sentry_traces_sample_rate=0.0)
    with (
        patch.object(observability, "get_settings", return_value=settings),
        patch.object(observability, "sentry_sdk") as sentry,
    ):
        enabled = observability.init_sentry()
    assert enabled is False
    sentry.init.assert_not_called()


def test_init_sentry_initialises_when_dsn_present():
    settings = MagicMock(
        sentry_dsn=SecretStr("https://abc@o0.ingest.sentry.io/1"),
        env="prod",
        sentry_traces_sample_rate=0.1,
    )
    with (
        patch.object(observability, "get_settings", return_value=settings),
        patch.object(observability, "sentry_sdk") as sentry,
    ):
        enabled = observability.init_sentry()
    assert enabled is True
    sentry.init.assert_called_once()
    kwargs = sentry.init.call_args.kwargs
    assert kwargs["environment"] == "prod"
    assert kwargs["dsn"].startswith("https://")
    assert kwargs["traces_sample_rate"] == 0.1


def test_new_error_id_is_short_hex():
    eid = observability.new_error_id()
    assert len(eid) == 8
    int(eid, 16)  # parses as hex


def test_capture_sends_exception_with_tags():
    exc = ValueError("boom")
    with patch.object(observability, "sentry_sdk") as sentry:
        scope = sentry.new_scope.return_value.__enter__.return_value
        observability.capture(exc, where="ensure_sessions", user_id="u1", session_id="s1")
    sentry.capture_exception.assert_called_once_with(exc)
    scope.set_tag.assert_any_call("where", "ensure_sessions")
    scope.set_tag.assert_any_call("user_id", "u1")


def test_capture_skips_none_tags():
    with patch.object(observability, "sentry_sdk") as sentry:
        scope = sentry.new_scope.return_value.__enter__.return_value
        observability.capture(ValueError("x"), where="cron", user_id=None)
    tagged_keys = [call.args[0] for call in scope.set_tag.call_args_list]
    assert "user_id" not in tagged_keys


def test_report_endpoint_error_returns_body_and_captures():
    exc = RuntimeError("kaboom")
    with patch.object(observability, "capture") as capture:
        body = observability.report_endpoint_error(
            exc, endpoint="coach_generate_plan", user_id="u1"
        )
    assert body["status"] == "unexpected_error"
    assert body["type"] == "RuntimeError"
    assert len(body["error_id"]) == 8
    capture.assert_called_once()
    assert capture.call_args.kwargs["where"] == "coach_generate_plan"
    assert capture.call_args.kwargs["error_id"] == body["error_id"]
