"""Symmetric encryption (Fernet) for sensitive OAuth tokens at rest."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from garmin_sync.config import get_settings


def generate_fernet_key() -> str:
    """Helper for ops: generate a new Fernet key (run once, store as env var)."""
    return Fernet.generate_key().decode("ascii")


class TokenCipher:
    """Wraps Fernet symmetric encryption with the project's key from settings."""

    def __init__(self, key: bytes | None = None) -> None:
        if key is None:
            key = get_settings().fernet_key.get_secret_value().encode("ascii")
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as e:
            msg = "ciphertext is invalid or corrupted"
            raise ValueError(msg) from e
