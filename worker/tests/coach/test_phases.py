"""Tests for phase computation (base/build/peak/taper backward-planning)."""

from __future__ import annotations

from datetime import date, timedelta

from garmin_sync.coach.phases import compute_phases


def test_12_weeks_plan_distribution() -> None:
    """12-week plan : ~6-7 base + 3 build + 1 peak + 2 taper."""
    start = date(2026, 1, 1)
    race = start + timedelta(weeks=12)
    phases = compute_phases(start, race)
    counts = {p: sum(1 for _, ph in phases if ph == p) for p in ("base", "build", "peak", "taper")}
    assert sum(counts.values()) == 12
    assert counts["taper"] == 2
    assert counts["peak"] >= 1
    assert counts["build"] >= 3
    assert counts["base"] >= 5


def test_8_weeks_plan_has_2_taper() -> None:
    start = date(2026, 1, 1)
    race = start + timedelta(weeks=8)
    phases = compute_phases(start, race)
    assert len(phases) == 8
    counts = {p: sum(1 for _, ph in phases if ph == p) for p in ("base", "build", "peak", "taper")}
    assert counts["taper"] == 2


def test_4_weeks_plan_minimum_1_taper() -> None:
    """Short plan still has at least 1 taper week."""
    start = date(2026, 1, 1)
    race = start + timedelta(weeks=4)
    phases = compute_phases(start, race)
    assert len(phases) == 4
    last_phase = phases[-1][1]
    assert last_phase == "taper"


def test_1_week_plan_is_full_taper() -> None:
    start = date(2026, 1, 1)
    race = start + timedelta(weeks=1)
    phases = compute_phases(start, race)
    assert len(phases) == 1
    assert phases[0] == (0, "taper")


def test_phases_are_in_order_and_indexed() -> None:
    """week_offset must go 0, 1, 2, ... sequentially."""
    start = date(2026, 1, 1)
    race = start + timedelta(weeks=10)
    phases = compute_phases(start, race)
    for i, (offset, _) in enumerate(phases):
        assert offset == i
