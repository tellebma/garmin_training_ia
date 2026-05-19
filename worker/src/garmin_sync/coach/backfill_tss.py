"""One-shot script to compute TSS for activities where tss IS NULL.

Idempotent — skip rows where tss is already set.
Usage : python -m garmin_sync.coach.backfill_tss
"""

from __future__ import annotations

import logging
from typing import Any, cast

from garmin_sync.coach.tss import compute_tss
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)


def backfill_tss() -> dict[str, int]:
    """Compute TSS for all activities with tss IS NULL.

    Returns: {"updated": int, "skipped": int, "errors": int}
    """
    db = get_admin_client()
    activities_resp = (
        db.table('activities')
        .select('id, user_id, duration_s, sport, power_avg, hr_avg')
        .is_('tss', 'null')
        .execute()
    )
    activities = cast('list[dict[str, Any]]', activities_resp.data or [])

    profile_cache: dict[str, dict[str, Any]] = {}
    updated = 0
    skipped = 0
    errors = 0
    for a in activities:
        try:
            user_id = a['user_id']
            if user_id not in profile_cache:
                p_resp = (
                    db.table('athlete_profiles')
                    .select('ftp_watts, fc_max_bpm')
                    .eq('user_id', user_id)
                    .single()
                    .execute()
                )
                profile_cache[user_id] = cast('dict[str, Any]', p_resp.data or {})
            profile = profile_cache[user_id]
            tss = compute_tss(
                duration_s=a.get('duration_s', 0),
                sport=a.get('sport', ''),
                power_avg=a.get('power_avg'),
                hr_avg=a.get('hr_avg'),
                ftp_watts=profile.get('ftp_watts'),
                fc_max_bpm=profile.get('fc_max_bpm'),
            )
            if tss is None:
                skipped += 1
                continue
            db.table('activities').update({'tss': tss}).eq('id', a['id']).execute()
            updated += 1
        except Exception:
            log.exception('Failed to backfill TSS for activity %s', a.get('id'))
            errors += 1
    return {'updated': updated, 'skipped': skipped, 'errors': errors}


if __name__ == '__main__':
    import json
    result = backfill_tss()
    print(json.dumps(result, indent=2))
