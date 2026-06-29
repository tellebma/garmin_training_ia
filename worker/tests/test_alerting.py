from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from garmin_sync import alerting


def _settings(webhook: str | None) -> MagicMock:
    return MagicMock(
        discord_webhook_url=SecretStr(webhook) if webhook else None,
        env="prod",
    )


def test_notify_discord_skips_when_no_webhook():
    with (
        patch.object(alerting, "get_settings", return_value=_settings(None)),
        patch.object(alerting, "httpx") as httpx_mod,
    ):
        alerting.notify_discord_error(ValueError("boom"), where="ensure_sessions")
    httpx_mod.post.assert_not_called()


def test_notify_discord_posts_embed_with_context():
    with (
        patch.object(
            alerting,
            "get_settings",
            return_value=_settings("https://discord.com/api/webhooks/1/abc"),
        ),
        patch.object(alerting, "httpx") as httpx_mod,
    ):
        alerting.notify_discord_error(
            ValueError("warmup exceeds cap"),
            where="ensure_sessions",
            session_id="s1",
            user_id=None,
        )
    httpx_mod.post.assert_called_once()
    url = httpx_mod.post.call_args.args[0]
    payload = httpx_mod.post.call_args.kwargs["json"]
    assert url == "https://discord.com/api/webhooks/1/abc"
    embed = payload["embeds"][0]
    assert "ValueError" in embed["title"]
    assert "ensure_sessions" in embed["title"]
    assert "warmup exceeds cap" in embed["description"]
    field_names = [f["name"] for f in embed["fields"]]
    assert "env" in field_names
    assert "session_id" in field_names
    assert "user_id" not in field_names  # None tags are dropped


def test_notify_discord_swallows_post_failure():
    with (
        patch.object(
            alerting,
            "get_settings",
            return_value=_settings("https://discord.com/api/webhooks/1/abc"),
        ),
        patch.object(alerting, "httpx") as httpx_mod,
    ):
        httpx_mod.post.side_effect = RuntimeError("network down")
        # must not raise — alerting can never break the calling path
        alerting.notify_discord_error(ValueError("x"), where="cron")
