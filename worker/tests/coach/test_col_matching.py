from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

import garmin_sync.coach.col_matching as mod

# Col voisin du domicile historique des tests (~45.0, 6.0).
NEARBY_COL = {"id": "col-1", "latitude": 45.05, "longitude": 6.05}
# Col du Chaussy — loin de tout domicile, mais sur le tracé d'une sortie en Maurienne.
CHAUSSY_COL = {"id": "col-chaussy", "latitude": 45.3085, "longitude": 6.3235}


class _FakeQuery:
    def __init__(self, rows: Any) -> None:
        self._rows = rows
        self.upserted: list[dict[str, Any]] | None = None
        self.updated: dict[str, Any] | None = None

    @property
    def not_(self) -> _FakeQuery:
        return self

    def select(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def eq(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def is_(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def gt(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def limit(self, value: int) -> _FakeQuery:
        # Reproduit le comportement PostgREST : borne les lignes retournées.
        self._rows = (self._rows or [])[:value]
        return self

    def gte(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def lte(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def order(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def maybe_single(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def upsert(self, rows: list[dict[str, Any]], **_k: Any) -> _FakeQuery:
        self.upserted = rows
        return self

    def update(self, values: dict[str, Any]) -> _FakeQuery:
        self.updated = values
        return self

    def execute(self) -> Any:
        class _R:
            data = self._rows

        return _R()


class _FakeColsQuery(_FakeQuery):
    """Filtre les cols par les bornes `gte`/`lte` posées sur latitude/longitude,
    comme le ferait PostgREST — indispensable pour tester que le matching ne
    compare une activité qu'aux cols de SON bbox, pas au référentiel entier."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__(rows)
        self._bounds: dict[str, float] = {}

    def gte(self, key: str, value: Any) -> _FakeColsQuery:
        self._bounds[f"{key}_min"] = float(value)
        return self

    def lte(self, key: str, value: Any) -> _FakeColsQuery:
        self._bounds[f"{key}_max"] = float(value)
        return self

    def execute(self) -> Any:
        rows = self._rows or []
        if self._bounds:
            rows = [
                r
                for r in rows
                if self._bounds.get("latitude_min", -90) <= float(r["latitude"])
                and float(r["latitude"]) <= self._bounds.get("latitude_max", 90)
                and self._bounds.get("longitude_min", -180) <= float(r["longitude"])
                and float(r["longitude"]) <= self._bounds.get("longitude_max", 180)
            ]
        self._bounds = {}

        class _R:
            data = rows

        return _R()


class _FakeSamplesQuery(_FakeQuery):
    """Routes `.eq("garmin_activity_id", X)` to per-activity canned samples, and
    honors `.range(start, end)` like the real PostgREST-backed client would — this
    is what lets a test reproduce server-side page-cap truncation."""

    def __init__(self, samples_by_activity: dict[int, list[dict[str, Any]]]) -> None:
        super().__init__([])
        self._samples_by_activity = samples_by_activity
        self._activity_id: int | None = None
        self._range: tuple[int, int] | None = None

    def eq(self, key: str, value: Any) -> _FakeSamplesQuery:
        if key == "garmin_activity_id":
            self._activity_id = value
        return self

    def range(self, start: int, end: int) -> _FakeSamplesQuery:
        self._range = (start, end)
        return self

    def execute(self) -> Any:
        all_samples = self._samples_by_activity.get(self._activity_id, [])
        if self._range is not None:
            start, end = self._range
            page = all_samples[start : end + 1]
        else:
            page = all_samples

        class _R:
            data = page

        return _R()


class _FakeDb:
    def __init__(
        self,
        *,
        cols_rows: list[dict[str, Any]],
        profile_row: dict[str, Any] | None,
        activities_rows: list[dict[str, Any]],
        samples_by_activity: dict[int, list[dict[str, Any]]],
    ) -> None:
        self.cols_query = _FakeColsQuery(cols_rows)
        self.profile_query = _FakeQuery(profile_row)
        self.activities_query = _FakeQuery(activities_rows)
        self.samples_query = _FakeSamplesQuery(samples_by_activity)
        self.crossings_query = _FakeQuery(None)

    def table(self, name: str) -> _FakeQuery:
        return {
            "cols": self.cols_query,
            "athlete_profiles": self.profile_query,
            "activities": self.activities_query,
            "activity_samples": self.samples_query,
            "col_crossings": self.crossings_query,
        }[name]


@pytest.fixture(autouse=True)
def _no_overpass_cooldown(monkeypatch: Any) -> None:
    monkeypatch.setattr(mod, "_OVERPASS_COOLDOWN_S", 0)


def test_records_crossing_within_threshold(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        samples_by_activity={1: [{"latitude": 45.0501, "longitude": 6.0501}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", MagicMock())

    mod.recompute_col_crossings("user-1")

    assert db.crossings_query.upserted is not None
    assert len(db.crossings_query.upserted) == 1
    row = db.crossings_query.upserted[0]
    assert row["col_id"] == "col-1"
    assert row["garmin_activity_id"] == 1
    assert row["min_distance_m"] < 150
    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-01T08:00:00Z"}


def test_records_crossing_far_from_home(monkeypatch: Any) -> None:
    # Régression bug prod 2026-07-25 : le col du Chaussy (Maurienne, ~125 km du
    # domicile) était invisible parce que le matching se limitait aux cols à
    # moins de 50 km de chez soi. Le matching par bbox d'activité doit le trouver.
    db = _FakeDb(
        cols_rows=[CHAUSSY_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-25T08:23:31Z"}],
        samples_by_activity={1: [{"latitude": 45.3086, "longitude": 6.3236}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", MagicMock())

    mod.recompute_col_crossings("user-1")

    assert db.crossings_query.upserted is not None
    assert db.crossings_query.upserted[0]["col_id"] == "col-chaussy"


def test_fetches_overpass_for_activity_bbox(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        samples_by_activity={1: [{"latitude": 45.30, "longitude": 6.30}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    overpass_mock = MagicMock()
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", overpass_mock)

    mod.recompute_col_crossings("user-1")

    overpass_mock.assert_called_once()
    south, west, north, east = overpass_mock.call_args.args
    # Le bbox passé à Overpass englobe le tracé, avec une marge de couverture.
    assert south < 45.30 < north
    assert west < 6.30 < east


def test_no_crossing_when_track_stays_beyond_threshold(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        # ~1.1km away from the col, well beyond 150m.
        samples_by_activity={1: [{"latitude": 45.06, "longitude": 6.05}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", MagicMock())

    mod.recompute_col_crossings("user-1")

    assert db.crossings_query.upserted is None
    # Cursor still advances — the activity was processed.
    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-01T08:00:00Z"}


def test_cursor_advances_when_no_cols_in_bbox(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        samples_by_activity={1: [{"latitude": 45.0, "longitude": 6.0}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", MagicMock())

    mod.recompute_col_crossings("user-1")

    assert db.crossings_query.upserted is None
    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-01T08:00:00Z"}


def test_matches_only_against_cols_inside_the_activity_bbox(monkeypatch: Any) -> None:
    # Un col à l'autre bout du pays ne doit même pas être chargé pour cette activité.
    db = _FakeDb(
        cols_rows=[NEARBY_COL, {"id": "col-far", "latitude": 50.0, "longitude": 2.0}],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        samples_by_activity={1: [{"latitude": 45.0501, "longitude": 6.0501}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", MagicMock())

    mod.recompute_col_crossings("user-1")

    assert db.crossings_query.upserted is not None
    assert [r["col_id"] for r in db.crossings_query.upserted] == ["col-1"]


def test_no_new_activities_leaves_cursor_untouched(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": "2026-07-01T08:00:00Z"},
        activities_rows=[],
        samples_by_activity={},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    overpass_mock = MagicMock()
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", overpass_mock)

    mod.recompute_col_crossings("user-1")

    assert db.crossings_query.upserted is None
    assert db.profile_query.updated is None
    overpass_mock.assert_not_called()


def test_activity_without_gps_samples_advances_cursor_without_overpass(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        samples_by_activity={1: []},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    overpass_mock = MagicMock()
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", overpass_mock)

    mod.recompute_col_crossings("user-1")

    assert db.crossings_query.upserted is None
    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-01T08:00:00Z"}
    overpass_mock.assert_not_called()


def test_paginates_past_the_server_row_cap(monkeypatch: Any) -> None:
    # Reproduces a real production bug (2026-07-09): Supabase's REST API enforces
    # its own server-side row cap regardless of the client's requested limit. A
    # 1730-sample activity returned only 1000 rows for a `.limit(5000)` request,
    # silently dropping the second half of the ride — including the exact point
    # that passed within meters of a col. Pagination via `.range()` is the fix;
    # this test shrinks the page size to 2 so a 3-sample activity forces two pages,
    # with the matching sample sitting in the second one.
    monkeypatch.setattr(mod, "_SAMPLE_PAGE_SIZE", 2)
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        samples_by_activity={
            1: [
                {"latitude": 45.0, "longitude": 6.0},  # page 1, far from col
                {"latitude": 45.0, "longitude": 6.0},  # page 1, far from col
                {"latitude": 45.0501, "longitude": 6.0501},  # page 2, within threshold
            ]
        },
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", MagicMock())

    mod.recompute_col_crossings("user-1")

    assert db.crossings_query.upserted is not None
    assert len(db.crossings_query.upserted) == 1
    assert db.crossings_query.upserted[0]["col_id"] == "col-1"


def test_processes_two_activities_and_advances_cursor_to_latest(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[
            {"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"},
            {"garmin_activity_id": 2, "start_time": "2026-07-03T08:00:00Z"},
        ],
        samples_by_activity={
            1: [{"latitude": 45.0501, "longitude": 6.0501}],
            2: [{"latitude": 45.06, "longitude": 6.05}],  # beyond threshold
        },
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    overpass_mock = MagicMock()
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", overpass_mock)

    mod.recompute_col_crossings("user-1")

    assert db.crossings_query.upserted is not None
    assert len(db.crossings_query.upserted) == 1
    assert db.crossings_query.upserted[0]["garmin_activity_id"] == 1
    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-03T08:00:00Z"}
    # Les deux tracés partagent la même zone : un seul appel Overpass (couverture réutilisée).
    overpass_mock.assert_called_once()


def test_fetches_overpass_once_per_distinct_zone(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[],
        profile_row={"col_matching_cursor": None},
        activities_rows=[
            {"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"},
            {"garmin_activity_id": 2, "start_time": "2026-07-03T08:00:00Z"},
        ],
        samples_by_activity={
            1: [{"latitude": 45.0, "longitude": 6.0}],  # zone domicile
            2: [{"latitude": 45.30, "longitude": 6.33}],  # Maurienne, hors couverture
        },
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    overpass_mock = MagicMock()
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", overpass_mock)

    mod.recompute_col_crossings("user-1")

    assert overpass_mock.call_count == 2


def test_overpass_failure_keeps_progress_and_reraises(monkeypatch: Any) -> None:
    # Si Overpass tombe au milieu d'un backfill, on garde le curseur sur la
    # dernière activité traitée avec succès (la suivante sera rejouée au prochain
    # cron) et on propage l'erreur pour que cron.py la capture.
    db = _FakeDb(
        cols_rows=[],
        profile_row={"col_matching_cursor": None},
        activities_rows=[
            {"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"},
            {"garmin_activity_id": 2, "start_time": "2026-07-03T08:00:00Z"},
        ],
        samples_by_activity={
            1: [{"latitude": 45.0, "longitude": 6.0}],
            2: [{"latitude": 45.30, "longitude": 6.33}],  # zone distincte → 2e appel
        },
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    overpass_mock = MagicMock(side_effect=[None, RuntimeError("overpass down")])
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", overpass_mock)

    with pytest.raises(RuntimeError, match="overpass down"):
        mod.recompute_col_crossings("user-1")

    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-01T08:00:00Z"}


def test_backfill_is_bounded_per_run_and_cursor_resumes(monkeypatch: Any) -> None:
    # Audit 2026-07-26 : après le reset du curseur (migration), un seul run de
    # cron retraitait TOUT l'historique (samples + Overpass par zone) d'un coup.
    # On borne chaque run ; le curseur s'arrête à la dernière activité traitée
    # et le cron suivant reprend naturellement la suite.
    monkeypatch.setattr(mod, "_MAX_ACTIVITIES_PER_RUN", 2)
    db = _FakeDb(
        cols_rows=[],
        profile_row={"col_matching_cursor": None},
        activities_rows=[
            {"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"},
            {"garmin_activity_id": 2, "start_time": "2026-07-02T08:00:00Z"},
            {"garmin_activity_id": 3, "start_time": "2026-07-03T08:00:00Z"},
        ],
        samples_by_activity={
            1: [{"latitude": 45.0, "longitude": 6.0}],
            2: [{"latitude": 45.0, "longitude": 6.0}],
            3: [{"latitude": 45.0, "longitude": 6.0}],
        },
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(mod, "fetch_cols_in_bbox", MagicMock())

    mod.recompute_col_crossings("user-1")

    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-02T08:00:00Z"}
