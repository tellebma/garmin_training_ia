from __future__ import annotations

from typing import Any

import garmin_sync.coach.col_matching as mod

NEARBY_COL = {"id": "col-1", "latitude": 45.05, "longitude": 6.05}
FAR_COL = {"id": "col-2", "latitude": 50.0, "longitude": 2.0}


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


class _FakeSamplesQuery(_FakeQuery):
    """Routes `.eq("garmin_activity_id", X)` to per-activity canned samples."""

    def __init__(self, samples_by_activity: dict[int, list[dict[str, Any]]]) -> None:
        super().__init__([])
        self._samples_by_activity = samples_by_activity
        self._activity_id: int | None = None

    def eq(self, key: str, value: Any) -> _FakeSamplesQuery:
        if key == "garmin_activity_id":
            self._activity_id = value
        return self

    def execute(self) -> Any:
        class _R:
            data = self._samples_by_activity.get(self._activity_id, [])

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
        self.cols_query = _FakeQuery(cols_rows)
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


def test_records_crossing_within_threshold(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        samples_by_activity={1: [{"latitude": 45.0501, "longitude": 6.0501}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    mod.recompute_col_crossings("user-1", 45.0, 6.0)

    assert db.crossings_query.upserted is not None
    assert len(db.crossings_query.upserted) == 1
    row = db.crossings_query.upserted[0]
    assert row["col_id"] == "col-1"
    assert row["garmin_activity_id"] == 1
    assert row["min_distance_m"] < 150
    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-01T08:00:00Z"}


def test_no_crossing_when_track_stays_beyond_threshold(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        # ~1.1km away from the col, well beyond 150m.
        samples_by_activity={1: [{"latitude": 45.06, "longitude": 6.05}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    mod.recompute_col_crossings("user-1", 45.0, 6.0)

    assert db.crossings_query.upserted is None
    # Cursor still advances — the activity was processed.
    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-01T08:00:00Z"}


def test_skips_entirely_when_no_cols_nearby(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[FAR_COL],
        profile_row={"col_matching_cursor": None},
        activities_rows=[{"garmin_activity_id": 1, "start_time": "2026-07-01T08:00:00Z"}],
        samples_by_activity={1: [{"latitude": 45.0, "longitude": 6.0}]},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    mod.recompute_col_crossings("user-1", 45.0, 6.0)

    assert db.crossings_query.upserted is None
    assert db.profile_query.updated is None


def test_no_new_activities_leaves_cursor_untouched(monkeypatch: Any) -> None:
    db = _FakeDb(
        cols_rows=[NEARBY_COL],
        profile_row={"col_matching_cursor": "2026-07-01T08:00:00Z"},
        activities_rows=[],
        samples_by_activity={},
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    mod.recompute_col_crossings("user-1", 45.0, 6.0)

    assert db.crossings_query.upserted is None
    assert db.profile_query.updated is None


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

    mod.recompute_col_crossings("user-1", 45.0, 6.0)

    assert db.crossings_query.upserted is not None
    assert len(db.crossings_query.upserted) == 1
    assert db.crossings_query.upserted[0]["garmin_activity_id"] == 1
    assert db.profile_query.updated == {"col_matching_cursor": "2026-07-03T08:00:00Z"}
