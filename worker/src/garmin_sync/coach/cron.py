"""Cron entry point — regenerate plans weekly for all active users.

Usage : python -m garmin_sync.coach.cron

Triggered by systemd timer on UNRAID server (see worker/deploy/README.md).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, cast

from garmin_sync.coach.planner import generate_plan
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)


def run_weekly_cron() -> dict[str, Any]:
    """For each user with an active future race_goal, regenerate the plan."""
    db = get_admin_client()
    today_iso = date.today().isoformat()
    users_resp = (
        db.table('race_goals')
        .select('user_id')
        .eq('is_primary', True)
        .gte('race_date', today_iso)
        .execute()
    )
    users = cast('list[dict[str, Any]]', users_resp.data or [])
    user_ids = list({u['user_id'] for u in users})

    results: dict[str, dict[str, Any]] = {}
    for uid in user_ids:
        try:
            results[uid] = generate_plan(uid)
        except Exception as e:
            log.exception('Plan regeneration failed for user=%s', uid)
            results[uid] = {'status': 'exception', 'type': type(e).__name__}
    return {'total_users': len(user_ids), 'results': results}


if __name__ == '__main__':
    print(json.dumps(run_weekly_cron(), indent=2))
