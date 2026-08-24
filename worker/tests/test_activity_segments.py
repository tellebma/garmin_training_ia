"""Tests de la décomposition multisport (E22.1)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from garmin_sync.transformers.activities import normalize_sport
from garmin_sync.transformers.segments import (
    extract_child_activity_ids,
    normalize_segment_sport,
    transform_activity_segment,
)


def test_extract_children_from_metadata_dto() -> None:
    parent = {"activityId": 10, "metadataDTO": {"childIds": [11, 12, 13]}}

    assert extract_child_activity_ids(parent) == [11, 12, 13]


def test_extract_children_from_root_key() -> None:
    # Forme rencontrée sur d'autres endpoints : la liste est à la racine.
    assert extract_child_activity_ids({"childIds": ["21", 22]}) == [21, 22]


def test_extract_children_ignores_unusable_values() -> None:
    parent = {"metadataDTO": {"childIds": [None, "abc", 0, 31]}}

    assert extract_child_activity_ids(parent) == [31]


def test_extract_children_absent_returns_empty() -> None:
    # Activité simple, ou multisport dont Garmin ne publie pas la décomposition :
    # pas d'exception, le sync marque l'activité comme traitée et passe.
    assert extract_child_activity_ids({"activityId": 10}) == []
    assert extract_child_activity_ids({"metadataDTO": {}}) == []


def test_transition_stays_a_transition() -> None:
    # `normalize_sport` écrase une transition en `brick` : au niveau du segment,
    # c'est précisément l'information à conserver.
    assert normalize_sport("transition") == "brick"
    assert normalize_segment_sport("transition") == "transition"


def test_multi_sport_type_key_normalizes_to_brick() -> None:
    # Le typeKey réel d'un triathlon Garmin, absent du set avant E22.1.
    assert normalize_sport("multi_sport") == "brick"


def test_segment_sports_follow_the_canonical_mapping() -> None:
    assert normalize_segment_sport("open_water_swimming") == "swim"
    assert normalize_segment_sport("road_biking") == "bike"
    assert normalize_segment_sport("running") == "run"
    # Sport inconnu : conservé tel quel, le front dégrade sans planter.
    assert normalize_segment_sport("kayaking") == "kayaking"


def test_transform_child_with_summary_dto() -> None:
    child: dict[str, Any] = {
        "activityId": 12,
        "activityTypeDTO": {"typeKey": "cycling"},
        "summaryDTO": {
            "startTimeGMT": "2026-08-16 08:12:00",
            "duration": 4200.0,
            "distance": 40000.0,
            "averageSpeed": 9.52,
            "averageHR": 148,
            "elevationGain": 320,
        },
    }

    row = transform_activity_segment(
        user_id="u1", parent_activity_id=10, segment_index=2, raw=child
    )

    assert row["garmin_activity_id"] == 10
    assert row["garmin_child_activity_id"] == 12
    assert row["segment_index"] == 2
    assert row["sport"] == "bike"
    assert row["duration_s"] == 4200
    assert row["distance_m"] == 40000.0
    assert row["hr_avg"] == 148
    assert row["elevation_gain_m"] == 320
    assert row["start_time"] == "2026-08-16T08:12:00+00:00"
    assert row["pace_avg_s_per_km"] == 105.04


def test_transform_child_with_flat_shape() -> None:
    # Forme de la liste d'activités : métriques à plat, pas de summaryDTO.
    child: dict[str, Any] = {
        "activityId": 11,
        "activityType": {"typeKey": "lap_swimming"},
        "startTimeGMT": "2026-08-16 07:30:00",
        "duration": 1500.0,
        "distance": 1500.0,
        "averageHR": 152,
    }

    row = transform_activity_segment(
        user_id="u1", parent_activity_id=10, segment_index=0, raw=child
    )

    assert row["sport"] == "swim"
    assert row["duration_s"] == 1500
    # Pas de vitesse moyenne publiée : l'allure retombe sur distance / durée.
    assert row["pace_avg_s_per_km"] == 1000.0


def test_transform_transition_without_distance() -> None:
    child: dict[str, Any] = {
        "activityId": 14,
        "activityTypeDTO": {"typeKey": "transition"},
        "summaryDTO": {"duration": 92.0},
    }

    row = transform_activity_segment(
        user_id="u1", parent_activity_id=10, segment_index=1, raw=child
    )

    assert row["sport"] == "transition"
    assert row["duration_s"] == 92
    assert row["distance_m"] is None
    assert row["pace_avg_s_per_km"] is None
    assert row["start_time"] is None


def _fake_db_with_candidate(activity_id: int) -> MagicMock:
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.in_.return_value
    chain.is_.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"garmin_activity_id": activity_id}
    ]
    return db


def test_sync_persists_segments_and_marks_activity() -> None:
    from garmin_sync import sync as sync_mod

    db = _fake_db_with_candidate(10)
    client = MagicMock()
    client.get_activity.side_effect = [
        {"activityId": 10, "metadataDTO": {"childIds": [11, 12]}},
        {"activityId": 11, "activityType": {"typeKey": "lap_swimming"}, "duration": 1500.0},
        {"activityId": 12, "activityType": {"typeKey": "cycling"}, "duration": 4200.0},
    ]

    sync_mod._sync_activity_segments(db, "u1", client, 3)

    upserts = [
        call
        for call in db.table.return_value.upsert.call_args_list
        if call.kwargs.get("on_conflict") == "user_id,garmin_activity_id,segment_index"
    ]
    assert len(upserts) == 1
    rows = upserts[0].args[0]
    assert [row["sport"] for row in rows] == ["swim", "bike"]
    assert [row["segment_index"] for row in rows] == [0, 1]
    assert db.table.return_value.update.called


def test_sync_marks_activity_even_without_children() -> None:
    # Sans marqueur, une activité multisport sans décomposition exploitable serait
    # ré-interrogée chez Garmin à chaque cron.
    from garmin_sync import sync as sync_mod

    db = _fake_db_with_candidate(10)
    client = MagicMock()
    client.get_activity.return_value = {"activityId": 10}

    sync_mod._sync_activity_segments(db, "u1", client, 3)

    assert not [
        call
        for call in db.table.return_value.upsert.call_args_list
        if call.kwargs.get("on_conflict") == "user_id,garmin_activity_id,segment_index"
    ]
    update_args = db.table.return_value.update.call_args.args[0]
    assert "segments_checked_at" in update_args


def test_sync_skips_one_unreadable_child() -> None:
    from garmin_sync import sync as sync_mod

    db = _fake_db_with_candidate(10)
    client = MagicMock()
    client.get_activity.side_effect = [
        {"activityId": 10, "metadataDTO": {"childIds": [11, 12]}},
        RuntimeError("garmin 500"),
        {"activityId": 12, "activityType": {"typeKey": "running"}, "duration": 1200.0},
    ]

    sync_mod._sync_activity_segments(db, "u1", client, 3)

    rows = next(
        call.args[0]
        for call in db.table.return_value.upsert.call_args_list
        if call.kwargs.get("on_conflict") == "user_id,garmin_activity_id,segment_index"
    )
    assert [row["sport"] for row in rows] == ["run"]


def test_sync_segments_disabled_when_limit_is_zero() -> None:
    from garmin_sync import sync as sync_mod

    db = MagicMock()
    client = MagicMock()

    sync_mod._sync_activity_segments(db, "u1", client, 0)

    client.get_activity.assert_not_called()


def test_transform_accepts_activity_type_as_plain_string() -> None:
    # Forme rencontrée sur certains payloads : le type est une chaîne, pas un objet.
    row = transform_activity_segment(
        user_id="u1",
        parent_activity_id=10,
        segment_index=0,
        raw={"activityId": 11, "activityType": "running", "duration": 600.0},
    )

    assert row["sport"] == "run"


def test_transform_ignores_unparseable_start_time() -> None:
    row = transform_activity_segment(
        user_id="u1",
        parent_activity_id=10,
        segment_index=0,
        raw={"activityId": 11, "startTimeGMT": "hier matin", "duration": 600.0},
    )

    assert row["start_time"] is None
    assert row["sport"] == "unknown"


def test_sync_survives_a_failing_decomposition() -> None:
    # Une décomposition qui casse ne doit pas faire tomber le reste du sync.
    from garmin_sync import sync as sync_mod

    db = _fake_db_with_candidate(10)
    client = MagicMock()
    client.get_activity.side_effect = RuntimeError("garmin 500")

    sync_mod._sync_activity_segments(db, "u1", client, 3)

    assert not db.table.return_value.update.called
