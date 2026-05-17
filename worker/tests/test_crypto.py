"""Tests for crypto.TokenCipher — Fernet encryption of OAuth tokens."""

from __future__ import annotations

import pytest

from garmin_sync.crypto import TokenCipher, generate_fernet_key


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
