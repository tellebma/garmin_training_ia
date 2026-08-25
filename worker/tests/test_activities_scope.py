"""Tests de la portée « activités qui comptent » (E24)."""

from __future__ import annotations

from unittest.mock import MagicMock

from garmin_sync.activities_scope import counted


def test_counted_filters_out_excluded_rows() -> None:
    query = MagicMock()

    result = counted(query)

    query.is_.assert_called_once_with("excluded_at", "null")
    assert result is query.is_.return_value


def test_transform_activity_never_writes_the_exclusion_flag() -> None:
    """Le sync ne doit jamais ressusciter une activité exclue.

    `ON CONFLICT DO UPDATE SET` ne réécrit que les colonnes présentes dans la ligne
    upsertée : tant que le transformer ne produit pas `excluded_at`, l'exclusion
    survit à toutes les resynchronisations.
    """
    from garmin_sync.transformers.activities import transform_activity

    row = transform_activity(
        user_id="user-1",
        raw={
            "activityId": 42,
            "startTimeGMT": "2026-08-22 07:30:00",
            "activityType": {"typeKey": "cycling"},
            "duration": 3600,
            "distance": 40000,
        },
    )

    assert "excluded_at" not in row
    assert "excluded_reason" not in row


def test_every_metric_reader_goes_through_the_scope_helper() -> None:
    """Garde-fou : le risque de E24 est d'oublier un appelant, pas d'écrire le flag.

    Si une lecture d'`activities` alimentant une métrique cesse d'utiliser `counted()`,
    une activité exclue se remet à compter en silence — ce test échoue à la place.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "src" / "garmin_sync"
    readers = [
        "coach/state.py",
        "coach/planner.py",
        "coach/discipline_level.py",
        "coach/briefing.py",
        "coach/sessions.py",
        "coach/chat/handlers.py",
        "coach/col_matching.py",
        "coach/home_location.py",
        "coach/race_tagging.py",
    ]

    for reader in readers:
        content = (src / reader).read_text(encoding="utf-8")
        assert "counted(" in content, f"{reader} lit activities sans filtrer les exclues"
