"""Symmetric encryption (Fernet) for sensitive OAuth tokens at rest.

Supports key rotation via ``MultiFernet``: the first key in the chain is the
active key used for all new encryption, any additional keys are only used to
decrypt ciphertext written before a rotation. See ``rotate_fernet.py`` and
``deploy/SECRETS_ROTATION.md`` for the rotation procedure.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from garmin_sync.config import get_settings


def generate_fernet_key() -> str:
    """Helper for ops: generate a new Fernet key (run once, store as env var)."""
    return Fernet.generate_key().decode("ascii")


class TokenCipher:
    """Wraps Fernet symmetric encryption with the project's key(s) from settings.

    Encryption always uses the first (active) key. Decryption is attempted
    against every key in the chain, so ciphertext written with a since-retired
    key still decrypts until it's been rotated (see ``rotate_fernet.py``).
    """

    def __init__(self, key: bytes | None = None, *, keys: list[bytes] | None = None) -> None:
        if keys is not None:
            key_chain = keys
        elif key is not None:
            key_chain = [key]
        else:
            key_chain = [k.encode("ascii") for k in get_settings().fernet_key_chain()]
        self._multi_fernet = MultiFernet([Fernet(k) for k in key_chain])

    def encrypt(self, plaintext: str) -> bytes:
        return self._multi_fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._multi_fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as e:
            msg = "ciphertext is invalid or corrupted"
            raise ValueError(msg) from e
