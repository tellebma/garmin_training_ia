"""Tests for rotate_fernet — batch re-encryption of stored Garmin tokens."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.config import get_settings
from garmin_sync.crypto import TokenCipher, generate_fernet_key


@pytest.fixture(autouse=True)
def _clear_settings_cache_after_test():  # type: ignore[no-untyped-def]
    yield
    get_settings.cache_clear()


def _fake_db_with_rows(rows: list[dict[str, object]]) -> MagicMock:
    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.not_.is_.return_value.execute.return_value.data = rows  # noqa: E501
    return fake_db


def test_rotate_reencrypts_rows_using_legacy_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row encrypted with a legacy key gets re-encrypted with the active key
    and written back."""
    old_key = generate_fernet_key()
    new_key = generate_fernet_key()

    legacy_cipher = TokenCipher(key=old_key.encode("ascii"))
    ciphertext = legacy_cipher.encrypt('{"oauth": "ok"}').decode("ascii")

    monkeypatch.setenv("FERNET_KEYS", f"{new_key},{old_key}")
    get_settings.cache_clear()

    fake_db = _fake_db_with_rows([{"user_id": "u1", "oauth_tokens_encrypted": ciphertext}])

    from garmin_sync.rotate_fernet import rotate_fernet_keys

    with patch("garmin_sync.rotate_fernet.get_admin_client", return_value=fake_db):
        result = rotate_fernet_keys()

    assert result == {"rotated": 1, "already_active": 0, "skipped": 0, "errors": 0}

    update_calls = fake_db.table.return_value.update.call_args_list
    assert len(update_calls) == 1
    new_ciphertext = update_calls[0].args[0]["oauth_tokens_encrypted"]
    active_only = TokenCipher(key=new_key.encode("ascii"))
    assert active_only.decrypt(new_ciphertext.encode("ascii")) == '{"oauth": "ok"}'


def test_rotate_is_idempotent_for_rows_already_on_active_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row already encrypted with the active key must not be rewritten —
    re-running the script after a successful rotation is a no-op."""
    new_key = generate_fernet_key()
    old_key = generate_fernet_key()
    monkeypatch.setenv("FERNET_KEYS", f"{new_key},{old_key}")
    get_settings.cache_clear()

    active_cipher = TokenCipher(key=new_key.encode("ascii"))
    ciphertext = active_cipher.encrypt('{"oauth": "already-active"}').decode("ascii")

    fake_db = _fake_db_with_rows([{"user_id": "u1", "oauth_tokens_encrypted": ciphertext}])

    from garmin_sync.rotate_fernet import rotate_fernet_keys

    with patch("garmin_sync.rotate_fernet.get_admin_client", return_value=fake_db):
        result = rotate_fernet_keys()

    assert result == {"rotated": 0, "already_active": 1, "skipped": 0, "errors": 0}
    fake_db.table.return_value.update.assert_not_called()


def test_rotate_dry_run_does_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    old_key = generate_fernet_key()
    new_key = generate_fernet_key()
    legacy_cipher = TokenCipher(key=old_key.encode("ascii"))
    ciphertext = legacy_cipher.encrypt('{"oauth": "ok"}').decode("ascii")

    monkeypatch.setenv("FERNET_KEYS", f"{new_key},{old_key}")
    get_settings.cache_clear()

    fake_db = _fake_db_with_rows([{"user_id": "u1", "oauth_tokens_encrypted": ciphertext}])

    from garmin_sync.rotate_fernet import rotate_fernet_keys

    with patch("garmin_sync.rotate_fernet.get_admin_client", return_value=fake_db):
        result = rotate_fernet_keys(dry_run=True)

    assert result == {"rotated": 1, "already_active": 0, "skipped": 0, "errors": 0}
    fake_db.table.return_value.update.assert_not_called()


def test_rotate_counts_undecryptable_rows_as_errors_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row that can't be decrypted with any key in the chain (corrupted, or
    encrypted with a key that's been fully retired) is counted as an error but
    must not stop the batch — the next row still gets processed."""
    old_key = generate_fernet_key()
    new_key = generate_fernet_key()
    unrelated_key = generate_fernet_key()

    unrelated_cipher = TokenCipher(key=unrelated_key.encode("ascii"))
    bad_ciphertext = unrelated_cipher.encrypt("orphaned").decode("ascii")

    legacy_cipher = TokenCipher(key=old_key.encode("ascii"))
    good_ciphertext = legacy_cipher.encrypt('{"oauth": "ok"}').decode("ascii")

    monkeypatch.setenv("FERNET_KEYS", f"{new_key},{old_key}")
    get_settings.cache_clear()

    fake_db = _fake_db_with_rows(
        [
            {"user_id": "u-bad", "oauth_tokens_encrypted": bad_ciphertext},
            {"user_id": "u-good", "oauth_tokens_encrypted": good_ciphertext},
        ]
    )

    from garmin_sync.rotate_fernet import rotate_fernet_keys

    with patch("garmin_sync.rotate_fernet.get_admin_client", return_value=fake_db):
        result = rotate_fernet_keys()

    assert result == {"rotated": 1, "already_active": 0, "skipped": 0, "errors": 1}


def test_rotate_skips_rows_with_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    new_key = generate_fernet_key()
    monkeypatch.setenv("FERNET_KEYS", new_key)
    get_settings.cache_clear()

    fake_db = _fake_db_with_rows([{"user_id": "u1", "oauth_tokens_encrypted": None}])

    from garmin_sync.rotate_fernet import rotate_fernet_keys

    with patch("garmin_sync.rotate_fernet.get_admin_client", return_value=fake_db):
        result = rotate_fernet_keys()

    assert result == {"rotated": 0, "already_active": 0, "skipped": 1, "errors": 0}


def test_rotate_never_logs_plaintext_or_key_material(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    old_key = generate_fernet_key()
    new_key = generate_fernet_key()
    legacy_cipher = TokenCipher(key=old_key.encode("ascii"))
    secret_plaintext = '{"access_token": "super-secret-value"}'
    ciphertext = legacy_cipher.encrypt(secret_plaintext).decode("ascii")

    monkeypatch.setenv("FERNET_KEYS", f"{new_key},{old_key}")
    get_settings.cache_clear()

    fake_db = _fake_db_with_rows([{"user_id": "u1", "oauth_tokens_encrypted": ciphertext}])

    from garmin_sync.rotate_fernet import rotate_fernet_keys

    with (
        patch("garmin_sync.rotate_fernet.get_admin_client", return_value=fake_db),
        caplog.at_level("INFO"),
    ):
        rotate_fernet_keys()

    log_text = caplog.text
    assert secret_plaintext not in log_text
    assert old_key not in log_text
    assert new_key not in log_text


def test_main_exits_nonzero_when_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_db = _fake_db_with_rows(
        [{"user_id": "u-bad", "oauth_tokens_encrypted": "not-valid-base64-ciphertext"}]
    )

    from garmin_sync.rotate_fernet import main

    with patch("garmin_sync.rotate_fernet.get_admin_client", return_value=fake_db):
        exit_code = main([])

    assert exit_code == 1


def test_main_exits_zero_and_prints_json_when_no_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_db = _fake_db_with_rows([])

    from garmin_sync.rotate_fernet import main

    with patch("garmin_sync.rotate_fernet.get_admin_client", return_value=fake_db):
        exit_code = main([])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"rotated": 0, "already_active": 0, "skipped": 0, "errors": 0}


def test_main_dry_run_flag_is_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    old_key = generate_fernet_key()
    new_key = generate_fernet_key()
    legacy_cipher = TokenCipher(key=old_key.encode("ascii"))
    ciphertext = legacy_cipher.encrypt('{"oauth": "ok"}').decode("ascii")

    monkeypatch.setenv("FERNET_KEYS", f"{new_key},{old_key}")
    get_settings.cache_clear()

    fake_db = _fake_db_with_rows([{"user_id": "u1", "oauth_tokens_encrypted": ciphertext}])

    from garmin_sync.rotate_fernet import main

    with patch("garmin_sync.rotate_fernet.get_admin_client", return_value=fake_db):
        exit_code = main(["--dry-run"])

    assert exit_code == 0
    fake_db.table.return_value.update.assert_not_called()


def test_rotate_counts_db_write_failure_as_error_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The DB write on rotation can itself fail (network blip, RLS, etc.) —
    that must be counted as an error, not raised, so the batch keeps going."""
    old_key = generate_fernet_key()
    new_key = generate_fernet_key()
    legacy_cipher = TokenCipher(key=old_key.encode("ascii"))
    ciphertext = legacy_cipher.encrypt('{"oauth": "ok"}').decode("ascii")

    monkeypatch.setenv("FERNET_KEYS", f"{new_key},{old_key}")
    get_settings.cache_clear()

    fake_db = _fake_db_with_rows([{"user_id": "u1", "oauth_tokens_encrypted": ciphertext}])
    fake_db.table.return_value.update.return_value.eq.return_value.execute.side_effect = (
        RuntimeError("db unavailable")
    )

    from garmin_sync.rotate_fernet import rotate_fernet_keys

    with patch("garmin_sync.rotate_fernet.get_admin_client", return_value=fake_db):
        result = rotate_fernet_keys()

    assert result == {"rotated": 0, "already_active": 0, "skipped": 0, "errors": 1}


def test_rotate_fernet_main_block_runs_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke-test the ``if __name__ == '__main__'`` block via runpy, mirroring
    the pattern used in test_cron.py::test_cron_main_block_prints_json."""
    import runpy
    import sys

    fake_db = _fake_db_with_rows([])
    monkeypatch.setattr(
        "garmin_sync.supabase_client.get_admin_client",
        lambda: fake_db,
    )

    original_argv = sys.argv
    sys.argv = ["garmin_sync.rotate_fernet"]
    try:
        sys.modules.pop("garmin_sync.rotate_fernet", None)
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("garmin_sync.rotate_fernet", run_name="__main__")
        assert exc_info.value.code == 0
    finally:
        sys.argv = original_argv
        sys.modules.pop("garmin_sync.rotate_fernet", None)
