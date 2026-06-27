from typing import Any

import pytest

import garmin_sync.ondemand_sync as mod


class _FakeRpc:
    def __init__(self, data: Any) -> None:
        self._data = data

    def execute(self) -> Any:
        class _Resp:
            data = self._data

        return _Resp()


class _FakeDb:
    def __init__(self, data: Any) -> None:
        self._data = data
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> _FakeRpc:
        self.calls.append((name, params))
        return _FakeRpc(self._data)


def test_window_by_trigger_values() -> None:
    assert mod.WINDOW_BY_TRIGGER == {"auto": 1800, "manual": 300}


def test_try_claim_sync_claimed(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb({"outcome": "claimed"})
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    result = mod.try_claim_sync("user-1", 1800)

    assert result == {"outcome": "claimed"}
    assert db.calls == [
        ("try_claim_garmin_sync", {"p_user_id": "user-1", "p_window_seconds": 1800})
    ]


def test_try_claim_sync_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb({"outcome": "cooldown", "retry_after_seconds": 240})
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    result = mod.try_claim_sync("user-1", 300)

    assert result == {"outcome": "cooldown", "retry_after_seconds": 240}


def test_try_claim_sync_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb({"outcome": "no_credentials"})
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    assert mod.try_claim_sync("user-1", 1800) == {"outcome": "no_credentials"}


def test_try_claim_sync_unexpected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb(None)
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    assert mod.try_claim_sync("user-1", 1800) == {"outcome": "no_credentials"}


def test_run_ondemand_sync_invalid_trigger() -> None:
    assert mod.run_ondemand_sync("user-1", "weekly") == {"status": "invalid_trigger"}


def test_run_ondemand_sync_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mod, "try_claim_sync", lambda _u, _w: {"outcome": "cooldown", "retry_after_seconds": 120}
    )
    started: list[str] = []
    monkeypatch.setattr(mod, "_start_sync_thread", lambda uid: started.append(uid))

    result = mod.run_ondemand_sync("user-1", "manual")

    assert result == {"status": "cooldown", "retry_after_seconds": 120}
    assert started == []  # no sync when cooled down


def test_run_ondemand_sync_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "try_claim_sync", lambda _u, _w: {"outcome": "no_credentials"})
    started: list[str] = []
    monkeypatch.setattr(mod, "_start_sync_thread", lambda uid: started.append(uid))

    assert mod.run_ondemand_sync("user-1", "auto") == {"status": "no_credentials"}
    assert started == []


def test_run_ondemand_sync_started_uses_auto_window(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, int] = {}

    def _claim(user_id: str, window: int) -> dict[str, Any]:
        seen["window"] = window
        return {"outcome": "claimed"}

    monkeypatch.setattr(mod, "try_claim_sync", _claim)
    started: list[str] = []
    monkeypatch.setattr(mod, "_start_sync_thread", lambda uid: started.append(uid))

    result = mod.run_ondemand_sync("user-7", "auto")

    assert result == {"status": "started"}
    assert seen["window"] == 1800
    assert started == ["user-7"]
