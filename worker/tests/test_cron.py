"""Tests for cron.run_sync_for_user — token encoding round-trip + auth failure paths."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from garmin_sync.crypto import TokenCipher


def _make_creds_row(token_plain: str) -> dict[str, object]:
    cipher = TokenCipher()
    ciphertext = cipher.encrypt(token_plain)
    return {
        "oauth_tokens_encrypted": ciphertext.decode("ascii"),
        "initial_sync_completed_at": None,
    }


def test_run_sync_for_user_decodes_token_from_text_column() -> None:
    """The token is stored as TEXT (ASCII base64). cron.run_sync_for_user must
    encode it back to bytes before passing to Fernet.decrypt.
    """
    from garmin_sync.cron import run_sync_for_user

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (  # noqa: E501
        _make_creds_row('{"oauth": "ok"}')
    )
    fake_garmin = MagicMock()

    with (
        patch("garmin_sync.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.cron.login_with_tokens", return_value=fake_garmin) as login_mock,
        patch("garmin_sync.cron.sync_user_for_date_range") as sync_mock,
    ):
        result = run_sync_for_user("u1", initial=False)

    assert result["status"] == "ok"
    # Critical: login_with_tokens received the decrypted plaintext, NOT raw ciphertext
    login_mock.assert_called_once_with('{"oauth": "ok"}')
    sync_mock.assert_called_once()


def test_run_sync_for_user_returns_no_credentials_when_missing() -> None:
    from garmin_sync.cron import run_sync_for_user

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = None  # noqa: E501

    with patch("garmin_sync.cron.get_admin_client", return_value=fake_db):
        result = run_sync_for_user("u1", initial=False)

    assert result == {"status": "no_credentials"}
