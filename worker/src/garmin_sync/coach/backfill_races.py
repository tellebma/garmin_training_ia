"""Backfill du tag « course » sur tout l'historique (E23.1).

La détection tourne au sync sur la fenêtre synchronisée : elle ne voit donc que les
courses du jour. Les épreuves déjà courues avant la mise en service — dont le premier
triathlon de l'athlète, qui est précisément le cas d'usage de la vue course — n'ont
jamais été rattachées. Ce module rejoue la détection sur l'ensemble des `race_goals`.

Idempotent : une activité déjà rattachée à la bonne course ne produit aucune écriture,
et une activité taguée à la main n'est jamais réécrite.

Usage : python -m garmin_sync.coach.backfill_races [--user-id UUID]
"""

from __future__ import annotations

import logging
from typing import Any, cast

from garmin_sync.coach.race_tagging import tag_races_for_user
from garmin_sync.supabase_client import get_admin_client

log = logging.getLogger(__name__)


def _users_with_races(db: Any, user_id: str | None) -> list[str]:
    if user_id:
        return [user_id]
    rows = cast(
        "list[dict[str, Any]]",
        db.table("race_goals").select("user_id").execute().data or [],
    )
    return sorted({str(row["user_id"]) for row in rows if row.get("user_id")})


def backfill_races(user_id: str | None = None) -> dict[str, int]:
    """Rejoue la détection de course pour un athlète, ou pour tous."""
    db = get_admin_client()
    users = _users_with_races(db, user_id)
    tagged = 0
    for uid in users:
        count = tag_races_for_user(db, uid)
        tagged += count
        if count:
            log.info("race backfill: %s activities tagged for user=%s", count, uid)
    return {"users": len(users), "tagged": tagged}


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", default=None, help="restrict the backfill to one athlete")
    args = parser.parse_args()
    print(json.dumps(backfill_races(args.user_id), indent=2))
