"""Tests de la détection des activités de course (E23.1)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from garmin_sync.coach.race_tagging import (
    apply_race_tags,
    expected_distance_m,
    match_race_activities,
    race_sports,
    tag_races_for_user,
)

TRIATHLON = {
    "id": "race-1",
    "race_date": "2026-08-22",
    "discipline": "triathlon",
    "legs": [
        {"order": 1, "discipline": "swim", "distance_km": 1.4},
        {"order": 2, "discipline": "bike", "distance_km": 40.0},
        {"order": 3, "discipline": "run", "distance_km": 10.0},
    ],
}

TEN_K = {
    "id": "race-2",
    "race_date": "2026-06-14",
    "discipline": "run",
    "legs": [{"order": 1, "discipline": "run", "distance_km": 10.0}],
}


def activity(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "act-1",
        "start_time": "2026-08-22T07:30:00+00:00",
        "sport": "brick",
        "distance_m": 51_400.0,
        "duration_s": 9_000,
        "race_goal_id": None,
        "race_tag_source": None,
    }
    return {**base, **overrides}


def test_multisport_activity_on_race_day_is_tagged() -> None:
    assert match_race_activities([TRIATHLON], [activity()]) == {"act-1": "race-1"}


def test_mono_discipline_race_matches_its_sport() -> None:
    run = activity(
        id="act-run",
        start_time="2026-06-14T08:00:00+00:00",
        sport="run",
        distance_m=10_050.0,
        duration_s=2_700,
    )

    assert match_race_activities([TEN_K], [run]) == {"act-run": "race-2"}


def test_warmup_jog_on_race_morning_is_not_a_race() -> None:
    # Le faux positif le plus probable : 3 km de décrassage le matin même.
    jog = activity(id="act-jog", sport="run", distance_m=3_000.0, duration_s=1_100)

    assert match_race_activities([TRIATHLON], [jog]) == {}


def test_incompatible_sport_is_ignored() -> None:
    # Une séance de musculation le jour de la course n'est pas la course.
    strength = activity(id="act-gym", sport="strength_training", distance_m=None, duration_s=3_600)

    assert match_race_activities([TRIATHLON], [strength]) == {}


def test_activity_on_another_day_is_ignored() -> None:
    day_after = activity(id="act-2", start_time="2026-08-23T07:30:00+00:00")

    assert match_race_activities([TRIATHLON], [day_after]) == {}


def test_manual_tag_is_never_overwritten() -> None:
    # L'athlète a écarté cette activité à la main : la détection ne doit pas revenir dessus.
    manual = activity(race_tag_source="manual")

    assert match_race_activities([TRIATHLON], [manual]) == {}


def test_already_tagged_activity_produces_no_write() -> None:
    already = activity(race_goal_id="race-1", race_tag_source="auto")

    assert match_race_activities([TRIATHLON], [already]) == {}


def test_swim_leg_activity_matches_its_own_distance() -> None:
    # Montre qui enregistre chaque discipline séparément : la natation seule (1,4 km)
    # doit passer le seuil de volume du leg natation, pas celui de l'épreuve entière.
    swim = activity(id="act-swim", sport="swim", distance_m=1_420.0, duration_s=1_800)

    assert match_race_activities([TRIATHLON], [swim]) == {"act-swim": "race-1"}


def test_race_without_legs_falls_back_on_total_distance() -> None:
    race = {
        "id": "race-3",
        "race_date": "2026-05-01",
        "discipline": "bike",
        "legs": [],
        "total_distance_km": 120.0,
    }
    ride = activity(
        id="act-bike", start_time="2026-05-01T08:00:00+00:00", sport="bike", distance_m=118_000.0
    )

    assert match_race_activities([race], [ride]) == {"act-bike": "race-3"}


def test_race_without_any_distance_uses_duration_floor() -> None:
    race = {"id": "race-4", "race_date": "2026-05-02", "discipline": "swim", "legs": []}
    short = activity(
        id="act-short",
        start_time="2026-05-02T08:00:00+00:00",
        sport="swim",
        distance_m=None,
        duration_s=600,
    )
    long_enough = activity(
        id="act-long",
        start_time="2026-05-02T09:00:00+00:00",
        sport="swim",
        distance_m=None,
        duration_s=2_400,
    )

    assert match_race_activities([race], [short, long_enough]) == {"act-long": "race-4"}


def test_two_races_same_day_picks_the_longest_satisfied() -> None:
    short_format = {
        "id": "race-s",
        "race_date": "2026-08-22",
        "discipline": "triathlon",
        "legs": [
            {"discipline": "swim", "distance_km": 0.75},
            {"discipline": "bike", "distance_km": 20.0},
            {"discipline": "run", "distance_km": 5.0},
        ],
    }

    assert match_race_activities([short_format, TRIATHLON], [activity()]) == {"act-1": "race-1"}


def test_race_sports_and_expected_distance() -> None:
    assert race_sports(TEN_K) == {"run"}
    assert "brick" in race_sports(TRIATHLON)
    assert expected_distance_m(TRIATHLON, "brick") == 51_400.0
    assert expected_distance_m(TRIATHLON, "swim") == 1_400.0
    assert expected_distance_m(TEN_K, "run") == 10_000.0


def test_malformed_legs_do_not_crash() -> None:
    race = {
        "id": "race-x",
        "race_date": "2026-08-22",
        "discipline": "triathlon",
        "legs": ["not-a-dict", {"discipline": "bike", "distance_km": "oops"}],
    }

    assert match_race_activities([race], [activity(distance_m=None, duration_s=7_200)]) == {
        "act-1": "race-x"
    }


def test_apply_race_tags_writes_only_non_manual_rows() -> None:
    db = MagicMock()

    written = apply_race_tags(db, "user-1", {"act-1": "race-1"})

    assert written == 1
    db.table.assert_called_with("activities")
    update = db.table.return_value.update
    update.assert_called_once_with({"race_goal_id": "race-1", "race_tag_source": "auto"})
    update.return_value.eq.return_value.eq.return_value.neq.assert_called_once_with(
        "race_tag_source", "manual"
    )


def test_apply_race_tags_survives_a_write_error() -> None:
    db = MagicMock()
    db.table.return_value.update.return_value.eq.side_effect = RuntimeError("boom")

    assert apply_race_tags(db, "user-1", {"act-1": "race-1"}) == 0


def test_tag_races_for_user_without_races_does_nothing() -> None:
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

    assert tag_races_for_user(db, "user-1") == 0


def test_tag_races_for_user_never_raises() -> None:
    db = MagicMock()
    db.table.side_effect = RuntimeError("supabase down")

    assert tag_races_for_user(db, "user-1") == 0
