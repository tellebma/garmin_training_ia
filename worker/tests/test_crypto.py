"""Tests for crypto.TokenCipher — Fernet encryption of OAuth tokens."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from garmin_sync.config import get_settings
from garmin_sync.crypto import TokenCipher, generate_fernet_key


@pytest.fixture(autouse=True)
def _clear_settings_cache_after_test() -> Iterator[None]:
    """Some tests below mutate FERNET_KEYS and clear the settings cache to pick
    it up. Clear it again on teardown so later test modules that call
    ``get_settings()`` don't see a stale, test-local key chain."""
    yield
    get_settings.cache_clear()


def test_roundtrip_encrypt_decrypt() -> None:
    cipher = TokenCipher()
    plaintext = '{"access_token": "abc", "refresh_token": "def"}'
    encrypted = cipher.encrypt(plaintext)
    decrypted = cipher.decrypt(encrypted)
    assert decrypted == plaintext


def test_encrypt_produces_different_bytes_each_time() -> None:
    cipher = TokenCipher()
    plaintext = "same input"
    a = cipher.encrypt(plaintext)
    b = cipher.encrypt(plaintext)
    assert a != b  # Fernet uses random IV → ciphertext differs


def test_decrypt_rejects_tampered_data() -> None:
    cipher = TokenCipher()
    encrypted = cipher.encrypt("payload")
    tampered = encrypted[:-2] + b"00"
    with pytest.raises(ValueError, match=r"invalid|corrupt|InvalidToken"):
        cipher.decrypt(tampered)


def test_generate_fernet_key_is_valid() -> None:
    key = generate_fernet_key()
    assert len(key) == 44
    assert key.endswith("=")


def test_single_key_backward_compat_when_fernet_keys_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No FERNET_KEYS in the environment → behaviour identical to pre-rotation."""
    monkeypatch.delenv("FERNET_KEYS", raising=False)
    get_settings.cache_clear()

    cipher = TokenCipher()
    encrypted = cipher.encrypt("plain")
    assert cipher.decrypt(encrypted) == "plain"


def test_multi_key_decrypts_ciphertext_written_with_legacy_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token encrypted before rotation (old key) must still decrypt once
    FERNET_KEYS lists the new active key followed by the old one."""
    old_key = generate_fernet_key()
    new_key = generate_fernet_key()

    legacy_cipher = TokenCipher(key=old_key.encode("ascii"))
    ciphertext = legacy_cipher.encrypt("legacy-secret")

    monkeypatch.setenv("FERNET_KEYS", f"{new_key},{old_key}")
    get_settings.cache_clear()

    cipher = TokenCipher()
    assert cipher.decrypt(ciphertext) == "legacy-secret"


def test_multi_key_encrypts_with_active_key_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """New ciphertext must always be decryptable by the active key alone —
    proving encrypt() never uses a legacy key even though it's in the chain."""
    active_key = generate_fernet_key()
    legacy_key = generate_fernet_key()

    monkeypatch.setenv("FERNET_KEYS", f"{active_key},{legacy_key}")
    get_settings.cache_clear()

    cipher = TokenCipher()
    ciphertext = cipher.encrypt("fresh-secret")

    active_only = TokenCipher(key=active_key.encode("ascii"))
    assert active_only.decrypt(ciphertext) == "fresh-secret"


def test_multi_key_decrypt_rejects_corrupted_ciphertext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_key = generate_fernet_key()
    legacy_key = generate_fernet_key()
    monkeypatch.setenv("FERNET_KEYS", f"{active_key},{legacy_key}")
    get_settings.cache_clear()

    cipher = TokenCipher()
    encrypted = cipher.encrypt("payload")
    tampered = encrypted[:-2] + b"00"
    with pytest.raises(ValueError, match=r"invalid|corrupt|InvalidToken"):
        cipher.decrypt(tampered)


def test_explicit_keys_kwarg_overrides_settings() -> None:
    """The `keys=` constructor kwarg lets callers build a cipher over an
    explicit key chain without touching global settings (used by
    rotate_fernet.py to build an active-only cipher)."""
    key_a = generate_fernet_key().encode("ascii")
    key_b = generate_fernet_key().encode("ascii")

    cipher = TokenCipher(keys=[key_a, key_b])
    ciphertext = cipher.encrypt("secret")

    # Encrypted with key_a (first in the chain) — a cipher built from key_a
    # alone must be able to decrypt it.
    assert TokenCipher(key=key_a).decrypt(ciphertext) == "secret"
