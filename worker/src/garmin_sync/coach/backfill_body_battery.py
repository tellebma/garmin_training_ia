"""Re-derive daily_metrics Body Battery columns from the stored raw payload.

Issue #170 : ``body_battery_high`` received ``bodyBatteryMostRecentValue`` (the
level at sync time, late evening) instead of ``bodyBatteryHighestValue`` (the
daily peak). Rows already in base keep the wrong value, but ``daily_metrics.raw``
holds the full Garmin payload — so history can be repaired without re-syncing
Garmin (and without burning rate-limit budget).

Idempotent : a row whose recomputed columns already match is skipped. After the
updates, ``recovery_baselines`` is recomputed for each touched user, since the
``body_battery`` baseline is a median over ``body_battery_high``.

Usage : python -m garmin_sync.coach.backfill_body_battery [--dry-run] [--skip-baselines]
"""

from __future__ import annotations

import logging
from typing import Any, cast

from garmin_sync.coach.recovery_baselines import recompute_recovery_baselines
from garmin_sync.supabase_client import get_admin_client
from garmin_sync.transformers.daily import body_battery_fields

log = logging.getLogger(__name__)

_COLUMNS = "user_id, date, body_battery_low, body_battery_high, body_battery_current, raw"
_WRITTEN_COLUMNS = ("body_battery_high", "body_battery_current")


def _fetch_rows(db: Any) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", db.table("daily_metrics").select(_COLUMNS).execute().data)


def _pending_update(row: dict[str, Any]) -> dict[str, int | None] | None:
    """Columns to write for this row, or None when nothing must change.

    Returns None as well when ``raw`` carries no Body Battery at all: overwriting
    a stored value with NULL would destroy data rather than repair it.
    """
    raw = row.get("raw")
    if not isinstance(raw, dict):
        return None
    fields = body_battery_fields(raw)
    if all(fields[column] is None for column in _WRITTEN_COLUMNS):
        return None
    update = {c: fields[c] for c in _WRITTEN_COLUMNS if fields[c] != row.get(c)}
    return update or None


def _write(db: Any, row: dict[str, Any], update: dict[str, int | None]) -> None:
    (
        db.table("daily_metrics")
        .update(update)
        .eq("user_id", row["user_id"])
        .eq("date", row["date"])
        .execute()
    )


def _recompute_baselines(touched_users: set[str]) -> tuple[int, int]:
    """Refresh recovery_baselines for each touched user. Returns (recomputed, errors)."""
    recomputed = 0
    errors = 0
    for user_id in sorted(touched_users):
        try:
            recompute_recovery_baselines(user_id)
            recomputed += 1
        except Exception:
            log.exception("Failed to recompute recovery baselines for user %s", user_id)
            errors += 1
    return recomputed, errors


def backfill_body_battery(
    *, dry_run: bool = False, recompute_baselines: bool = True
) -> dict[str, int]:
    """Repair body_battery_high / body_battery_current from daily_metrics.raw.

    Returns: {"updated": int, "skipped": int, "errors": int, "users_recomputed": int}
    In ``dry_run`` mode nothing is written and no baseline is recomputed, but
    ``updated`` still reports how many rows would change.
    """
    db = get_admin_client()
    updated = 0
    skipped = 0
    errors = 0
    touched_users: set[str] = set()

    for row in _fetch_rows(db) or []:
        update = _pending_update(row)
        if update is None:
            skipped += 1
            continue
        if dry_run:
            updated += 1
            continue
        try:
            _write(db, row, update)
        except Exception:
            log.exception(
                "Failed to backfill Body Battery for user=%s date=%s",
                row.get("user_id"),
                row.get("date"),
            )
            errors += 1
            continue
        updated += 1
        touched_users.add(str(row["user_id"]))

    users_recomputed = 0
    if recompute_baselines and not dry_run:
        users_recomputed, baseline_errors = _recompute_baselines(touched_users)
        errors += baseline_errors

    return {
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "users_recomputed": users_recomputed,
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing anything",
    )
    parser.add_argument(
        "--skip-baselines",
        action="store_true",
        help="do not recompute recovery_baselines afterwards",
    )
    args = parser.parse_args()
    result = backfill_body_battery(
        dry_run=args.dry_run, recompute_baselines=not args.skip_baselines
    )
    print(json.dumps(result, indent=2))
