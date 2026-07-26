from __future__ import annotations

from typing import Any

import garmin_sync.coach.home_location as mod


class _FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.updated: dict[str, Any] | None = None
        self.order_args: tuple[Any, ...] | None = None
        self.order_kwargs: dict[str, Any] | None = None
        self.limit_value: int | None = None

    @property
    def not_(self) -> _FakeQuery:
        return self

    def select(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def eq(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def is_(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def order(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        self.order_args = args
        self.order_kwargs = kwargs
        return self

    def limit(self, value: int) -> _FakeQuery:
        self.limit_value = value
        return self

    def update(self, values: dict[str, Any]) -> _FakeQuery:
        self.updated = values
        return self

    def execute(self) -> Any:
        class _R:
            data = self._rows

        return _R()


class _FakeDb:
    def __init__(self, activities_rows: list[dict[str, Any]]) -> None:
        self.activities_query = _FakeQuery(activities_rows)
        self.profile_query = _FakeQuery([])

    def table(self, name: str) -> _FakeQuery:
        if name == "activities":
            return self.activities_query
        if name == "athlete_profiles":
            return self.profile_query
        raise AssertionError(f"unexpected table {name}")


def test_compute_home_location_uses_median_of_start_points(monkeypatch: Any) -> None:
    rows = [
        {"route_polyline": [[6.0, 45.0], [6.1, 45.1]]},
        {"route_polyline": [[6.2, 45.2], [6.3, 45.3]]},
        {"route_polyline": [[6.4, 45.4]]},
    ]
    db = _FakeDb(rows)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    result = mod.compute_home_location("user-1")

    assert result == (45.2, 6.2)
    assert db.profile_query.updated is not None
    assert db.profile_query.updated["lat"] == 45.2
    assert db.profile_query.updated["lon"] == 6.2
    assert db.profile_query.updated["home_computed_at"] is not None


def test_compute_home_location_ignores_malformed_polylines(monkeypatch: Any) -> None:
    rows = [
        {"route_polyline": [[6.0, 45.0]]},
        {"route_polyline": []},
        {"route_polyline": [[6.2]]},
        {"route_polyline": None},
    ]
    db = _FakeDb(rows)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    result = mod.compute_home_location("user-1")

    assert result == (45.0, 6.0)


def test_compute_home_location_returns_none_without_gps_activities(monkeypatch: Any) -> None:
    db = _FakeDb([])
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    result = mod.compute_home_location("user-1")

    assert result is None
    assert db.profile_query.updated is None


def test_compute_home_location_bounds_the_query(monkeypatch: Any) -> None:
    # Audit 2026-07-26 : le select non borné de route_polyline (colonne JSONB
    # lourde) tournait à chaque sync et finirait tronqué par le cap PostgREST.
    # On borne aux N sorties GPS les plus récentes — sémantiquement meilleur si
    # l'utilisateur déménage.
    db = _FakeDb([{"route_polyline": [[6.0, 45.0]]}])
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    mod.compute_home_location("user-1")

    assert db.activities_query.order_args == ("start_time",)
    assert db.activities_query.order_kwargs == {"desc": True}
    assert db.activities_query.limit_value == mod._RECENT_GPS_ACTIVITIES_LIMIT
