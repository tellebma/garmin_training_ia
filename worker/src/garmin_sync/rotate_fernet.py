"""One-shot script to rotate the Fernet encryption key for stored Garmin tokens.

Every ``garmin_credentials.oauth_tokens_encrypted`` row is re-encrypted with the
active key (the first key in ``Settings.fernet_key_chain()``, i.e. the first
value of ``FERNET_KEYS``, or ``FERNET_KEY`` when ``FERNET_KEYS`` is unset).

Idempotent: a row already encrypted with the active key is left untouched (no
DB write), so re-running the script after a successful rotation — or running
it when no rotation is in progress — is a no-op. Continues past per-user
errors so one bad row never blocks the batch; the exit code is non-zero if at
least one row failed.

Never logs token plaintext or key material — only ``user_id`` and a status.

Usage
-----
    python -m garmin_sync.rotate_fernet [--dry-run]

Rotation procedure: see ``deploy/SECRETS_ROTATION.md``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import sys
from typing import Any, cast

from garmin_sync.config import get_settings
from garmin_sync.crypto import TokenCipher
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)


def _decrypts_with(cipher: TokenCipher, ciphertext: bytes) -> bool:
    with contextlib.suppress(ValueError):
        cipher.decrypt(ciphertext)
        return True
    return False


def rotate_fernet_keys(*, dry_run: bool = False) -> dict[str, int]:
    """Re-encrypt every stored token with the active Fernet key.

    Returns ``{"rotated": int, "already_active": int, "skipped": int, "errors": int}``.
    """
    active_key = get_settings().fernet_key_chain()[0].encode("ascii")
    active_only_cipher = TokenCipher(key=active_key)
    full_chain_cipher = TokenCipher()

    db = get_admin_client()
    rows_resp = (
        db.table("garmin_credentials")
        .select("user_id, oauth_tokens_encrypted")
        .not_.is_("oauth_tokens_encrypted", "null")
        .execute()
    )
    rows = cast("list[dict[str, Any]]", rows_resp.data or [])

    counts = {"rotated": 0, "already_active": 0, "skipped": 0, "errors": 0}

    for row in rows:
        user_id = row.get("user_id")
        ciphertext_text = row.get("oauth_tokens_encrypted")
        if not user_id or not ciphertext_text:
            counts["skipped"] += 1
            continue

        ciphertext = ciphertext_text.encode("ascii")

        if _decrypts_with(active_only_cipher, ciphertext):
            counts["already_active"] += 1
            log.info("user=%s status=already_active", user_id)
            continue

        try:
            plaintext = full_chain_cipher.decrypt(ciphertext)
        except ValueError:
            counts["errors"] += 1
            log.error("user=%s status=undecryptable", user_id)
            continue

        if dry_run:
            counts["rotated"] += 1
            log.info("user=%s status=would_rotate", user_id)
            continue

        try:
            re_encrypted = active_only_cipher.encrypt(plaintext)
            db.table("garmin_credentials").update(
                {"oauth_tokens_encrypted": re_encrypted.decode("ascii")}
            ).eq("user_id", user_id).execute()
        except Exception:
            counts["errors"] += 1
            log.exception("user=%s status=write_failed", user_id)
            continue

        counts["rotated"] += 1
        log.info("user=%s status=rotated", user_id)

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be rotated without writing to the database",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    result = rotate_fernet_keys(dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
