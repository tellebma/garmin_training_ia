from __future__ import annotations

from datetime import date, timedelta

from garmin_sync.coach.discipline_level import compute_discipline_levels

TODAY = date(2026, 6, 22)


def _act(days_ago: int, sport: str, tss: float = 60.0) -> dict:
    return {
        "start_time": (TODAY - timedelta(days=days_ago)).isoformat() + "T08:00:00+00:00",
        "sport": sport,
        "duration_s": 3600,
        "tss": tss,
    }


def _spread_bike(n: int) -> list[dict]:
    # n activities spread across the 90-day window (every ~3.2 days for ~2.18/week)
    return [_act(days_ago=3 + int(i * 3.2), sport="cycling") for i in range(n)]


def test_level_up_when_declared_weak_but_regular_sustained() -> None:
    declared = {"swim": 3, "bike": 2, "run": 3}
    levels = compute_discipline_levels(declared, _spread_bike(28), today=TODAY)
    bike = levels.disciplines["bike"]
    assert bike.adjustment == 1
    assert bike.effective == 3
    assert bike.confidence == "high"
    assert "remonté" in bike.reason.lower()
    assert levels.effective_strengths["bike"] == 3


def test_no_downgrade_when_data_insufficient() -> None:
    # declared strong swim, only 1 swim activity (untracked pool) -> no change
    declared = {"swim": 5, "bike": 3, "run": 3}
    levels = compute_discipline_levels(declared, [_act(10, "lap_swimming")], today=TODAY)
    swim = levels.disciplines["swim"]
    assert swim.adjustment == 0
    assert swim.effective == 5
    assert swim.confidence == "low"
    assert "insuffisantes" in swim.reason.lower()


def test_downgrade_when_declared_strong_but_low_regularity_with_data() -> None:
    # 6 run activities all bunched in one early week -> confident but weak regularity
    declared = {"swim": 3, "bike": 3, "run": 4}
    runs = [_act(days_ago=80 + i, sport="running") for i in range(6)]
    levels = compute_discipline_levels(declared, runs, today=TODAY)
    run = levels.disciplines["run"]
    assert run.adjustment == -1
    assert run.effective == 3
    assert run.confidence == "high"


def test_no_level_up_when_burst_not_sustained() -> None:
    # many bike sessions but all in the last 10 days -> not sustained
    declared = {"swim": 3, "bike": 2, "run": 3}
    burst = [_act(days_ago=i % 10, sport="cycling") for i in range(20)]
    levels = compute_discipline_levels(declared, burst, today=TODAY)
    assert levels.disciplines["bike"].adjustment == 0


def test_confirmed_when_data_matches_declared() -> None:
    declared = {"swim": 3, "bike": 3, "run": 3}
    levels = compute_discipline_levels(declared, _spread_bike(10), today=TODAY)
    bike = levels.disciplines["bike"]
    assert bike.adjustment == 0
    assert bike.confidence == "high"
    assert bike.reason == "Niveau confirmé."


def test_no_activity_is_safe_noop() -> None:
    declared = {"swim": 2, "bike": 4, "run": 3}
    levels = compute_discipline_levels(declared, [], today=TODAY)
    assert levels.effective_strengths == {"swim": 2, "bike": 4, "run": 3}
    assert all(d.confidence == "low" for d in levels.disciplines.values())


def test_cap_and_floor_respected() -> None:
    # declared 1 with strong history -> up to 2 (not below 1, never jumps 2)
    up = compute_discipline_levels({"swim": 3, "bike": 1, "run": 3}, _spread_bike(28), today=TODAY)
    assert up.disciplines["bike"].effective == 2
    # to_dict shape
    payload = up.to_dict()
    assert set(payload["disciplines"]) == {"swim", "bike", "run"}
    assert "signals" in payload["disciplines"]["bike"]
