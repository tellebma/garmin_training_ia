from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

import garmin_sync.coach.overpass as mod


class _FakeQuery:
    def __init__(self, rows: Any) -> None:
        self._rows = rows
        self.upserted: list[dict[str, Any]] | None = None
        self.updated: dict[str, Any] | None = None

    def select(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def eq(self, *_a: Any, **_k: Any) -> _FakeQuery:
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


class _FakeDb:
    def __init__(self, profile_row: dict[str, Any] | None) -> None:
        self.profile_query = _FakeQuery(profile_row)
        self.cols_query = _FakeQuery(None)

    def table(self, name: str) -> _FakeQuery:
        if name == "athlete_profiles":
            return self.profile_query
        if name == "cols":
            return self.cols_query
        raise AssertionError(f"unexpected table {name}")


_OVERPASS_RESPONSE = {
    "elements": [
        {
            "type": "node",
            "id": 123,
            "lat": 45.05,
            "lon": 6.05,
            "tags": {"mountain_pass": "yes", "name": "Col du Truc", "ele": "1850"},
        },
        {
            "type": "node",
            "id": 456,
            "lat": 45.06,
            "lon": 6.06,
            "tags": {"mountain_pass": "yes"},
        },
    ]
}


def test_refresh_skips_when_cache_is_fresh_and_home_unchanged(monkeypatch: Any) -> None:
    db = _FakeDb(
        {
            "cols_cache_updated_at": "2026-07-01T00:00:00+00:00",
            "cols_cache_home_lat": 45.0,
            "cols_cache_home_lon": 6.0,
        }
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    monkeypatch.setattr(mod, "httpx", httpx_mock)
    # "now" close enough to 2026-07-01 that 30 days haven't passed.
    monkeypatch.setattr(mod, "_now", lambda: mod.datetime(2026, 7, 8, tzinfo=mod.UTC))

    mod.refresh_nearby_cols("user-1", 45.0001, 6.0001)

    httpx_mock.get.assert_not_called()
    assert db.cols_query.upserted is None


def test_refresh_fetches_and_upserts_when_cache_is_stale(monkeypatch: Any) -> None:
    db = _FakeDb(
        {
            "cols_cache_updated_at": "2026-01-01T00:00:00+00:00",
            "cols_cache_home_lat": 45.0,
            "cols_cache_home_lon": 6.0,
        }
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.json.return_value = _OVERPASS_RESPONSE
    monkeypatch.setattr(mod, "httpx", httpx_mock)
    monkeypatch.setattr(mod, "_now", lambda: mod.datetime(2026, 7, 8, tzinfo=mod.UTC))

    mod.refresh_nearby_cols("user-1", 45.0, 6.0)

    httpx_mock.get.assert_called_once()
    # Overpass rejects requests without an identifying User-Agent (406 Not Acceptable) —
    # verified against the live API during manual QA (2026-07-09).
    assert "User-Agent" in httpx_mock.get.call_args.kwargs["headers"]
    assert db.cols_query.upserted is not None
    assert len(db.cols_query.upserted) == 2
    named = next(r for r in db.cols_query.upserted if r["osm_id"] == 123)
    assert named["name"] == "Col du Truc"
    assert named["elevation_m"] == 1850
    unnamed = next(r for r in db.cols_query.upserted if r["osm_id"] == 456)
    assert "Col (OSM #456)" in unnamed["name"]
    assert db.profile_query.updated is not None
    assert db.profile_query.updated["cols_cache_home_lat"] == 45.0


def test_refresh_fetches_when_home_moved_more_than_5km(monkeypatch: Any) -> None:
    db = _FakeDb(
        {
            "cols_cache_updated_at": "2026-07-07T00:00:00+00:00",
            "cols_cache_home_lat": 45.0,
            "cols_cache_home_lon": 6.0,
        }
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.json.return_value = {"elements": []}
    monkeypatch.setattr(mod, "httpx", httpx_mock)
    monkeypatch.setattr(mod, "_now", lambda: mod.datetime(2026, 7, 8, tzinfo=mod.UTC))

    # ~1 degree of latitude is ~111km, well over the 5km threshold.
    mod.refresh_nearby_cols("user-1", 45.1, 6.0)

    httpx_mock.get.assert_called_once()


def test_refresh_propagates_network_errors_without_swallowing(monkeypatch: Any) -> None:
    db = _FakeDb(
        {"cols_cache_updated_at": None, "cols_cache_home_lat": None, "cols_cache_home_lon": None}
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    real_connect_error = mod.httpx.ConnectError
    httpx_mock = MagicMock()
    httpx_mock.get.side_effect = real_connect_error("connection refused")
    monkeypatch.setattr(mod, "httpx", httpx_mock)

    # Must propagate (no internal try/except) — the cron.py caller is responsible
    # for logging/capturing, per this feature's error-handling convention.
    with pytest.raises(real_connect_error, match="connection refused"):
        mod.refresh_nearby_cols("user-1", 45.0, 6.0)


def test_refresh_truncates_overly_long_col_names(monkeypatch: Any) -> None:
    db = _FakeDb(
        {"cols_cache_updated_at": None, "cols_cache_home_lat": None, "cols_cache_home_lon": None}
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    long_name = "A" * 500
    httpx_mock.get.return_value.json.return_value = {
        "elements": [
            {"type": "node", "id": 789, "lat": 45.0, "lon": 6.0, "tags": {"name": long_name}}
        ]
    }
    monkeypatch.setattr(mod, "httpx", httpx_mock)

    mod.refresh_nearby_cols("user-1", 45.0, 6.0)

    assert db.cols_query.upserted is not None
    assert len(db.cols_query.upserted[0]["name"]) == 200


def test_refresh_always_fetches_when_never_cached(monkeypatch: Any) -> None:
    db = _FakeDb(
        {"cols_cache_updated_at": None, "cols_cache_home_lat": None, "cols_cache_home_lon": None}
    )
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    httpx_mock = MagicMock()
    httpx_mock.get.return_value.json.return_value = {"elements": []}
    monkeypatch.setattr(mod, "httpx", httpx_mock)

    mod.refresh_nearby_cols("user-1", 45.0, 6.0)

    httpx_mock.get.assert_called_once()
